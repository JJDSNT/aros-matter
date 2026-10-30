#!/usr/bin/env python3
"""TCP on the wire: AROS (tcpbench.c) against the Linux host over the tap.

What it measures: the TCP behaviour AROS shows to a real peer - the options
in its SYN, its ephemeral ports and ISNs, how it recovers from loss (does it
use SACK, how many retransmissions per loss, how many timeouts), whether it
resets a connection closed with unread data, and its retransmission timeout
when nothing comes back. What it does not measure: absolute performance
(hosted AROS is no real machine).

The host shapes the link with tc on the tap: an ingress gact filter drops
packets from AROS (1 in N, or all), a root netem adds delay to what the host
sends. The capture is taken before the ingress filter, so dropped packets
and their retransmissions are both seen.

Usage: tests/tcp/run_tcp.py [--arostcp BIN] [--out DIR]
"""
import argparse, os, re, socket, subprocess, sys, threading, time, json

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
CROSS = os.environ.get("AROS_CROSS",
    os.path.expanduser("~/aros-midihub/build-aros-linux/bin/linux-x86_64/tools/crosstools/x86_64-aros-gcc"))
IFACE = "aros0"
AROS_IP = "192.168.166.2"
SEND_BYTES = 2000000
LOSS_EVERY = 50          # drop 1 in 50 packets from AROS during "send"
DELAY_MS = 10            # added to what the host sends during "send"
STALL_S = 8              # everything from AROS dropped for this long during "stall"


SHAPE = True


def tc(*args):
    if not SHAPE and args and args[0] in ("filter",) or (not SHAPE and len(args) > 4 and args[4] in ("root", "ingress") and args[1] == "add"):
        return
    subprocess.run(["sudo", "-n", "tc"] + list(args), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def tc_clear():
    tc("qdisc", "del", "dev", IFACE, "ingress")
    tc("qdisc", "del", "dev", IFACE, "root")


def tc_drop(every):
    """Drop 1 in every packets (every=1: all) arriving from AROS."""
    tc("qdisc", "add", "dev", IFACE, "ingress")
    act = ["action", "gact", "drop"] if every == 1 else \
          ["action", "gact", "pass", "random", "determ", "drop", str(every)]
    tc("filter", "add", "dev", IFACE, "parent", "ffff:", "protocol", "ipv6", "matchall", *act)


def tc_delay(ms):
    tc("qdisc", "add", "dev", IFACE, "root", "netem", "delay", "%dms" % ms)


class Listeners(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.log = {}
        self.socks = {}
        for port in (7001, 7002, 7003, 7004):
            s = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("::", port))
            s.listen(16)
            self.socks[port] = s
            threading.Thread(target=self.serve, args=(port, s), daemon=True).start()

    def serve(self, port, s):
        while True:
            c, peer = s.accept()
            threading.Thread(target=self.handle, args=(port, c), daemon=True).start()

    def handle(self, port, c):
        ev = self.log.setdefault(port, [])
        t0 = time.time()
        try:
            if port == 7002:
                tc_drop(LOSS_EVERY)
                tc_delay(DELAY_MS)
                n = 0
                while True:
                    d = c.recv(65536)
                    if not d:
                        break
                    n += len(d)
                tc_clear()
                ev.append({"bytes": n, "seconds": round(time.time() - t0, 3)})
            elif port == 7003:
                c.sendall(b"u" * 4000)
                try:
                    d = c.recv(100)
                    ev.append({"after_close": "FIN" if d == b"" else "data"})
                except ConnectionResetError:
                    ev.append({"after_close": "RST"})
            elif port == 7004:
                time.sleep(1.0)
                tc_drop(1)
                time.sleep(STALL_S)
                tc_clear()
                n = 0
                while True:
                    d = c.recv(4096)
                    if not d:
                        break
                    n += len(d)
                ev.append({"bytes": n})
            else:
                while c.recv(4096):
                    pass
                ev.append({"ok": True})
        except OSError as e:
            ev.append({"error": str(e)})
        finally:
            c.close()


LINE = re.compile(r"^(\d+\.\d+) IP6 .*?\) ([0-9a-f:]+)\.(\d+) > ([0-9a-f:]+)\.(\d+): Flags \[([^\]]*)\]"
                  r"(?:, cksum \S+(?: \([^)]*\))?)?(?:, seq (\d+)(?::(\d+))?)?(?:, ack (\d+))?(?:, win (\d+))?"
                  r"(?:, options \[([^\]]*)\])?, length (\d+)")


def parse(text):
    pk = []
    for raw in text.splitlines():
        m = LINE.search(raw)
        if not m:
            continue
        t, sa, sp, da, dp, fl, s0, s1, ack, win, opt, ln = m.groups()
        pk.append({"t": float(t), "sport": int(sp), "dport": int(dp), "flags": fl,
                   "seq": int(s0) if s0 else None, "end": int(s1) if s1 else None,
                   "ack": int(ack) if ack else None, "opts": opt or "", "len": int(ln)})
    return pk


def analyse(pk):
    out = {}
    # connect: AROS's SYNs to 7001
    syns = [p for p in pk if p["dport"] == 7001 and "S" in p["flags"] and "." not in p["flags"]]
    out["connect"] = {
        "syns": len(syns),
        "syn_options": syns[0]["opts"] if syns else None,
        "syn_flags": syns[0]["flags"] if syns else None,
        "source_ports": [p["sport"] for p in syns],
        "isn_deltas": [(syns[i]["seq"] - syns[i - 1]["seq"]) % 2**32 for i in range(1, len(syns))],
    }
    # send: data from AROS to 7002
    data = [p for p in pk if p["dport"] == 7002 and p["len"] > 0]
    acks = [p for p in pk if p["sport"] == 7002]
    seen, retx, rto, prev_t = set(), 0, 0, None
    gaps = []
    for p in data:
        key = p["seq"]
        if key in seen:
            retx += 1
            if prev_t is not None:
                gaps.append(round(p["t"] - prev_t, 3))
                if p["t"] - prev_t >= 0.2:
                    rto += 1
        seen.add(key)
        prev_t = p["t"]
    out["send"] = {
        "data_segments": len(data), "distinct": len(seen), "retransmissions": retx,
        "expected_losses": len(data) // LOSS_EVERY,
        "retransmissions_after_quiet_200ms_or_more": rto,
        "longest_quiet_before_a_retransmission": max(gaps) if gaps else None,
        "host_acks_with_sack": sum(1 for a in acks if "sack" in a["opts"] and "sackOK" not in a["opts"]),
        "seconds": round(data[-1]["t"] - data[0]["t"], 3) if data else None,
        "mss_seen": max((p["len"] for p in data), default=None),
    }
    # unread: what AROS sends after closing with unread data
    after = [p for p in pk if p["dport"] == 7003 and ("R" in p["flags"] or "F" in p["flags"])]
    out["unread"] = {"aros_close_flags": [p["flags"] for p in after]}
    # stall: transmissions of the first data segment to 7004
    sd = [p for p in pk if p["dport"] == 7004 and p["len"] > 0]
    if sd:
        first = sd[0]["seq"]
        times = [p["t"] for p in sd if p["seq"] == first]
        out["stall"] = {"transmissions": len(times),
                        "intervals": [round(times[i] - times[i - 1], 3) for i in range(1, len(times))]}
    else:
        out["stall"] = {"transmissions": 0}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", default=os.environ.get("AROS_HOSTED_IMAGE",
        os.path.expanduser("~/aros-build-ipv6-hosted/bin/linux-x86_64/AROS")))
    ap.add_argument("--arostcp")
    ap.add_argument("--no-shape", action="store_true", help="leave the link alone (no tc)")
    ap.add_argument("--only", help="comma-separated modes to run (connect,send,unread,stall)")
    ap.add_argument("--out", default=os.path.join(ROOT, "tests", "tcp", "out", time.strftime("%Y%m%d-%H%M%S")))
    a = ap.parse_args()
    global SHAPE
    SHAPE = not a.no_shape
    os.makedirs(a.out, exist_ok=True)
    exe = os.path.join(a.out, "tcpbench")
    subprocess.run([CROSS, "-std=gnu99", "-O2", "-Wall", "-Wno-pointer-sign", "-o", exe,
                    os.path.join(HERE, "tcpbench.c")], check=True)
    subprocess.run([os.path.join(ROOT, "tools", "tap-up.sh")], check=True, stdout=subprocess.DEVNULL)
    tc_clear()
    host_ll = None
    for line in subprocess.run(["ip", "-6", "addr", "show", "dev", IFACE], capture_output=True, text=True).stdout.splitlines():
        m = re.search(r"inet6 (fe80::\S+)/", line)
        if m:
            host_ll = m.group(1)
    lst = Listeners()
    pcap = os.path.join(a.out, "tcp.pcap")
    dump = subprocess.Popen(["sudo", "-n", "tcpdump", "-i", IFACE, "-n", "-s", "128", "-w", pcap, os.environ.get("TCP_BENCH_FILTER", "ip6 and tcp")],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1)
    script = os.path.join(a.out, "tcp.script")
    b = "C:tcpbench eth0 %s" % host_ll
    with open(script, "w") as f:
        f.write("Execute SYS:System/Network/AROSTCP/S/startnet\nWait 4\n")
        modes = (a.only or "connect,send,unread,stall").split(",")
        if "connect" in modes: f.write("%s connect 7001 10 >SYS:out/connect.log\n" % b)
        if "send" in modes: f.write("%s send 7002 %d >SYS:out/send.log\n" % (b, SEND_BYTES))
        if "unread" in modes: f.write("%s unread 7003 >SYS:out/unread.log\n" % b)
        if "stall" in modes: f.write("%s stall 7004 >SYS:out/stall.log\n" % b)
    env = dict(os.environ, AROS_HOSTED_IMAGE=a.image, AROS_TAP_IP=AROS_IP, AROS_RUN_TIMEOUT="400")
    if a.arostcp:
        env["AROS_AROSTCP"] = a.arostcp
    r = subprocess.run([os.path.join(ROOT, "tools", "hosted-run.sh"), os.path.join(a.out, "aros"), script, exe],
                       env=env, capture_output=True, text=True)
    time.sleep(1)
    pids = subprocess.run(["pgrep", "-f", "^tcpdump -i %s -n -s 128 -w %s" % (IFACE, pcap)],
                          capture_output=True, text=True).stdout.split()
    for pid in pids:
        subprocess.run(["sudo", "-n", "kill", "-INT", pid])
    dump.wait(timeout=10)
    tc_clear()
    text = subprocess.run(["sudo", "-n", "tcpdump", "-tt", "-nn", "-S", "-v", "-r", pcap],
                          capture_output=True, text=True).stdout
    open(os.path.join(a.out, "tcp.txt"), "w").write(text)
    res = analyse(parse(text))
    res["host"] = lst.log
    res["boot"] = "ok" if "finished" in r.stdout else "did not finish"
    json.dump(res, open(os.path.join(a.out, "result.json"), "w"), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
