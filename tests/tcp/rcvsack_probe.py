#!/usr/bin/env python3
"""
rcvsack_probe.py - the SACK blocks AROS sends as a receiver (RFC 2018
section 4), on the wire.

The host sends 1 MB to AROS (tcpserve 4 PORT recv) over IPv4. On its way
out the host drops segments with four counters (every 100th, 102nd, 104th
and 106th), so a window has several holes; AROS's ACKs are delayed 20 ms
(netem on an ifb, at the tap's ingress). From the capture (taken where the
host's segments leave, after the drops, so it shows what AROS got):

  first_block_not_highest  ACKs with 2+ blocks whose first block is not
                      the highest: new data comes in order, so the latest
                      segment is in the highest block, and RFC 2018 says
                      the first block MUST hold the segment that triggered
                      the ACK (a retransmission filling a lower hole is the
                      exception, rare here)
  first_block_below_ack  ACKs whose first block lies below their own
                      cumulative ACK: the sender reads it as a D-SACK
                      (RFC 2883), a segment received twice
  report_delay        how long an out-of-order segment waits for its first
                      SACK (median, max)
  first_block_misses  the first block does not hold the segment captured
                      last before the ACK (loose: AROS takes segments in
                      batches)
  max_blocks          the most blocks in one ACK (3 fit with timestamps)
  ranges_never_sacked out-of-order ranges AROS held that no ACK reported
  host seconds, retransmissions and timeouts of the Linux sender

    rcvsack_probe.py [--arostcp FILE] [--image DIR] [--out DIR]
Needs sudo -n for tc, ip and tcpdump.
"""
import argparse, json, os, re, socket, subprocess, sys, threading, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import run_tcp

IFACE = run_tcp.IFACE
IFB = "ifbrsack"
PORT = 7071
BYTES = 1000000
DROPS = (100, 102, 104, 106)


def sh(*a):
    return subprocess.run(["sudo", "-n"] + list(a), capture_output=True, text=True)


def clear():
    sh("tc", "qdisc", "del", "dev", IFACE, "root")
    sh("tc", "qdisc", "del", "dev", IFACE, "ingress")
    sh("ip", "link", "del", IFB)


def shape():
    clear()
    sh("tc", "qdisc", "add", "dev", IFACE, "root", "handle", "1:", "prio")
    for prio, n in enumerate(DROPS, 1):
        sh("tc", "filter", "add", "dev", IFACE, "parent", "1:", "protocol", "ip", "prio", str(prio),
           "u32", "match", "ip", "protocol", "6", "0xff", "match", "ip", "dport", str(PORT), "0xffff",
           "action", "gact", "continue", "random", "determ", "drop", str(n))
    sh("ip", "link", "add", IFB, "type", "ifb")
    sh("ip", "link", "set", IFB, "up")
    sh("tc", "qdisc", "add", "dev", IFB, "root", "netem", "delay", "20ms")
    sh("tc", "qdisc", "add", "dev", IFACE, "ingress")
    sh("tc", "filter", "add", "dev", IFACE, "parent", "ffff:", "protocol", "ip", "prio", "1",
       "u32", "match", "ip", "protocol", "6", "0xff", "match", "ip", "sport", str(PORT), "0xffff",
       "action", "mirred", "egress", "redirect", "dev", IFB)


def sender(log):
    end = time.time() + 120
    while time.time() < end:
        try:
            s = socket.create_connection((run_tcp.AROS_IP, PORT), timeout=2)
        except OSError:
            time.sleep(0.5)
            continue
        t0 = time.time()
        s.sendall(b"x" * BYTES)
        s.shutdown(socket.SHUT_WR)
        s.settimeout(60)
        try:
            s.recv(1)
        except OSError:
            pass
        log["host_seconds"] = round(time.time() - t0, 3)
        s.close()
        return


def parse(text):
    # tcpdump -v puts the IPv4 header on its own line: join each packet's lines
    text = re.sub(r"\n\s+(?=\d+\.\d+\.\d+\.\d+\.\d+ >)", " ", text)
    pk = []
    for m in re.finditer(r"^(\d+\.\d+) IP .*? ([\d.]+)\.(\d+) > ([\d.]+)\.(\d+): Flags \[([^\]]*)\]"
                         r"(?:, cksum \S+(?: \([^)]*\))?)?(?:, seq (\d+)(?::(\d+))?)?(?:, ack (\d+))?"
                         r"(?:, win (\d+))?(?:, options \[([^\]]*)\])?, length (\d+)", text, re.M):
        t, sa, sp, da, dp, fl, s0, s1, ack, win, opt, ln = m.groups()
        pk.append({"t": float(t), "sport": int(sp), "dport": int(dp), "flags": fl,
                   "seq": int(s0) if s0 else None, "end": int(s1) if s1 else None,
                   "ack": int(ack) if ack else None, "opts": opt or "", "len": int(ln)})
    return pk


def le(a, b):
    return (b - a) % 2**32 < 2**31


def analyse(pk):
    data = [p for p in pk if p["dport"] == PORT and p["len"] > 0]
    acks = [p for p in pk if p["sport"] == PORT and p["ack"] is not None]
    if not data:
        return {"error": "no data captured"}
    rcv_nxt = data[0]["seq"]        # the receiver, simulated from what it got
    held = []                       # out-of-order segments it holds
    ooo = []                        # every out-of-order segment
    reported = []
    last_ooo = None
    misses = checked = max_blocks = 0
    evs = sorted([(p["t"], 0, p) for p in data] + [(p["t"], 1, p) for p in acks], key=lambda x: (x[0], x[1]))
    for t, kind, p in evs:
        if kind == 0:
            s, e = p["seq"], p["end"]
            if le(e, rcv_nxt):
                last_ooo = None                     # a duplicate
            elif le(s, rcv_nxt):
                rcv_nxt = e                         # in order: take what was held
                moved = True
                while moved:
                    moved = False
                    for h in list(held):
                        if le(h[0], rcv_nxt):
                            held.remove(h)
                            if not le(h[1], rcv_nxt):
                                rcv_nxt = h[1]
                            moved = True
                last_ooo = None
            else:
                held.append((s, e))
                ooo.append((s, e))
                last_ooo = (s, e)
        else:
            blocks = [(int(a), int(b)) for a, b in re.findall(r"\{(\d+):(\d+)\}", p["opts"])]
            max_blocks = max(max_blocks, len(blocks))
            reported += blocks
            if last_ooo is not None:
                checked += 1
                if not blocks or not (le(blocks[0][0], last_ooo[0]) and le(last_ooo[1], blocks[0][1])):
                    misses += 1
            last_ooo = None
    never = sum(1 for s, e in ooo if not any(le(a, s) and le(e, b) for a, b in reported))
    # with new data coming in order, the latest segment is the highest: the
    # first block of an ACK with several should be the highest one
    multi = [p for p in acks if len(re.findall(r"\{(\d+):(\d+)\}", p["opts"])) >= 2]
    not_highest = 0
    for p in multi:
        bl = [(int(x), int(y)) for x, y in re.findall(r"\{(\d+):(\d+)\}", p["opts"])]
        if any(le(bl[0][1], o[0]) for o in bl[1:]):
            not_highest += 1
    # how long an out-of-order segment waits for its first SACK
    delays = []
    sacks = [(p["t"], [(int(x), int(y)) for x, y in re.findall(r"\{(\d+):(\d+)\}", p["opts"])]) for p in acks]
    tdel = {}
    for p in data:
        tdel.setdefault((p["seq"], p["end"]), p["t"])
    for s, e in set(ooo):
        t0 = tdel.get((s, e))
        for t, bl in sacks:
            if t >= t0 and any(le(x, s) and le(e, y) for x, y in bl):
                delays.append(t - t0)
                break
    seen, retx = set(), 0
    for p in data:
        if p["seq"] in seen:
            retx += 1
        seen.add(p["seq"])
    delays.sort()
    below = sum(1 for p in acks
                if (lambda bl: bool(bl) and le(bl[0][1], p["ack"]))(
                    [(int(x), int(y)) for x, y in re.findall(r"\{(\d+):(\d+)\}", p["opts"])]))
    return {"first_block_below_ack": below,"multi_block_acks": len(multi), "first_block_not_highest": not_highest,
            "report_delay_median_ms": round(1000 * delays[len(delays) // 2], 1) if delays else None,
            "report_delay_max_ms": round(1000 * delays[-1], 1) if delays else None,
            "acks_after_ooo": checked, "first_block_misses": misses, "max_blocks": max_blocks,
            "ooo_segments": len(ooo), "ooo_segments_never_sacked": never,
            "host_retransmissions_delivered": retx,
            "acks_with_sack": sum(1 for p in acks if "sack" in p["opts"])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", default=os.environ.get("AROS_HOSTED_IMAGE",
        os.path.expanduser("~/aros-build-ipv6-hosted-claude/bin/linux-x86_64/AROS")))
    ap.add_argument("--arostcp")
    ap.add_argument("--out", default=os.path.join(HERE, "out", "rcvsack-" + time.strftime("%Y%m%d-%H%M%S")))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    exe = os.path.join(a.out, "tcpserve")
    subprocess.run([run_tcp.CROSS, "-std=gnu99", "-O2", "-Wall", "-Wno-pointer-sign", "-o", exe,
                    os.path.join(HERE, "tcpserve.c")], check=True, capture_output=True)
    subprocess.run([os.path.join(ROOT, "tools", "tap-up.sh")], check=True, stdout=subprocess.DEVNULL)
    run_tcp.kill_strays()
    shape()
    pcap = os.path.join(a.out, "rcvsack.pcap")
    dump = subprocess.Popen(["sudo", "-n", "tcpdump", "-i", IFACE, "-n", "-s", "128", "-w", pcap,
                             "tcp port %d" % PORT], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1)
    log = {}
    th = threading.Thread(target=sender, args=(log,), daemon=True)
    th.start()
    script = os.path.join(a.out, "rcvsack.script")
    with open(script, "w") as f:
        f.write("Execute SYS:System/Network/AROSTCP/S/startnet\nWait 4\n")
        f.write("C:tcpserve 4 %d recv %d >SYS:out/serve.log\n" % (PORT, BYTES))
    env = dict(os.environ, AROS_HOSTED_IMAGE=a.image, AROS_TAP_IP=run_tcp.AROS_IP, AROS_RUN_TIMEOUT="300")
    if a.arostcp:
        env["AROS_AROSTCP"] = os.path.abspath(a.arostcp)
    r = subprocess.run([os.path.join(ROOT, "tools", "hosted-run.sh"), os.path.join(a.out, "aros"), script, exe],
                       env=env, capture_output=True, text=True)
    th.join(timeout=10)
    time.sleep(1)
    for pid in subprocess.run(["pgrep", "-f", "^tcpdump -i %s -n -s 128 -w %s" % (IFACE, pcap)],
                              capture_output=True, text=True).stdout.split():
        sh("kill", "-INT", pid)
    dump.wait(timeout=10)
    clear()
    text = sh("tcpdump", "-tt", "-nn", "-S", "-v", "-r", pcap).stdout
    open(os.path.join(a.out, "rcvsack.txt"), "w").write(text)
    res = analyse(parse(text))
    res.update(log)
    serve = os.path.join(a.out, "aros", "out", "serve.log")
    res["aros_got"] = open(serve).read().strip() if os.path.exists(serve) else None
    res["boot"] = "ok" if "finished" in r.stdout else "did not finish"
    # the bench checks itself: losses made out-of-order data, the transfer completed
    res["bench_ok"] = res["boot"] == "ok" and res["ooo_segments"] > 0 and \
        bool(res["aros_got"]) and str(BYTES) in res["aros_got"]
    json.dump(res, open(os.path.join(a.out, "result.json"), "w"), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
