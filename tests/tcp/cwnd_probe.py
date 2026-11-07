#!/usr/bin/env python3
"""
cwnd_probe.py - AROS's CUBIC congestion window over time (RFC 9438), on the
wire, as AROS's own TCP_INFO reports it.

AROS (tcpbench cwnd) sends to the host for SECS seconds over IPv6
link-local, without blocking, and prints snd_cwnd and ssthresh every 50 ms.
The host delays its ACKs (netem, DELAY ms) and drops one in EVERY of AROS's
segments (tc gact determ), so losses come at regular intervals and CUBIC's
epochs lie between them.

For each epoch (from a fall of ssthresh to the next) it reports:
  - steps: the share of samples, after the first RTT, in which cwnd did
    not move although below the curve - the curve advancing in 500 ms
    jumps leaves cwnd waiting;
  - err: the median distance between cwnd and RFC 9438's W(t) =
    C*(t-K)^3 + W_max (C 0.4, beta 0.7, K = cbrt(W_max*(1-beta)/C)),
    in segments, while CUBIC is above the Reno-friendly window;
  - the time to get back to W_max, against K.

    cwnd_probe.py [--arostcp FILE] [--image DIR] [--secs 30] [--delay 20] [--every 3000] [--out DIR]
Needs sudo -n for tc.
"""
import argparse, json, os, re, socket, statistics, subprocess, sys, threading, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import run_tcp

PORT = 7201
C, BETA = 0.4, 0.7


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


def epochs(samples, mss):
    """Split the samples at each fall of ssthresh (a loss)."""
    out, cur, last_ss = [], None, None
    for t, cw, ss, rtt in samples:
        if last_ss is not None and ss < last_ss:
            prev = [x for x in samples if x[0] < t]
            wmax = max(x[1] for x in prev[-4:]) if prev else cw
            cur = {"t0": t, "wmax": wmax, "ss": ss, "pts": []}
            out.append(cur)
        last_ss = ss
        if cur is not None:
            cur["pts"].append((t, cw, ss, rtt))
    return out


def analyse(samples, mss):
    res = []
    for e in epochs(samples, mss):
        pts = e["pts"]
        if len(pts) < 10:
            continue
        wmax = e["wmax"] / mss
        k = (wmax * (1 - BETA) / C) ** (1 / 3)
        rtt = statistics.median([p[3] for p in pts]) / 1e6 or 0.001
        steps = still = 0
        errs = []
        back = None
        for i in range(1, len(pts)):
            t = (pts[i][0] - e["t0"]) / 1000
            w = C * (t - k) ** 3 + wmax
            cw = pts[i][1] / mss
            if t > rtt and cw < w:
                steps += 1
                if pts[i][1] == pts[i - 1][1]:
                    still += 1
            if t > rtt:
                errs.append(abs(cw - w))
            if back is None and pts[i][1] >= e["wmax"]:
                back = t
        res.append({"t0_s": e["t0"] / 1000, "wmax_mss": round(wmax, 1), "k_s": round(k, 2),
                    "samples": len(pts), "still_below_curve": round(still / steps, 2) if steps else None,
                    "median_err_mss": round(statistics.median(errs), 1) if errs else None,
                    "back_to_wmax_s": round(back, 2) if back is not None else None})
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", default=os.path.expanduser("~/aros-build-ipv6-hosted-claude/bin/linux-x86_64/AROS"))
    ap.add_argument("--arostcp")
    ap.add_argument("--secs", type=int, default=30)
    ap.add_argument("--delay", type=int, default=20)
    ap.add_argument("--every", type=int, default=3000)
    ap.add_argument("--out", default=os.path.join(ROOT, "tests", "tcp", "out", "cwnd-" + time.strftime("%Y%m%d-%H%M%S")))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    exe = os.path.join(a.out, "tcpbench")
    subprocess.run([run_tcp.CROSS, "-std=gnu99", "-O2", "-Wall", "-Wno-pointer-sign", "-o", exe,
                    os.path.join(HERE, "tcpbench.c")], check=True)
    subprocess.run([os.path.join(ROOT, "tools", "tap-up.sh")], check=True, stdout=subprocess.DEVNULL)
    run_tcp.kill_strays()
    host_ll = None
    for line in subprocess.run(["ip", "-6", "addr", "show", "dev", run_tcp.IFACE], capture_output=True, text=True).stdout.splitlines():
        m = re.search(r"inet6 (fe80::\S+)/", line)
        if m:
            host_ll = m.group(1)
    if host_ll is None:
        sys.exit("no IPv6 link-local address on %s" % run_tcp.IFACE)
    lsock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    lsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    lsock.bind(("::", PORT))
    lsock.listen(2)
    log = []
    threading.Thread(target=sink, args=(lsock, log), daemon=True).start()
    run_tcp.tc_clear()
    run_tcp.tc_delay(a.delay)
    run_tcp.tc_drop(a.every)
    script = os.path.join(a.out, "cwnd.script")
    with open(script, "w") as f:
        f.write("Execute SYS:System/Network/AROSTCP/S/startnet\nWait 4\n")
        f.write("C:tcpbench eth0 %s cwnd %d %d >SYS:out/cwnd.log\n" % (host_ll, PORT, a.secs))
    env = dict(os.environ, AROS_HOSTED_IMAGE=a.image, AROS_TAP_IP=run_tcp.AROS_IP,
               AROS_RUN_TIMEOUT=str(a.secs + 120))
    if a.arostcp:
        env["AROS_AROSTCP"] = os.path.abspath(a.arostcp)
    try:
        r = subprocess.run([os.path.join(ROOT, "tools", "hosted-run.sh"), os.path.join(a.out, "aros"), script, exe],
                           env=env, capture_output=True, text=True)
    finally:
        run_tcp.tc_clear()
    samples, mss = [], 1428
    try:
        for line in open(os.path.join(a.out, "aros", "out", "cwnd.log")):
            p = line.split()
            if len(p) == 6 and p[0] == "cwnd":
                samples.append((int(p[1]), int(p[2]), int(p[3]), int(p[4])))
                mss = int(p[5])
    except OSError:
        pass
    ep = analyse(samples, mss)
    res = {"mss": mss, "delay_ms": a.delay, "every": a.every, "samples": len(samples), "epochs": ep,
           "bytes": sum(log), "boot": "ok" if "finished" in r.stdout else "did not finish",
           # the bench's own check: losses happened, so there are epochs to look at
           "ok": len(ep) >= 2}
    json.dump(res, open(os.path.join(a.out, "result.json"), "w"), indent=1)
    with open(os.path.join(a.out, "cwnd.csv"), "w") as f:
        f.write("ms,cwnd,ssthresh,rtt_us\n")
        for s in samples:
            f.write("%d,%d,%d,%d\n" % s)
    for e in ep:
        print("epoch t0=%6.2fs wmax=%6.1f K=%5.2fs samples=%3d still_below_curve=%s median_err=%s mss back_to_wmax=%s s" % (
            e["t0_s"], e["wmax_mss"], e["k_s"], e["samples"], e["still_below_curve"], e["median_err_mss"], e["back_to_wmax_s"]))
    print("samples=%d bytes=%d ok=%s boot=%s out=%s" % (len(samples), res["bytes"], res["ok"], res["boot"], a.out))


if __name__ == "__main__":
    main()
