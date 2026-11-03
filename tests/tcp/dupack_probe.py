#!/usr/bin/env python3
"""
dupack_probe.py - which ACKs AROS counts as duplicate ACKs (RFC 5681
section 2, RFC 6675 section 2, RFC 2883 D-SACK), deterministically.

AROS (tcpbench send) sends 20 MB to the host over IPv6 link-local, one
connection per case (up to 3: a case is tried again when the state is not
what it needs, e.g. the host's window was shut at the time). 0.1 s in (well before the end), the host drops everything AROS sends on
that port (tc ingress, before its stack), so data stays in flight and the
host's own stack sends nothing more. From the host's last real ACK it then
injects three duplicate ACKs - the same sequence, acknowledgment, window
and timestamps - and watches 300 ms for a retransmission of SND.UNA (the
retransmission timer is a second or more away):

  dsack    each ACK carries a D-SACK only (a block below the ACK: a
           segment received twice): nothing is missing - no retransmission
  newsack  each ACK SACKs one more segment above SND.UNA (data AROS has
           sent, checked against what it sent): fast retransmit
  samewin  no SACK option, the same window: fast retransmit (RFC 5681)

    dupack_probe.py [--arostcp FILE] [--image DIR] [--out DIR]
Needs sudo -n for tc and the raw socket.
"""
import argparse, json, os, re, socket, struct, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import run_tcp

IFACE = run_tcp.IFACE
PORT = 7061
CASES = [("dsack", False), ("newsack", True), ("samewin", True)]   # name, retransmission expected
TRIES = 3       # connections per case: one where the host's window was shut does not count


def sh(*a):
    return subprocess.run(["sudo", "-n"] + list(a), capture_output=True, text=True)


def cksum(b):
    if len(b) % 2:
        b += b"\0"
    t = sum(struct.unpack("!%dH" % (len(b) // 2), b))
    while t >> 16:
        t = (t & 0xffff) + (t >> 16)
    return ~t & 0xffff


def tcp6(f):
    """An IPv6 TCP frame: dict or None."""
    if len(f) < 74 or f[12:14] != b"\x86\xdd" or f[20] != 6:
        return None
    ip, t = f[14:54], f[54:]
    off = (t[12] >> 4) * 4
    plen = struct.unpack("!H", ip[4:6])[0]
    sport, dport, seq, ack = struct.unpack("!HHII", t[:12])
    return {"src": ip[8:24], "dst": ip[24:40], "sport": sport, "dport": dport, "seq": seq, "ack": ack,
            "flags": t[13], "win": struct.unpack("!H", t[14:16])[0], "opts": t[20:off], "len": plen - off}


def ts_option(opts):
    """The timestamp option (kind 8) of opts, or b''."""
    i = 0
    while i < len(opts):
        k = opts[i]
        if k == 0:
            break
        if k == 1:
            i += 1
            continue
        if i + 1 >= len(opts):
            break
        n = opts[i + 1]
        if k == 8 and n == 10:
            return opts[i:i + 10]
        i += max(n, 2)
    return b""


def build(f, last, sack):
    """A duplicate of the host's ACK frame f (parsed: last) with SACK
    blocks sack [(start, end)]."""
    opts = b""
    ts = ts_option(last["opts"])
    if ts:
        opts += b"\x01\x01" + ts
    if sack:
        opts += b"\x01\x01" + struct.pack("!BB", 5, 2 + 8 * len(sack)) + \
            b"".join(struct.pack("!II", a & 0xffffffff, b & 0xffffffff) for a, b in sack)
    hl = 20 + len(opts)
    tcp = struct.pack("!HHIIBBHHH", last["sport"], last["dport"], last["seq"], last["ack"],
                      (hl // 4) << 4, 0x10, last["win"], 0, 0) + opts
    pseudo = last["src"] + last["dst"] + struct.pack("!I3xB", len(tcp), 6)
    tcp = tcp[:16] + struct.pack("!H", cksum(pseudo + tcp)) + tcp[18:]
    ip = f[14:18] + struct.pack("!HBB", len(tcp), 6, 64) + last["src"] + last["dst"]
    return f[0:14] + ip + tcp


def serve(result):
    """The host side, as root."""
    p = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(0x0003))
    p.setsockopt(socket.SOL_SOCKET, 33, 16 << 20)      # SO_RCVBUFFORCE: hold a whole case
    p.bind((IFACE, 0))
    l = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    l.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    l.bind(("::", PORT))
    l.listen(4)
    l.settimeout(200)
    res, todo, tries = {}, [n for n, _ in CASES], 0
    while todo and tries < TRIES * len(CASES):
        name = todo[0]
        tries += 1
        r = {}
        try:
            c, addr = l.accept()
        except socket.timeout:
            res.setdefault(name, {"error": "no connection"})
            break
        aport = addr[1]
        c.setblocking(False)
        lastf = last = None
        snd_max, mss, after = None, 0, 0
        end = time.time() + 0.1
        while time.time() < end:                    # let it run
            try:
                while c.recv(65536):
                    pass
            except (BlockingIOError, OSError):
                time.sleep(0.002)
        sh("tc", "qdisc", "add", "dev", IFACE, "ingress")
        sh("tc", "filter", "add", "dev", IFACE, "parent", "ffff:", "protocol", "ipv6", "prio", "1",
           "u32", "match", "ip6", "protocol", "6", "0xff", "match", "ip6", "dport", str(PORT), "0xffff",
           "action", "gact", "drop")
        time.sleep(0.2)
        # everything captured up to now, in order (the capture lags the
        # wire): the host's last ACK, and what AROS has sent
        p.settimeout(0.05)
        while True:
            try:
                f, where = p.recvfrom(4096)
            except socket.timeout:
                break
            x = tcp6(f)
            if not x:
                continue
            if where[2] == socket.PACKET_OUTGOING and x["sport"] == PORT and x["dport"] == aport:
                lastf, last = f, x
            elif where[2] != socket.PACKET_OUTGOING and x["sport"] == aport and x["len"] > 0:
                after += 1
                e = (x["seq"] + x["len"]) & 0xffffffff
                if snd_max is None or (e - snd_max) % 2**32 < 2**31:
                    snd_max = e
                mss = max(mss, x["len"])
        una = last["ack"] if last else None
        r["debug"] = {"snd_max": snd_max, "una": una, "mss": mss,
                      "host_win": last["win"] if last else None, "after_drop": after}
        if last is None or snd_max is None or not mss:
            r["error"] = "no ACK from the host, or no data from AROS"
        elif (snd_max - (una + mss * 8)) % 2**32 >= 2**31:
            # the SACK blocks of newsack must be data AROS has sent and the
            # host has not acknowledged
            r["error"] = "too little in flight: %d bytes" % ((snd_max - una) % 2**32)
        else:
            for k in range(3):
                if name == "dsack":
                    sack = [(una - mss * (k + 2), una - mss * (k + 1))]
                elif name == "newsack":
                    sack = [(una + mss * 4, una + mss * (5 + k))]
                else:
                    sack = []
                p.send(build(lastf, last, sack))
            t0 = time.time()
            rx, sent = [], 0
            p.settimeout(0.02)
            while time.time() < t0 + 0.3:
                try:
                    f, where = p.recvfrom(4096)
                except socket.timeout:
                    continue
                x = tcp6(f)
                if x and where[2] != socket.PACKET_OUTGOING and x["sport"] == aport and x["dport"] == PORT and x["len"] > 0:
                    sent += 1
                    if x["seq"] == una:
                        rx.append(round(time.time() - t0, 3))
            r.update(una=una, in_flight=(snd_max - una) % 2**32, mss=mss,
                     retransmitted_at=rx, aros_segments_seen=sent)
        sh("tc", "qdisc", "del", "dev", IFACE, "ingress")
        c.close()
        r["attempt"] = tries
        res[name] = r
        if "error" not in r:
            todo.pop(0)
        time.sleep(0.5)
    with open(result, "w") as fo:
        json.dump(res, fo, indent=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--serve", help=argparse.SUPPRESS)
    ap.add_argument("--image", default=os.environ.get("AROS_HOSTED_IMAGE",
        os.path.expanduser("~/aros-build-ipv6-hosted-claude/bin/linux-x86_64/AROS")))
    ap.add_argument("--arostcp")
    ap.add_argument("--out", default=os.path.join(HERE, "out", "dupack-" + time.strftime("%Y%m%d-%H%M%S")))
    a = ap.parse_args()
    if a.serve:
        return serve(a.serve)
    os.makedirs(a.out, exist_ok=True)
    exe = os.path.join(a.out, "tcpbench")
    subprocess.run([run_tcp.CROSS, "-std=gnu99", "-O2", "-Wall", "-Wno-pointer-sign", "-o", exe,
                    os.path.join(HERE, "tcpbench.c")], check=True, capture_output=True)
    subprocess.run([os.path.join(ROOT, "tools", "tap-up.sh")], check=True, stdout=subprocess.DEVNULL)
    run_tcp.tc_clear()
    run_tcp.kill_strays()
    host_ll = re.findall(r"inet6 (fe80::[0-9a-f:]+)/", subprocess.run(
        ["ip", "-6", "addr", "show", "dev", IFACE], capture_output=True, text=True).stdout)[0]
    hostres = os.path.join(a.out, "host.json")
    srv = subprocess.Popen(["sudo", "-n", sys.executable, "-I", os.path.abspath(__file__), "--serve", hostres])
    time.sleep(1)
    script = os.path.join(a.out, "dupack.script")
    with open(script, "w") as f:
        f.write("Execute SYS:System/Network/AROSTCP/S/startnet\nWait 4\n")
        for i in range(TRIES * len(CASES)):
            f.write("C:tcpbench eth0 %s send %d 20000000 >SYS:out/c%d.log\nWait 1\n" % (host_ll, PORT, i))
    env = dict(os.environ, AROS_HOSTED_IMAGE=a.image, AROS_TAP_IP=run_tcp.AROS_IP, AROS_RUN_TIMEOUT="400")
    if a.arostcp:
        env["AROS_AROSTCP"] = os.path.abspath(a.arostcp)
    subprocess.run([os.path.join(ROOT, "tools", "hosted-run.sh"), os.path.join(a.out, "aros"), script, exe],
                   env=env, capture_output=True, text=True)
    try:
        srv.wait(timeout=30)
    except subprocess.TimeoutExpired:
        sh("kill", str(srv.pid))
    run_tcp.tc_clear()
    host = json.load(open(hostres)) if os.path.exists(hostres) else {}
    res, ok = {}, True
    for name, expect in CASES:
        h = host.get(name, {})
        if "error" in h or h.get("aros_segments_seen") is None:
            res[name] = dict(h, verdict="BENCH: " + h.get("error", "no result"))
            ok = False
            continue
        got = bool(h["retransmitted_at"])
        res[name] = dict(h, verdict="ok" if got == expect else "FAIL")
    # the bench checks itself: the positive controls must see a retransmission
    bench_ok = ok and res["newsack"]["verdict"] == "ok" and res["samewin"]["verdict"] == "ok"
    res["bench_ok"] = bench_ok
    json.dump(res, open(os.path.join(a.out, "result.json"), "w"), indent=1)
    for name, _ in CASES:
        print("%-8s %-6s retransmitted_at=%s" % (name, res[name]["verdict"], res[name].get("retransmitted_at")))
    print("bench_ok=%s out=%s" % (bench_ok, a.out))


if __name__ == "__main__":
    main()
