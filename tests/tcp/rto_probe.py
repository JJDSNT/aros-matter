#!/usr/bin/env python3
"""
rto_probe.py - AROS's TCP retransmission timeout (RFC 6298) against the
round-trip time, on the wire.

AROS (tcpbench rto) opens REPS connections to the host over IPv6
link-local, one after the other. On each it makes 20 exchanges of 100 bytes
each way, so the RTT estimate settles, waits 0.5 s and sends a 77-byte
tail. The host drops the tail's first copy (tc ingress u32 on the IPv6
payload length; a raw-socket watcher, which sees it before the filter,
takes the filter away at once), so it can only be retransmitted when the
timer fires: the time between the two copies in the capture is the RTO.
No later data, so no duplicate ACKs.

Each delay (netem on what the host sends) is its own boot. For each the
probe reports the RTT seen in the capture, the RTOs, and what RFC 6298 (1 s
minimum, a fine clock) and Linux (200 ms minimum) would use for that RTT,
and the TSval step between the two copies (AROS's own clock: a hosted stall
shows as a step much smaller than the seconds measured).

    rto_probe.py [--arostcp FILE] [--image DIR] [--delays 0,50,200,500] [--reps 8] [--out DIR]
Needs sudo -n for tc, tcpdump and the watcher's raw socket.
"""
import argparse, json, os, re, socket, statistics, struct, subprocess, sys, threading, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import run_tcp

IFACE = run_tcp.IFACE
PORT = 7101
SYN_PORT = 7102                # --syn: the first SYN of each connection dropped
EXCHANGES = 20
TAIL = 77
TS_HDR = 32                    # TCP header with timestamps
PLEN = TS_HDR + TAIL           # the tail's IPv6 payload length


def kill_children(proc, sig):
    """Signal what the sudo of proc runs, by PID (a pattern could match the
    sudo that runs pkill itself)."""
    for pid in subprocess.run(["pgrep", "-P", str(proc.pid)], capture_output=True, text=True).stdout.split():
        subprocess.run(["sudo", "-n", "kill", "-" + sig, pid])
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        subprocess.run(["sudo", "-n", "kill", "-KILL", str(proc.pid)])


def tc(*a):
    return subprocess.run(["sudo", "-n", "tc"] + list(a), capture_output=True, text=True)


class Dropper:
    """The u32 filter that drops the tail; armed per connection."""
    def __init__(self):
        self.lock = threading.Lock()
        self.armed = self.syn_armed = False
        tc("qdisc", "add", "dev", IFACE, "ingress")

    def arm(self):
        with self.lock:
            if not self.armed:
                r = tc("filter", "add", "dev", IFACE, "parent", "ffff:", "protocol", "ipv6", "prio", "1",
                       "u32", "match", "u16", str(PLEN), "0xffff", "at", "4",
                       "match", "u8", "6", "0xff", "at", "6", "action", "drop")
                self.armed = r.returncode == 0

    def disarm(self):
        with self.lock:
            if self.armed:
                tc("filter", "del", "dev", IFACE, "parent", "ffff:", "prio", "1")
                self.armed = False
            if self.syn_armed:
                tc("filter", "del", "dev", IFACE, "parent", "ffff:", "prio", "2")
                self.syn_armed = False

    def arm_syn(self):
        """A SYN (no ACK) to SYN_PORT: TCP flags at 40 + 13."""
        with self.lock:
            if not self.syn_armed:
                r = tc("filter", "add", "dev", IFACE, "parent", "ffff:", "protocol", "ipv6", "prio", "2",
                       "u32", "match", "u8", "6", "0xff", "at", "6",
                       "match", "u16", str(SYN_PORT), "0xffff", "at", "42",
                       "match", "u8", "0x02", "0x12", "at", "53", "action", "drop")
                self.syn_armed = r.returncode == 0


def watch(syn_drops=1):
    """Run as root (--watch): print "tail" and take the filter away each
    time AROS's tail goes by, before the ingress filter sees it. Only an
    ETH_P_ALL socket gets a packet before ingress, as tcpdump does; one for
    ETH_P_IPV6 alone gets it after, so never a dropped one."""
    p = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(0x0003))
    p.bind((IFACE, 0))
    syns = {}                           # SYN copies seen per source port
    while True:
        f, addr = p.recvfrom(2048)
        if addr[2] == socket.PACKET_OUTGOING or len(f) < 14 + 40 + 20 or f[12:14] != b"\x86\xdd":
            continue
        ip = f[14:]
        plen, nh = struct.unpack("!HB", ip[4:7])
        if nh != 6:
            continue
        doff = (ip[40 + 12] >> 4) * 4
        if plen - doff == TAIL and struct.unpack("!H", ip[42:44])[0] == PORT:
            subprocess.run(["tc", "filter", "del", "dev", IFACE, "parent", "ffff:", "prio", "1"],
                           capture_output=True)
            print("tail", flush=True)
        elif struct.unpack("!H", ip[42:44])[0] == SYN_PORT and ip[40 + 13] & 0x12 == 0x02:
            # the first syn_drops copies of each connection's SYN are dropped
            sport = struct.unpack("!H", ip[40:42])[0]
            syns[sport] = syns.get(sport, 0) + 1
            if syns[sport] == syn_drops:
                subprocess.run(["tc", "filter", "del", "dev", IFACE, "parent", "ffff:", "prio", "2"],
                               capture_output=True)
                print("syn", flush=True)


class Watcher(threading.Thread):
    """The root helper; marks the filter gone each time it takes it away."""
    def __init__(self, dropper, syn_drops=1):
        super().__init__(daemon=True)
        self.d = dropper
        self.seen = 0
        self.proc = subprocess.Popen(["sudo", "-n", sys.executable, "-I", os.path.abspath(__file__), "--watch",
                                      "--syn-drops", str(syn_drops)],
                                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        time.sleep(0.5)

    def run(self):
        for line in self.proc.stdout:
            if line.strip() == "tail":
                self.seen += 1
                with self.d.lock:
                    self.d.armed = False
            elif line.strip() == "syn":
                self.seen += 1
                with self.d.lock:
                    self.d.syn_armed = False

    def stop(self):
        kill_children(self.proc, "TERM")


class Server:
    """One listening socket for the whole probe; each boot gets its own
    dropper and log."""
    def __init__(self):
        self.dropper, self.log = None, []
        self.lsock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        self.lsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.lsock.bind(("::", PORT))
        self.lsock.listen(4)
        threading.Thread(target=self.run, daemon=True).start()
        self.ssock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        self.ssock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.ssock.bind(("::", SYN_PORT))
        self.ssock.listen(4)
        threading.Thread(target=self.run_syn, daemon=True).start()

    def run_syn(self):
        """Accept, close, and drop the next connection's first SYN."""
        while True:
            c, _ = self.ssock.accept()
            c.close()
            if self.dropper is not None:
                self.dropper.arm_syn()

    def run(self):
        while True:
            c, _ = self.lsock.accept()
            if self.dropper is None:
                c.close()
                continue
            serve(c, self.dropper, self.log)


def serve(c, dropper, log):
    """One connection: answer each 100-byte request, and the tail with 1 byte."""
    dropper.arm()
    n = 0
    try:
        while True:
            d = c.recv(4096)
            if not d:
                break
            n += len(d)
            if len(d) == 100:
                c.sendall(b"r" * 100)
            elif len(d) == TAIL:
                c.sendall(b"!")
    except OSError as e:
        log.append({"error": str(e)})
    log.append({"bytes": n})
    c.close()


def analyse(pk, delay_ms, jitter_ms=0):
    conns = {}
    for p in pk:
        if p["dport"] == PORT and p["len"] > 0:
            conns.setdefault(p["sport"], {"aros": [], "host": []})["aros"].append(p)
        elif p["sport"] == PORT and p["len"] > 0:
            conns.setdefault(p["dport"], {"aros": [], "host": []})["host"].append(p)
    rows = []
    for sport, c in sorted(conns.items()):
        tails = [p for p in c["aros"] if p["len"] == TAIL]
        reqs = [p for p in c["aros"] if p["len"] == 100]
        reps = c["host"]
        # RTT: AROS's request, then the host's reply as it leaves netem (the
        # capture sees what the host sends after the qdisc, so after the delay)
        rtts = []
        for q in reqs:
            nxt = [r["t"] for r in reps if r["t"] > q["t"]]
            if nxt:
                rtts.append(nxt[0] - q["t"])
        ts = [re.search(r"TS val (\d+)", p["opts"]) for p in tails]
        # nothing but the tail's first copy is dropped: any other copy of
        # data already sent is a spurious retransmission
        seen, spurious = set(), 0
        for q in reqs:
            if q["seq"] in seen:
                spurious += 1
            seen.add(q["seq"])
        row = {"port": sport, "tail_copies": len(tails),
               "rtt_ms": round(1000 * statistics.median(rtts), 1) if rtts else None,
               "rto_s": round(tails[1]["t"] - tails[0]["t"], 3) if len(tails) >= 2 else None,
               "tsval_step": (int(ts[1].group(1)) - int(ts[0].group(1))) if len(ts) >= 2 and ts[0] and ts[1] else None,
               "spurious": spurious + max(0, len(tails) - 2)}
        rows.append(row)
    rtos = [r["rto_s"] for r in rows if r["rto_s"] is not None]
    rtt = statistics.median([r["rtt_ms"] for r in rows if r["rtt_ms"] is not None] or [0]) / 1000
    return {
        "delay_ms": delay_ms, "connections": rows,
        "rto_s": {"min": min(rtos), "median": statistics.median(rtos), "max": max(rtos)} if rtos else None,
        "rtt_s": round(rtt, 3),
        "spurious": sum(r["spurious"] for r in rows),
        "rfc6298_fine_clock_s": round(max(1.0, rtt + 0.004), 3),
        "linux_s": round(rtt + 0.2, 3),
        # the bench's own checks: every tail dropped once, and the RTT seen is
        # the delay set (within 20 ms)
        "ok": bool(rows) and all(r["tail_copies"] >= 2 for r in rows) and abs(rtt * 1000 - delay_ms) < max(20, jitter_ms),
    }


def analyse_syn(pk, drops=1):
    """Per connection to SYN_PORT: the times between copies of its SYN; with
    drops copies dropped, drops intervals, which should double (RFC 6298
    section 5.5: 1, 2, 4 s...)."""
    syns = {}
    for p in pk:
        if p["dport"] == SYN_PORT and "S" in p["flags"] and "." not in p["flags"]:
            syns.setdefault(p["sport"], []).append(p["t"])
    rows = [{"port": sp, "syn_copies": len(t), "rto_s": round(t[1] - t[0], 3) if len(t) >= 2 else None,
             "intervals_s": [round(t[i] - t[i - 1], 3) for i in range(1, len(t))]}
            for sp, t in sorted(syns.items())]
    rtos = [r["rto_s"] for r in rows if r["rto_s"] is not None]
    return {"connections": rows,
            "initial_rto_s": {"min": min(rtos), "median": statistics.median(rtos), "max": max(rtos)} if rtos else None,
            "rfc6298_s": 1.0,
            "ok": bool(rows) and all(r["syn_copies"] == drops + 1 for r in rows)}


def run_one(a, delay, host_ll, exe, server, syn=False):
    out = os.path.join(a.out, "d%d" % delay)
    os.makedirs(out, exist_ok=True)
    run_tcp.tc_clear()
    if delay and a.jitter:
        # normal jitter; one segment in flight at a time, so no reordering
        run_tcp.tc("qdisc", "add", "dev", IFACE, "root", "netem", "delay", "%dms" % delay,
                   "%dms" % a.jitter, "distribution", "normal")
    elif delay:
        run_tcp.tc_delay(delay)
    dropper = Dropper()
    watcher = Watcher(dropper, a.syn_drops)
    watcher.start()
    log = []
    server.dropper, server.log = dropper, log
    if syn:
        dropper.arm_syn()
    try:
        return boot(a, delay, host_ll, exe, out, dropper, watcher, log, syn)
    finally:
        server.dropper = None
        watcher.stop()
        dropper.disarm()
        run_tcp.tc_clear()


def boot(a, delay, host_ll, exe, out, dropper, watcher, log, syn=False):
    pcap = os.path.join(out, "rto.pcap")
    dump = subprocess.Popen(["sudo", "-n", "tcpdump", "-i", IFACE, "-n", "-s", "128", "-w", pcap,
                             "ip6 and (tcp port %d or tcp port %d)" % (PORT, SYN_PORT)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1)
    script = os.path.join(out, "rto.script")
    with open(script, "w") as f:
        f.write("Execute SYS:System/Network/AROSTCP/S/startnet\nWait 4\n")
        if syn:
            f.write("C:tcpbench eth0 %s connect %d %d >SYS:out/rto.log\n" % (host_ll, SYN_PORT, a.reps))
        else:
            f.write("C:tcpbench eth0 %s rto %d %d %d >SYS:out/rto.log\n" % (host_ll, PORT, a.reps, EXCHANGES))
    env = dict(os.environ, AROS_HOSTED_IMAGE=a.image, AROS_TAP_IP=run_tcp.AROS_IP, AROS_RUN_TIMEOUT="600")
    if a.arostcp:
        env["AROS_AROSTCP"] = os.path.abspath(a.arostcp)
    r = subprocess.run([os.path.join(ROOT, "tools", "hosted-run.sh"), os.path.join(out, "aros"), script, exe],
                       env=env, capture_output=True, text=True)
    time.sleep(1)
    kill_children(dump, "INT")
    text = subprocess.run(["sudo", "-n", "tcpdump", "-tt", "-nn", "-S", "-v", "-r", pcap],
                          capture_output=True, text=True).stdout
    text = run_tcp.clock().monotonic(text)    # wall clock -> monotonic (WSL2 steps)
    open(os.path.join(out, "rto.txt"), "w").write(text)
    res = analyse_syn(run_tcp.parse(text), a.syn_drops) if syn else analyse(run_tcp.parse(text), delay, a.jitter)
    res["jitter_ms"] = a.jitter
    res["boot"] = "ok" if "finished" in r.stdout else "did not finish"
    res["tails_seen_by_watcher"] = watcher.seen
    res["host"] = log
    try:
        res["aros"] = open(os.path.join(out, "aros", "out", "rto.log")).read().split("\n")
    except OSError:
        res["aros"] = None
    json.dump(res, open(os.path.join(out, "result.json"), "w"), indent=1)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--watch", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--image", default=os.path.expanduser("~/aros-build-ipv6-hosted-claude/bin/linux-x86_64/AROS"))
    ap.add_argument("--arostcp")
    ap.add_argument("--delays", default="0,50,200,500")
    ap.add_argument("--reps", type=int, default=8)
    ap.add_argument("--jitter", type=int, default=0, help="netem jitter (ms, normal) on top of each delay")
    ap.add_argument("--syn", action="store_true", help="measure the initial RTO instead: drop each first SYN")
    ap.add_argument("--syn-drops", type=int, default=1, help="with --syn: SYN copies dropped per connection")
    ap.add_argument("--out", default=os.path.join(ROOT, "tests", "tcp", "out", "rto-" + time.strftime("%Y%m%d-%H%M%S")))
    a = ap.parse_args()
    run_tcp.clock()                     # sampled from now; the capture's times made monotonic
    if a.watch:
        return watch(a.syn_drops)
    os.makedirs(a.out, exist_ok=True)
    exe = os.path.join(a.out, "tcpbench")
    subprocess.run([run_tcp.CROSS, "-std=gnu99", "-O2", "-Wall", "-Wno-pointer-sign", "-o", exe,
                    os.path.join(HERE, "tcpbench.c")], check=True)
    subprocess.run([os.path.join(ROOT, "tools", "tap-up.sh")], check=True, stdout=subprocess.DEVNULL)
    run_tcp.kill_strays()
    host_ll = None
    for line in subprocess.run(["ip", "-6", "addr", "show", "dev", IFACE], capture_output=True, text=True).stdout.splitlines():
        m = re.search(r"inet6 (fe80::\S+)/", line)
        if m:
            host_ll = m.group(1)
    if host_ll is None:
        sys.exit("no IPv6 link-local address on %s" % IFACE)
    summary = []
    server = Server()
    if a.syn:
        res = run_one(a, 0, host_ll, exe, server, syn=True)
        print("initial RTO (SYN) min/med/max %s s  rfc6298 1.0  ok=%s boot=%s" % (res["initial_rto_s"], res["ok"], res["boot"]))
        for c in res["connections"]:
            print("  SYN intervals %s s" % c["intervals_s"])
        json.dump(res, open(os.path.join(a.out, "summary.json"), "w"), indent=1)
        return
    for d in [int(x) for x in a.delays.split(",")]:
        res = run_one(a, d, host_ll, exe, server)
        s = res["rto_s"] or {}
        print("delay %4d ms jitter %3d  rtt %6.3f s  rto min/med/max %s/%s/%s s  rfc6298 %.3f  linux %.3f  spurious %d  tsval %s  ok=%s boot=%s" % (
            d, a.jitter, res["rtt_s"], s.get("min"), s.get("median"), s.get("max"), res["rfc6298_fine_clock_s"],
            res["linux_s"], res["spurious"], [c["tsval_step"] for c in res["connections"]], res["ok"], res["boot"]))
        summary.append(res)
    json.dump(summary, open(os.path.join(a.out, "summary.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
