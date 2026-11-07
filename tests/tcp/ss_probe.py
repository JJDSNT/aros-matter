#!/usr/bin/env python3
"""
ss_probe.py - how AROS's first slow start ends (HyStart++, RFC 9406), on the
wire, behind a bottleneck.

AROS (tcpbench cwnd) sends to the host for SECS seconds over IPv6
link-local and prints TCP_INFO's snd_cwnd and ssthresh every 50 ms. On the
host, what AROS sends goes through an ifb with a token bucket (RATE Mbit/s,
a queue of QUEUE KB): slow start fills the queue, the RTT grows, and when
the queue overflows segments are lost. The host delays its ACKs DELAY ms.
Before sending, AROS sets the sysctls of the mode (tests/tcp/tcpctl.c),
e.g. "abc1:15=1" (net.inet.tcp leaf 15 to 1): an A/B in one binary, one
boot each.

For each it reports from the samples and a capture: when the first slow
start ended (ssthresh leaves its initial value) and how - by HyStart++
(no retransmission before it) or by a loss; cwnd there; the segments lost
then (the token bucket's drops, and AROS's retransmissions in the first
seconds); and the bytes delivered.

    ss_probe.py [--arostcp FILE] [--image DIR] [--rate 20] [--queue 64] [--delay 20] [--secs 10] [--out DIR]
Needs sudo -n for tc, ip and tcpdump.
"""
import argparse, json, os, re, socket, subprocess, sys, threading, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import run_tcp

IFACE = run_tcp.IFACE
IFB = "ifbss"
PORT = 7301
INITIAL_SSTHRESH = 65535 << 14


def sh(*a):
    return subprocess.run(["sudo", "-n"] + list(a), capture_output=True, text=True)


def clear():
    sh("tc", "qdisc", "del", "dev", IFACE, "ingress")
    sh("tc", "qdisc", "del", "dev", IFACE, "root")
    sh("ip", "link", "del", IFB)


def shape(a):
    clear()
    sh("tc", "qdisc", "add", "dev", IFACE, "root", "netem", "delay", "%dms" % a.delay)
    sh("ip", "link", "add", IFB, "type", "ifb")
    sh("ip", "link", "set", IFB, "up")
    if a.rate == 0:                     # no bottleneck: delay only
        sh("tc", "qdisc", "add", "dev", IFB, "root", "pfifo", "limit", "10000")
    else:
        sh("tc", "qdisc", "add", "dev", IFB, "root", "tbf", "rate", "%dmbit" % a.rate,
           "burst", "3000", "limit", str(a.queue * 1024))
    sh("tc", "qdisc", "add", "dev", IFACE, "ingress")
    sh("tc", "filter", "add", "dev", IFACE, "parent", "ffff:", "protocol", "ipv6", "matchall",
       "action", "mirred", "egress", "redirect", "dev", IFB)


def sink(lsock, log):
    """Read every connection to the end, each in its own thread: one from
    an earlier boot never gets its FIN (the machine is stopped), and a
    single reader stuck on it would shut the window of the next one."""
    def drain(c):
        try:
            c.settimeout(5)
            while True:
                d = c.recv(65536)
                if not d:
                    break
                log.append(len(d))
        except OSError:
            pass
        c.close()

    while True:
        c, _ = lsock.accept()
        threading.Thread(target=drain, args=(c,), daemon=True).start()


def analyse_capture(text):
    """From a capture of both directions: AROS's retransmissions, an RTT per
    ACK (the newest segment it covers, first sent once: Karn), and the
    throughput in 100 ms bins from the ACKs; times from the first data."""
    sent, retx, rtts, t0 = {}, [], [], None
    acked0 = last_ack = None
    bins = {}
    for line in text.splitlines():
        mm = re.match(r"(\d+\.\d+) IP6 (\S+)\.(\d+) > (\S+)\.(\d+): Flags \[([^\]]*)\](.*)", line)
        if not mm:
            continue
        t, sport, rest = float(mm.group(1)), int(mm.group(3)), mm.group(7)
        if int(mm.group(5)) == PORT:                     # AROS's data
            ms = re.search(r"seq (\d+):(\d+)", rest)
            if not ms:
                continue
            if t0 is None:
                t0 = t
            s0, s1 = int(ms.group(1)), int(ms.group(2))
            if s1 in sent:
                sent[s1] = None                          # resent: no sample
                retx.append(t - t0)
            else:
                sent[s1] = t
        elif sport == PORT and t0 is not None:           # the host's ACKs
            ma = re.search(r"ack (\d+)", rest)
            if not ma:
                continue
            ack = int(ma.group(1))
            if acked0 is None:
                acked0 = last_ack = ack
            adv = (ack - last_ack) & 0xffffffff
            if 0 < adv < 1 << 31:                        # forward, modulo 2^32
                b = int((t - t0) * 10)
                bins[b] = bins.get(b, 0) + adv
                ts = sent.get(ack)
                if ts:
                    rtts.append((t - t0, (t - ts) * 1000))
                last_ack = ack
    mbit = [round(bins.get(i, 0) * 8 / 0.1 / 1e6, 1) for i in range(max(bins) + 1)] if bins else []
    steady = None
    if len(mbit) > 20:
        tail = sorted(mbit[-50:])[len(mbit[-50:]) // 2]
        for i in range(len(mbit)):
            if all(x >= 0.9 * tail for x in mbit[i:i + 5]):
                steady = i / 10
                break
    return {"retx": retx, "rtts": rtts, "mbit": mbit, "steady_s": steady,
            "min_rtt_ms": round(min(r for t, r in rtts), 1) if rtts else None}


def run(a, mode, host_ll, exes, log, rep=0):
    name, _, sets = mode.partition(":")
    out = os.path.join(a.out, "%s-%d" % (name, rep))
    os.makedirs(out, exist_ok=True)
    shape(a)
    pcap = os.path.join(out, "ss.pcap")
    dump = subprocess.Popen(["sudo", "-n", "tcpdump", "-i", IFACE, "-n", "-s", "96", "-w", pcap,
                             "ip6 and tcp port %d" % PORT], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1)
    script = os.path.join(out, "ss.script")
    with open(script, "w") as f:
        f.write("Execute SYS:System/Network/AROSTCP/S/startnet\nWait 4\n")
        if a.ssthresh:          # the link route's ssthresh (rtssthresh.c)
            f.write("C:rtssthresh eth0 %d %s >>SYS:out/tcpctl.log\n" % (a.ssthresh, host_ll))
        for kv in filter(None, sets.split(";")):
            leaf, val = kv.split("=")
            f.write("C:tcpctl %s %s >>SYS:out/tcpctl.log\n" % (leaf, val))
        f.write("C:tcpbench eth0 %s cwnd %d %d >SYS:out/cwnd.log\n" % (host_ll, PORT, a.secs))
    env = dict(os.environ, AROS_HOSTED_IMAGE=a.image, AROS_TAP_IP=run_tcp.AROS_IP,
               AROS_RUN_TIMEOUT=str(a.secs + 120))
    if a.arostcp:
        env["AROS_AROSTCP"] = os.path.abspath(a.arostcp)
    n0 = len(log)
    try:
        r = subprocess.run([os.path.join(ROOT, "tools", "hosted-run.sh"), os.path.join(out, "aros"), script] + exes,
                           env=env, capture_output=True, text=True)
    finally:
        stats = sh("tc", "-s", "qdisc", "show", "dev", IFB).stdout
        for pid in subprocess.run(["pgrep", "-P", str(dump.pid)], capture_output=True, text=True).stdout.split():
            sh("kill", "-INT", pid)
        dump.wait(timeout=10)
        clear()
    m = re.search(r"dropped (\d+)", stats)
    drops = int(m.group(1)) if m else None
    text = subprocess.run(["sudo", "-n", "tcpdump", "-tt", "-nn", "-S", "-r", pcap], capture_output=True, text=True).stdout
    cap = analyse_capture(text)
    retx = cap["retx"]
    samples, mss = [], 1428
    try:
        for line in open(os.path.join(out, "aros", "out", "cwnd.log")):
            p = line.split()
            if len(p) == 6 and p[0] == "cwnd":
                samples.append((int(p[1]), int(p[2]), int(p[3]), int(p[4])))
                mss = int(p[5])
    except OSError:
        pass
    exit_s = exit_cwnd = exit_ss = None
    for t, cw, ss, rtt in samples:
        if ss < INITIAL_SSTHRESH - mss:
            exit_s, exit_cwnd, exit_ss = t / 1000, cw // mss, ss // mss
            break
    first_retx = retx[0] if retx else None
    how = None
    if exit_s is not None:
        how = "loss" if first_retx is not None and first_retx <= exit_s + 0.1 else "hystart"
    res = {"mode": mode, "rate_mbit": a.rate, "queue_kb": a.queue, "delay_ms": a.delay,
           "exit_s": exit_s, "exit_how": how, "exit_cwnd_mss": exit_cwnd, "exit_ssthresh_mss": exit_ss,
           "max_cwnd_mss": max((s[1] for s in samples), default=0) // mss,
           "tbf_drops": drops, "retransmissions": len(retx),
           "retransmissions_first_3s": sum(1 for x in retx if x < 3), "first_retx_s": first_retx,
           "bytes": sum(log[n0:]), "samples": len(samples),
           "min_rtt_ms": cap["min_rtt_ms"], "max_rtt_ss_ms": None, "rtt_at_exit_ms": None,
           "steady_s": cap["steady_s"], "mbit_per_100ms": cap["mbit"],
           "boot": "ok" if "finished" in r.stdout else "did not finish"}
    # how congestion avoidance grows cwnd in the 5 s after it begins (cwnd
    # at a non-initial ssthresh; with --ssthresh that is after slow start
    # climbed to the route's value, not at t = 0)
    ca0 = next((t for t, cw, ss, rtt in samples if ss < INITIAL_SSTHRESH - mss and cw >= ss), None)
    if ca0 is not None:
        after = [cw for t, cw, ss, rtt in samples if ca0 <= t <= ca0 + 5000]
        res["ca_start_s"] = ca0 / 1000
        res["ca_growth_5s_mss"] = (after[-1] - after[0]) // mss
    # RTT inflation during the first slow start, and at its end
    if exit_s is not None:
        ss_rtts = [r for t, r in cap["rtts"] if t <= exit_s]
        if ss_rtts:
            res["max_rtt_ss_ms"] = round(max(ss_rtts), 1)
        near = [r for t, r in cap["rtts"] if abs(t - exit_s) < 0.05]
        if near:
            res["rtt_at_exit_ms"] = round(sorted(near)[len(near) // 2], 1)
    # the bench's own checks: there were RTT samples, and the slow start
    # ended within the run (a congestion-free run may never end it: then
    # only the samples)
    res["ok"] = bool(cap["rtts"]) and (exit_s is not None or a.rate == 0)
    json.dump(res, open(os.path.join(out, "result.json"), "w"), indent=1)
    with open(os.path.join(out, "cwnd.csv"), "w") as f:
        f.write("ms,cwnd,ssthresh,rtt_us\n")
        for s in samples:
            f.write("%d,%d,%d,%d\n" % s)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", default=os.path.expanduser("~/aros-build-ipv6-hosted-claude/bin/linux-x86_64/AROS"))
    ap.add_argument("--arostcp")
    ap.add_argument("--rate", type=int, default=20)
    ap.add_argument("--queue", type=int, default=64)
    ap.add_argument("--delay", type=int, default=20)
    ap.add_argument("--secs", type=int, default=10)
    ap.add_argument("--ssthresh", type=int, default=0,
                    help="set the link route's ssthresh (bytes) before connecting: slow start ends there, without a loss")
    ap.add_argument("--modes", default="abc1:15=1,abc2:15=2",
                    help="name:leaf=value;leaf=value,... (net.inet.tcp leaves, set before sending)")
    ap.add_argument("--out", default=os.path.join(ROOT, "tests", "tcp", "out", "ss-" + time.strftime("%Y%m%d-%H%M%S")))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    exes = []
    for src in ("tcpbench", "tcpctl", "rtssthresh"):
        exe = os.path.join(a.out, src)
        subprocess.run([run_tcp.CROSS, "-std=gnu99", "-O2", "-Wall", "-Wno-pointer-sign", "-o", exe,
                        os.path.join(HERE, src + ".c")], check=True)
        exes.append(exe)
    subprocess.run([os.path.join(ROOT, "tools", "tap-up.sh")], check=True, stdout=subprocess.DEVNULL)
    run_tcp.kill_strays()
    host_ll = None
    for line in subprocess.run(["ip", "-6", "addr", "show", "dev", IFACE], capture_output=True, text=True).stdout.splitlines():
        m = re.search(r"inet6 (fe80::\S+)/", line)
        if m:
            host_ll = m.group(1)
    if host_ll is None:
        sys.exit("no IPv6 link-local address on %s" % IFACE)
    lsock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    lsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    lsock.bind(("::", PORT))
    lsock.listen(2)
    log = []
    threading.Thread(target=sink, args=(lsock, log), daemon=True).start()
    results = []
    for i, h in enumerate(a.modes.split(",")):
        res = run(a, h, host_ll, exes, log, i)
        time.sleep(1)
        print("%-12s exit=%s s by %s cwnd=%s ssthresh=%s max_cwnd=%s drops=%s retx=%d minrtt=%s maxrtt_ss=%s rtt_exit=%s steady=%s s ca_growth_5s=%s bytes=%d ok=%s boot=%s" % (
            h, res["exit_s"], res["exit_how"], res["exit_cwnd_mss"], res["exit_ssthresh_mss"], res["max_cwnd_mss"],
            res["tbf_drops"], res["retransmissions"], res["min_rtt_ms"], res["max_rtt_ss_ms"], res["rtt_at_exit_ms"],
            res["steady_s"], res.get("ca_growth_5s_mss"), res["bytes"], res["ok"], res["boot"]))
        results.append(res)
    json.dump(results, open(os.path.join(a.out, "summary.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
