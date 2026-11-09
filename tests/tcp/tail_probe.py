#!/usr/bin/env python3
"""
tail_probe.py - how fast AROS's TCP recovers the tail of a burst (RFC 8985
section 7, Tail Loss Probe), on the wire.

AROS (tcpbench bursts) sends N bursts of SIZE bytes, GAP ms apart, to the
host over IPv6 link-local: an application's replies. The host delays what
it sends back (its ACKs) by DELAY ms and, on the tap's ingress, drops once,
from the second burst on, the segment that holds each burst's last byte
(AROS splits a write into segments as it likes, and PSH marks no burst's
end). A watcher (root, AF_PACKET) reads AROS's ISN from its SYN, puts a
group of tc u32 filters per burst - the sequence numbers a segment holding
that byte can start at, in aligned blocks - and takes a group away once
its segment has gone by once. No ACK after the tail tells AROS of the
loss: it learns it from a timer, the RTO (at least 200 ms here) or a loss
probe (about 2 * SRTT).

From a capture (taken before the host's ingress, so it sees the dropped
copies) it reports, for each tail sent more than once, the time from its
first copy to its second; their median and maximum, against SRTT (the
host's echo of the timestamps gives none, so SRTT is DELAY plus the median
time AROS took to see the ACKs of the bursts before); and the transfer's
seconds.

    tail_probe.py [--arostcp FILE] [--image DIR] [--bursts 20] [--size 10000]
                  [--gap 300] [--delay 20] [--out DIR]
Needs sudo -n for tc and tcpdump.
"""
import argparse, json, os, re, socket, statistics, struct, subprocess, sys, threading, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import run_tcp

PORT = 7601
IFACE = run_tcp.IFACE


def sh(*a):
    return subprocess.run(["sudo", "-n"] + list(a), capture_output=True, text=True)


MSS = 1428


def blocks(lo, hi):
    """[lo, hi] (mod 2**32) as aligned (value, mask) blocks, for u32."""
    out = []
    lo %= 2**32
    n = (hi - lo) % 2**32 + 1
    while n > 0:
        size = lo & -lo if lo else 2**32
        while size > n:
            size //= 2
        out.append((lo, (2**32 - size) & 0xffffffff))
        lo = (lo + size) % 2**32
        n -= size
    return out


def watch(port, nbursts, size, result):
    """As root: the ISN from AROS's SYN to port; then, for bursts 1..N-1,
    a filter group (prio 100+i) dropping a segment that starts within MSS
    before the burst's end; the group goes once such a segment has been
    seen (dropped) once."""
    p = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(0x0003))
    p.bind((IFACE, 0))
    p.settimeout(1)
    isn, pending, rec = None, {}, {"dropped": []}
    end = time.time() + 280
    while time.time() < end and (isn is None or pending):
        try:
            f, where = p.recvfrom(4096)
        except socket.timeout:
            continue
        if where[2] == socket.PACKET_OUTGOING or f[12:14] != b"\x86\xdd" or f[14 + 6] != 6:
            continue
        t = f[54:]
        dport, seq = struct.unpack("!HI", t[2:8])
        if dport != port:
            continue
        if t[13] & 0x02 and isn is None:          # SYN
            isn = seq
            rec["isn"] = isn
            for i in range(1, nbursts):
                b = (isn + 1 + (i + 1) * size) % 2**32
                lo, hi = (b - MSS) % 2**32, (b - 1) % 2**32
                for v, m in blocks(lo, hi):
                    r = subprocess.run(["tc", "filter", "add", "dev", IFACE, "parent", "ffff:", "protocol", "ipv6",
                                        "prio", str(100 + i), "u32", "match", "ip6", "dport", str(port), "0xffff",
                                        "match", "u32", "%#x" % v, "%#x" % m, "at", "44", "action", "gact", "drop"],
                                       capture_output=True, text=True)
                    if r.returncode:
                        rec.setdefault("errors", []).append(r.stderr.strip()[:200])
                pending[i] = (lo, hi)
            continue
        for i, (lo, hi) in list(pending.items()):
            if (seq - lo) % 2**32 <= (hi - lo) % 2**32:
                subprocess.run(["tc", "filter", "del", "dev", IFACE, "parent", "ffff:", "protocol", "ipv6",
                                "prio", str(100 + i)], capture_output=True)
                rec["dropped"].append({"burst": i, "seq": seq, "t": time.time()})
                del pending[i]
    rec["left"] = sorted(pending)
    with open(result, "w") as fo:
        json.dump(rec, fo)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", default=os.path.expanduser("~/aros-build-ipv6-hosted-claude/bin/linux-x86_64/AROS"))
    ap.add_argument("--arostcp")
    ap.add_argument("--bursts", type=int, default=20)
    ap.add_argument("--size", type=int, default=10000)
    ap.add_argument("--gap", type=int, default=300)
    ap.add_argument("--delay", type=int, default=20)
    ap.add_argument("--out", default=os.path.join(HERE, "out", "tail-" + time.strftime("%Y%m%d-%H%M%S")))
    ap.add_argument("--watch", nargs=4, help=argparse.SUPPRESS)
    a = ap.parse_args()
    if a.watch:
        return watch(int(a.watch[0]), int(a.watch[1]), int(a.watch[2]), a.watch[3])
    run_tcp.clock()
    os.makedirs(a.out, exist_ok=True)
    exe = os.path.join(a.out, "tcpbench")
    subprocess.run([run_tcp.CROSS, "-std=gnu99", "-O2", "-Wall", "-Wno-pointer-sign", "-o", exe,
                    os.path.join(HERE, "tcpbench.c")], check=True)
    subprocess.run([os.path.join(ROOT, "tools", "tap-up.sh")], check=True, stdout=subprocess.DEVNULL)
    run_tcp.kill_strays()
    run_tcp.tc_clear()
    host_ll = re.findall(r"inet6 (fe80::[0-9a-f:]+)/", subprocess.run(
        ["ip", "-6", "addr", "show", "dev", IFACE], capture_output=True, text=True).stdout)[0]
    lsock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    lsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    lsock.bind(("::", PORT))
    lsock.listen(2)
    got = []

    def serve():
        while True:
            c, _ = lsock.accept()
            n = 0
            c.settimeout(60)
            try:
                while True:
                    d = c.recv(65536)
                    if not d:
                        break
                    n += len(d)
            except OSError:
                pass
            got.append(n)
            c.close()

    threading.Thread(target=serve, daemon=True).start()
    run_tcp.tc_delay(a.delay)
    sh("tc", "qdisc", "add", "dev", IFACE, "ingress")
    w = subprocess.Popen(["sudo", "-n", sys.executable, "-I", os.path.abspath(__file__), "--watch",
                          str(PORT), str(a.bursts), str(a.size), os.path.join(a.out, "watch.json")])
    pcap = os.path.join(a.out, "tail.pcap")
    dump = subprocess.Popen(["sudo", "-n", "tcpdump", "-i", IFACE, "-n", "-s", "128", "-w", pcap,
                             "ip6 and tcp port %d" % PORT], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1)
    script = os.path.join(a.out, "tail.script")
    with open(script, "w") as f:
        f.write("Execute SYS:System/Network/AROSTCP/S/startnet\nWait 4\n")
        f.write("C:tcpbench eth0 %s bursts %d %d %d %d >SYS:out/bursts.log\n" % (host_ll, PORT, a.bursts, a.size, a.gap))
    env = dict(os.environ, AROS_HOSTED_IMAGE=a.image, AROS_TAP_IP=run_tcp.AROS_IP, AROS_RUN_TIMEOUT="300")
    if a.arostcp:
        env["AROS_AROSTCP"] = os.path.abspath(a.arostcp)
    try:
        r = subprocess.run([os.path.join(ROOT, "tools", "hosted-run.sh"), os.path.join(a.out, "aros"), script, exe],
                           env=env, capture_output=True, text=True)
    finally:
        time.sleep(1)
        for pid in subprocess.run(["pgrep", "-P", str(dump.pid)], capture_output=True, text=True).stdout.split():
            sh("kill", "-INT", pid)
        dump.wait(timeout=10)
        try:
            w.wait(timeout=10)
        except subprocess.TimeoutExpired:
            sh("kill", str(w.pid))
        sh("tc", "qdisc", "del", "dev", IFACE, "ingress")
        run_tcp.tc_clear()
    text = subprocess.run(["sudo", "-n", "tcpdump", "-tt", "-nn", "-S", "-r", pcap], capture_output=True, text=True).stdout
    text = run_tcp.clock().monotonic(text)
    first, copies, data, acks = {}, {}, [], []
    for line in text.splitlines():
        m = re.match(r"(\d+\.\d+) IP6 (\S+)\.(\d+) > (\S+)\.(\d+): Flags \[([^\]]*)\](.*)", line)
        if not m:
            continue
        t, flags, rest = float(m.group(1)), m.group(6), m.group(7)
        if int(m.group(5)) == PORT:
            ms = re.search(r"seq (\d+):(\d+)", rest)
            if ms:
                seq = int(ms.group(1))
                data.append((t, seq, int(ms.group(2)), "P" in flags))
                copies.setdefault(seq, []).append(t)
        elif int(m.group(3)) == PORT:
            ma = re.search(r"ack (\d+)", rest)
            if ma:
                acks.append((t, int(ma.group(1))))
    tails = []
    for seq, ts in sorted(copies.items(), key=lambda x: x[1][0]):
        if len(ts) > 1:
            tails.append({"seq": seq, "copies": len(ts), "recovery_ms": round((ts[1] - ts[0]) * 1000, 1)})
    rec = [x["recovery_ms"] for x in tails]
    # SRTT as AROS saw it: from each burst's last segment to the host's ACK
    # of it, for the bursts that lost nothing
    rtts = []
    for t, seq, end, psh in data:
        if len(copies.get(seq, [])) == 1:
            later = [ta for ta, ack in acks if ta >= t and (ack - end) % 2**32 < 2**31]
            if later:
                rtts.append((later[0] - t) * 1000)
    span = data[-1][0] - data[0][0] if data else None
    try:
        wj = json.load(open(os.path.join(a.out, "watch.json")))
    except (OSError, ValueError):
        wj = {}
    # a resent segment is a tail if it ends where a burst does
    isn = wj.get("isn")
    ends = {(isn + 1 + (i + 1) * a.size) % 2**32 for i in range(a.bursts)} if isn is not None else set()
    seg_end = {seq: end for t, seq, end, psh in data}
    for x in tails:
        x["tail"] = seg_end.get(x["seq"]) in ends
    rec = [x["recovery_ms"] for x in tails if x["tail"]]
    res = {"bursts": a.bursts, "size": a.size, "gap_ms": a.gap, "delay_ms": a.delay,
           "watch_errors": wj.get("errors"), "watch_dropped": len(wj.get("dropped", [])),
           "tails_resent": len(rec), "other_resent": sum(1 for x in tails if not x["tail"]), "recovery_ms": rec,
           "recovery_median_ms": statistics.median(rec) if rec else None, "recovery_max_ms": max(rec) if rec else None,
           "rtt_median_ms": round(statistics.median(rtts), 1) if rtts else None,
           "sent_3_or_more": sum(1 for x in tails if x["copies"] >= 3),
           "seconds": round(span, 3) if span else None, "host_bytes": got,
           "boot": "ok" if "finished" in r.stdout else "did not finish"}
    # the bench's own checks: the filter took, tails were lost and resent,
    # and every byte arrived
    res["ok"] = not wj.get("errors") and len(rec) >= a.bursts // 2 and got == [a.bursts * a.size]
    json.dump(res, open(os.path.join(a.out, "result.json"), "w"), indent=1)
    print(json.dumps({k: v for k, v in res.items() if k != "recovery_ms"}, indent=1))


if __name__ == "__main__":
    main()
