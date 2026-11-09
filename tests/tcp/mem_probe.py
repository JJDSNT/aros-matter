#!/usr/bin/env python3
"""
mem_probe.py - socket buffer autosizing under memory pressure: N
connections receiving at once, and what they take of AROS's mbuf cluster
pool (mbconf.maxmem).

AROS listens on N ports (tcpserve 4 PORT recv, all but the last with Run);
the host connects to all of them, then sends BYTES on each at once, with
netem DELAY ms (and an optional link RATE) on what it sends. The pool
running out shows in AROS's log ("m_clalloc: max amount of memory already
used"; packets are then lost for every connection), counted here; AROS runs
"netstat -s" after, for where segments were dropped, and "netstat -m"
(needs netstat with AROS commit 18b3ca3227; the pool is never given back,
so "taken from the system" is the peak). It reports the
aggregate and per-connection throughput and the host's retransmissions.

    mem_probe.py [--arostcp FILE] [--image DIR] [--conns 8] [--bytes 8000000]
                 [--delay 100] [--rate R] [--out DIR]
Needs sudo -n for tc.
"""
import argparse, json, os, re, socket, subprocess, sys, threading, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import run_tcp

PORT = 7500


def retransmissions():
    out = subprocess.run(["nstat", "-az", "TcpRetransSegs"], capture_output=True, text=True).stdout
    m = re.search(r"TcpRetransSegs\s+(\d+)", out)
    return int(m.group(1)) if m else 0


def netstat_s(path):
    """The drop counters of AROS's netstat -s that are not 0."""
    try:
        text = open(path, errors="replace").read()
    except OSError:
        return None
    keep = {}
    for line in text.splitlines():
        m = re.match(r"\s*(\d+) (.*)", line)
        if m and int(m.group(1)) and re.search(r"drop|discard|after window|out-of-order|duplicate|full|no buffer|overflow|denied", m.group(2)):
            keep[m.group(2)] = int(m.group(1))
    return keep


def netstat_m(path):
    """AROS's netstat -m, as lines (None if it did not run)."""
    try:
        return [l.strip() for l in open(path, errors="replace") if l.strip()] or None
    except OSError:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", default=os.path.expanduser("~/aros-build-ipv6-hosted-claude/bin/linux-x86_64/AROS"))
    ap.add_argument("--arostcp")
    ap.add_argument("--conns", type=int, default=8)
    ap.add_argument("--bytes", type=int, default=8000000)
    ap.add_argument("--delay", type=int, default=100)
    ap.add_argument("--rate")
    ap.add_argument("--out", default=os.path.join(ROOT, "tests", "tcp", "out", "mem-" + time.strftime("%Y%m%d-%H%M%S")))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    exe = os.path.join(a.out, "tcpserve")
    subprocess.run([run_tcp.CROSS, "-std=gnu99", "-O2", "-Wall", "-Wno-pointer-sign", "-o", exe,
                    os.path.join(HERE, "tcpserve.c")], check=True)
    subprocess.run([os.path.join(ROOT, "tools", "tap-up.sh")], check=True, stdout=subprocess.DEVNULL)
    run_tcp.kill_strays()
    run_tcp.tc_clear()
    run_tcp.tc_delay(a.delay, a.rate)
    script = os.path.join(a.out, "mem.script")
    with open(script, "w") as f:
        f.write("Execute SYS:System/Network/AROSTCP/S/startnet\nWait 4\n")
        for i in range(a.conns - 1):
            f.write("Run >NIL: C:tcpserve 4 %d recv 0 >SYS:out/serve%d.log\n" % (PORT + i, i))
        f.write("C:tcpserve 4 %d recv 0 >SYS:out/serve%d.log\n" % (PORT + a.conns - 1, a.conns - 1))
        f.write("Wait 5\nC:netstat -s >SYS:out/netstat-s.log\nC:netstat -m >SYS:out/netstat-m.log\n")
    env = dict(os.environ, AROS_HOSTED_IMAGE=a.image, AROS_TAP_IP=run_tcp.AROS_IP, AROS_RUN_TIMEOUT="300")
    if a.arostcp:
        env["AROS_AROSTCP"] = os.path.abspath(a.arostcp)
    boot = subprocess.Popen([os.path.join(ROOT, "tools", "hosted-run.sh"), os.path.join(a.out, "aros"), script, exe],
                            env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    socks, err = [], None
    deadline = time.time() + 90
    for i in range(a.conns):
        while True:
            try:
                socks.append(socket.create_connection((run_tcp.AROS_IP, PORT + i), timeout=2))
                break
            except OSError:
                if time.time() > deadline:
                    err = "no connection to port %d" % (PORT + i)
                    break
                time.sleep(0.5)
        if err:
            break
    took = [None] * len(socks)
    rx0 = retransmissions()

    def send(i, c):
        chunk, sent, t0 = b"d" * 65536, 0, time.monotonic()
        try:
            while sent < a.bytes:
                c.sendall(chunk)
                sent += len(chunk)
            c.shutdown(socket.SHUT_WR)
            c.settimeout(30)
            while c.recv(4096):
                pass
            took[i] = time.monotonic() - t0
        except OSError:
            pass
        c.close()

    t0 = time.monotonic()
    threads = [threading.Thread(target=send, args=(i, c)) for i, c in enumerate(socks)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    span = time.monotonic() - t0
    retx = retransmissions() - rx0
    out_text = boot.communicate()[0]
    run_tcp.tc_clear()
    per = [round(a.bytes * 8 / t / 1e6, 1) if t else None for t in took]
    try:
        pool_full = open(os.path.join(a.out, "aros", "serial.log"), errors="replace").read().count("max amount of memory")
    except OSError:
        pool_full = None
    res = {"conns": a.conns, "bytes_each": a.bytes, "delay_ms": a.delay, "rate": a.rate, "error": err,
           "aggregate_mbit": round(a.bytes * len(socks) * 8 / span / 1e6, 1) if socks else None,
           "per_conn_mbit": per, "host_retransmissions": retx, "pool_full_msgs": pool_full,
           "aros_drops": netstat_s(os.path.join(a.out, "aros", "out", "netstat-s.log")),
           "netstat_m": netstat_m(os.path.join(a.out, "aros", "out", "netstat-m.log")),
           "boot": "ok" if "finished" in out_text else "did not finish"}
    # the bench's own checks: every connection finished, and AROS reported its counters
    res["ok"] = err is None and all(per) and res["aros_drops"] is not None
    json.dump(res, open(os.path.join(a.out, "result.json"), "w"), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
