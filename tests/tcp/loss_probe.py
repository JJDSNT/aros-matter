#!/usr/bin/env python3
"""
loss_probe.py - how AROS's TCP recovers from loss it can see with SACK
(RFC 6675, RFC 6937 PRR), on the wire, under losses the host places.

AROS (tcpbench send) sends 1 MB to the host over IPv6 link-local, one
connection per scenario, each to its own port. The host shapes what arrives
from AROS on the tap (tc ingress, before its stack; all set up before AROS
starts, as a fast transfer is over before a command could catch it) and
delays what it sends back by 20 ms:

  random      1 in 50 of AROS's segments dropped (as run_tcp.py)
  partial     three drop counters (every 100th, 101st, 103rd segment):
              several holes in one window, the host's ACKs carry 2+ SACK
              blocks (checked in the capture)
  lostrexmit  a segment and its first retransmission both lost: a u32
              filter on its sequence number drops every copy until the
              second copy has gone by (checked: 3+ copies in the capture)
  reorder     no loss; netem (through an ifb) delays AROS's segments 5 ms
              but sends every 10th at once, ahead of them: every
              retransmission is spurious

For each it reports from the capture: seconds, data segments, retransmitted
segments, needless retransmissions (of data the host had acknowledged or
SACKed in an ACK seen 5 ms or more before), segments sent 3+ times (beyond the lostrexmit one, a sign the
same hole is retransmitted again and again), quiet gaps of 500 ms or more
before a retransmission (timeouts), the host's ACKs with 2+ SACK blocks,
and whether all the bytes arrived.

    loss_probe.py [--arostcp FILE] [--image DIR] [--only a,b] [--out DIR]
Needs sudo -n for tc, ip, tcpdump and the watcher's raw socket.
"""
import argparse, json, os, re, socket, struct, subprocess, sys, threading, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import run_tcp

IFACE = run_tcp.IFACE
IFB = "ifbloss"
BYTES = 1000000
DELAY_MS = 20                    # on what the host sends (the ACKs)
SCENARIOS = {"random": 7051, "partial": 7052, "lostrexmit": 7053, "reorder": 7054}
LOST_AT = 200                    # lostrexmit: the segment 150 after the 200th
LOST_AHEAD = 150


SH_ERRORS = []


def sh(*a, quiet=False):
    r = subprocess.run(["sudo", "-n"] + list(a), capture_output=True, text=True)
    if r.returncode and not quiet:
        SH_ERRORS.append("%s: %s" % (" ".join(a[:6]), r.stderr.strip()[:200]))
    return r


def match(port):
    """u32: TCP over IPv6, to the host's port."""
    return ["u32", "match", "ip6", "protocol", "6", "0xff", "match", "ip6", "dport", str(port), "0xffff"]


def clear():
    sh("tc", "qdisc", "del", "dev", IFACE, "ingress", quiet=True)
    sh("tc", "qdisc", "del", "dev", IFACE, "root", quiet=True)
    sh("ip", "link", "del", IFB, quiet=True)


def shape_all(only):
    """All the scenarios at once, each on its own port: in place before AROS
    connects (setting them up when a connection came in took longer than a
    fast transfer)."""
    clear()
    sh("tc", "qdisc", "add", "dev", IFACE, "root", "netem", "delay", "%dms" % DELAY_MS)
    sh("tc", "qdisc", "add", "dev", IFACE, "ingress")
    prio = 10
    if "random" in only:
        sh("tc", "filter", "add", "dev", IFACE, "parent", "ffff:", "protocol", "ipv6", "prio", str(prio),
           *match(SCENARIOS["random"]), "action", "gact", "continue", "random", "determ", "drop", "50")
        prio += 1
    if "partial" in only:
        for n in (100, 101, 103):
            sh("tc", "filter", "add", "dev", IFACE, "parent", "ffff:", "protocol", "ipv6", "prio", str(prio),
               *match(SCENARIOS["partial"]), "action", "gact", "continue", "random", "determ", "drop", str(n))
            prio += 1
    if "reorder" in only:
        sh("ip", "link", "add", IFB, "type", "ifb")
        sh("ip", "link", "set", IFB, "up")
        sh("tc", "qdisc", "add", "dev", IFB, "root", "netem", "delay", "5ms", "reorder", "100%", "gap", "10")
        sh("tc", "filter", "add", "dev", IFACE, "parent", "ffff:", "protocol", "ipv6", "prio", str(prio),
           *match(SCENARIOS["reorder"]), "action", "mirred", "egress", "redirect", "dev", IFB)


def watch(port, result):
    """lostrexmit, as root: after the LOST_AT-th data segment to port, drop
    every copy of the segment LOST_AHEAD further on until two copies have
    been seen (the first transmission and the first retransmission), then
    let the rest through."""
    p = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(0x0003))
    p.bind((IFACE, 0))
    p.settimeout(1)
    n, target, copies, rec = 0, None, 0, {}
    end = time.time() + 400        # never outlive a run
    while time.time() < end:
        try:
            f, where = p.recvfrom(4096)
        except socket.timeout:
            continue
        if where[2] == socket.PACKET_OUTGOING or f[12:14] != b"\x86\xdd" or f[14 + 6] != 6:
            continue
        t = f[54:]
        dport, seq = struct.unpack("!HI", t[2:8])
        plen = struct.unpack("!H", f[18:20])[0] - (t[12] >> 4) * 4
        if dport != port or plen <= 0:
            continue
        n += 1
        if target is None and n == LOST_AT:
            target = (seq + LOST_AHEAD * plen) & 0xffffffff
            r = sh("tc", "filter", "add", "dev", IFACE, "parent", "ffff:", "protocol", "ipv6", "prio", "1",
                   "u32", "match", "u32", "%#x" % target, "0xffffffff", "at", "44", "action", "gact", "drop")
            rec["target"] = target
            rec["add_rc"] = r.returncode
            rec["add_err"] = r.stderr.strip()[:200]
        elif target is not None and seq == target:
            copies += 1
            rec.setdefault("copy_times", []).append(time.time())
            if copies == 2:
                r = sh("tc", "filter", "del", "dev", IFACE, "parent", "ffff:", "protocol", "ipv6", "prio", "1")
                rec["released"] = r.returncode == 0
                break
    with open(result, "w") as fo:
        json.dump(rec, fo)


class Host:
    def __init__(self, out, only):
        self.log, self.out = {}, out
        for name in only:
            port = SCENARIOS[name]
            s = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("::", port))
            s.listen(2)
            threading.Thread(target=self.serve, args=(name, port, s), daemon=True).start()

    def serve(self, name, port, s):
        c, _ = s.accept()
        t0, n = time.time(), 0
        c.settimeout(60)
        try:
            while True:
                d = c.recv(65536)
                if not d:
                    break
                n += len(d)
        except OSError as e:
            self.log[name + "_error"] = str(e)
        self.log[name] = {"bytes": n, "host_seconds": round(time.time() - t0, 3)}
        c.close()


MARGIN = 0.005      # an ACK AROS has surely read: seen this long before


def needless(pk, port):
    """Retransmissions of data the host had already acknowledged, by its
    cumulative ACK or a SACK block, in an ACK seen at least MARGIN before
    the retransmission (hosted AROS reads its ACKs a little after they
    leave the host): what a scoreboard is there to avoid."""
    una, blocks, seen, n, pending = None, [], set(), 0, []
    for p in pk:
        while pending and pending[0]["t"] <= p["t"] - MARGIN:
            q = pending.pop(0)
            if una is None or (q["ack"] - una) % 2**32 < 2**31:
                una = q["ack"]
            for a, b in re.findall(r"\{(\d+):(\d+)\}", q["opts"]):
                blocks.append((int(a), int(b)))
        if p["sport"] == port and p["ack"] is not None:
            pending.append(p)
        elif p["dport"] == port and p["len"] > 0:
            s, e = p["seq"], (p["seq"] + p["len"]) % 2**32
            if s in seen:
                if una is not None and (una - e) % 2**32 < 2**31:
                    n += 1
                elif any((s - a) % 2**32 < 2**31 and (b - e) % 2**32 < 2**31 for a, b in blocks):
                    n += 1
            seen.add(s)
    return n


def analyse(pk, port):
    data = [p for p in pk if p["dport"] == port and p["len"] > 0]
    acks = [p for p in pk if p["sport"] == port]
    count, retx, quiet, prev = {}, 0, 0, None
    for p in data:
        count[p["seq"]] = count.get(p["seq"], 0) + 1
        if count[p["seq"]] > 1:
            retx += 1
            if prev is not None and p["t"] - prev >= 0.5:
                quiet += 1
        prev = p["t"]
    return {
        "seconds": round(data[-1]["t"] - data[0]["t"], 3) if data else None,
        "data_segments": len(data),
        "retransmissions": retx,
        "sent_3_or_more": sorted(s for s, c in count.items() if c >= 3),
        "timeouts": quiet,
        "needless_retransmissions": needless(pk, port),
        "acks_with_sack": sum(1 for a in acks if "sack " in a["opts"]),
        "acks_2plus_sack": sum(1 for a in acks if a["opts"].count("sack") and
                               len(re.findall(r"\{\d+:\d+\}", a["opts"])) >= 2),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--watch", nargs=2, help=argparse.SUPPRESS)
    ap.add_argument("--image", default=os.environ.get("AROS_HOSTED_IMAGE",
        os.path.expanduser("~/aros-build-ipv6-hosted-claude/bin/linux-x86_64/AROS")))
    ap.add_argument("--arostcp")
    ap.add_argument("--only", default=",".join(SCENARIOS))
    ap.add_argument("--out", default=os.path.join(HERE, "out", "loss-" + time.strftime("%Y%m%d-%H%M%S")))
    a = ap.parse_args()
    if a.watch:
        return watch(int(a.watch[0]), a.watch[1])
    only = a.only.split(",")
    os.makedirs(a.out, exist_ok=True)
    exe = os.path.join(a.out, "tcpbench")
    subprocess.run([run_tcp.CROSS, "-std=gnu99", "-O2", "-Wall", "-Wno-pointer-sign", "-o", exe,
                    os.path.join(HERE, "tcpbench.c")], check=True, capture_output=True)
    subprocess.run([os.path.join(ROOT, "tools", "tap-up.sh")], check=True, stdout=subprocess.DEVNULL)
    clear()
    run_tcp.kill_strays()
    host_ll = re.findall(r"inet6 (fe80::[0-9a-f:]+)/", subprocess.run(
        ["ip", "-6", "addr", "show", "dev", IFACE], capture_output=True, text=True).stdout)[0]
    host = Host(a.out, only)
    shape_all(only)
    w = None
    if "lostrexmit" in only:
        w = subprocess.Popen(["sudo", "-n", sys.executable, "-I", os.path.abspath(__file__),
                              "--watch", str(SCENARIOS["lostrexmit"]), os.path.join(a.out, "watch.json")])
    pcap = os.path.join(a.out, "loss.pcap")
    dump = subprocess.Popen(["sudo", "-n", "tcpdump", "-i", IFACE, "-n", "-s", "128", "-w", pcap, "ip6 and tcp"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1)
    script = os.path.join(a.out, "loss.script")
    with open(script, "w") as f:
        f.write("Execute SYS:System/Network/AROSTCP/S/startnet\nWait 4\n")
        for name in only:
            f.write("C:tcpbench eth0 %s send %d %d >SYS:out/%s.log\nWait 1\n" % (host_ll, SCENARIOS[name], BYTES, name))
    env = dict(os.environ, AROS_HOSTED_IMAGE=a.image, AROS_TAP_IP=run_tcp.AROS_IP, AROS_RUN_TIMEOUT="400")
    if a.arostcp:
        env["AROS_AROSTCP"] = os.path.abspath(a.arostcp)
    r = subprocess.run([os.path.join(ROOT, "tools", "hosted-run.sh"), os.path.join(a.out, "aros"), script, exe],
                       env=env, capture_output=True, text=True)
    time.sleep(1)
    for pid in subprocess.run(["pgrep", "-f", "^tcpdump -i %s -n -s 128 -w %s" % (IFACE, pcap)],
                              capture_output=True, text=True).stdout.split():
        sh("kill", "-INT", pid)
    dump.wait(timeout=10)
    ifb_stats = sh("tc", "-s", "qdisc", "show", "dev", IFB, quiet=True).stdout
    if w:
        try:
            w.wait(timeout=5)
        except subprocess.TimeoutExpired:
            sh("kill", str(w.pid), quiet=True)
    clear()
    text = sh("tcpdump", "-tt", "-nn", "-S", "-v", "-r", pcap).stdout
    open(os.path.join(a.out, "loss.txt"), "w").write(text)
    pk = run_tcp.parse(text)
    res = {"boot": "ok" if "finished" in r.stdout else "did not finish"}
    w = {}
    if os.path.exists(os.path.join(a.out, "watch.json")):
        w = json.load(open(os.path.join(a.out, "watch.json")))
    for name in only:
        x = analyse(pk, SCENARIOS[name])
        x["host"] = host.log.get(name)
        x["complete"] = bool(x["host"] and x["host"]["bytes"] == BYTES)
        res[name] = x
    # the bench checks itself: each scenario did what it is for
    checks = {}
    if "partial" in res:
        checks["partial_has_multi_sack"] = res["partial"]["acks_2plus_sack"] > 0
    if "lostrexmit" in res:
        t = w.get("target")
        checks["lostrexmit_target_3_copies"] = t is not None and t in res["lostrexmit"]["sent_3_or_more"]
        if t is not None:
            res["lostrexmit"]["sent_3_or_more"] = [s for s in res["lostrexmit"]["sent_3_or_more"] if s != t]
    if "reorder" in res:
        # the host saw segments out of order: it SACKed
        checks["reorder_host_sacked"] = res["reorder"]["acks_with_sack"] > 0
    if "random" in res:
        checks["random_has_retransmissions"] = res["random"]["retransmissions"] > 0
    res["checks"] = checks
    res["shaping_errors"] = SH_ERRORS
    res["ifb_stats"] = ifb_stats
    if "lostrexmit" in res:
        res["watch"] = w
    if SH_ERRORS:
        checks["shaping_commands_ok"] = False
    res["bench_ok"] = res["boot"] == "ok" and all(checks.values()) and all(res[n]["complete"] for n in only)
    json.dump(res, open(os.path.join(a.out, "result.json"), "w"), indent=1)
    for name in only:
        x = res[name]
        print("%-10s %6ss segs=%-5s retx=%-4s needless=%-4s 3+=%-3d timeouts=%-2d multi_sack_acks=%-4d complete=%s" % (
            name, x["seconds"], x["data_segments"], x["retransmissions"], x["needless_retransmissions"],
            len(x["sent_3_or_more"]), x["timeouts"], x["acks_2plus_sack"], x["complete"]))
    print("checks=%s bench_ok=%s out=%s" % (checks, res["bench_ok"], a.out))


if __name__ == "__main__":
    main()
