#!/usr/bin/env python3
"""
rst_probe.py - what an AROS TCP connection does with a reset or a SYN it
did not expect (RFC 9293 section 3.10.7.4, RFC 5961 sections 3 and 4).

AROS (tcpbench hold) opens one connection to the host per case, over IPv6
link-local, and waits for one byte. The host learns AROS's next expected
sequence number (RCV.NXT) from AROS's last ACK on the tap, injects one
segment with a raw socket, watches what AROS sends back for 0.5 s, then
sends the byte. AROS gets it if the connection survived, ECONNRESET if not.

  exact    RST at RCV.NXT                must reset (and checks the bench)
  old      RST 100000 before RCV.NXT     outside the window: ignored
  inwin    RST 1000 after RCV.NXT        in the window, not exact: RFC 5961
                                         3.2, a challenge ACK, no reset
  syn      SYN 1000 after RCV.NXT        RFC 5961 4.2: a challenge ACK, no
                                         reset
  beyond   RST 2^30 after RCV.NXT        far outside the window: ignored
                                         (checks the bench)
  oldack   data at RCV.NXT, ACK 2^30     RFC 5961 5.2: not from the peer:
           before AROS's SND.UNA         dropped, a challenge ACK; AROS
                                         gets the host's byte, not this one
  limit    10 RSTs in the window at once RFC 5961 section 7: no reset, and
                                         1 to 5 challenge ACKs (5 a second)

    rst_probe.py [--arostcp FILE] [--image DIR] [--out DIR]
Needs sudo -n for the raw socket (AF_PACKET).
"""
import argparse, json, os, re, socket, struct, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
IFACE = "aros0"
PORT = 7031
ECONNRESET = 54
# name: (TCP flags, offset from RCV.NXT, survives, challenge ACK expected,
#        ACK offset from AROS's SND.UNA or None for none, payload)
CASES = [
    ("exact",  0x04, 0,          False, False, None,       b""),
    ("old",    0x04, -100000,    True,  False, None,       b""),
    ("inwin",  0x04, 1000,       True,  True,  None,       b""),
    ("syn",    0x02, 1000,       True,  True,  None,       b""),
    ("beyond", 0x04, 1 << 30,    True,  False, None,       b""),
    ("oldack", 0x18, 0,          True,  True,  -(1 << 30), b"z"),
    ("limit",  0x04, 1000,       True,  True,  None,       b""),
]
REPEAT = {"limit": 10}
LIMIT = 5


def cksum(b):
    if len(b) % 2:
        b += b"\0"
    t = sum(struct.unpack("!%dH" % (len(b) // 2), b))
    while t >> 16:
        t = (t & 0xffff) + (t >> 16)
    return ~t & 0xffff


def parse(f):
    """An IPv6 TCP frame: (src, dst, sport, dport, seq, ack, flags, payload length) or None."""
    if len(f) < 14 + 60 or f[12:14] != b"\x86\xdd":
        return None
    ip = f[14:]
    if ip[6] != 6:
        return None
    plen = struct.unpack("!H", ip[4:6])[0]
    t = ip[40:]
    sport, dport, seq, ack = struct.unpack("!HHII", t[:12])
    off = (t[12] >> 4) * 4
    return ip[8:24], ip[24:40], sport, dport, seq, ack, t[13], plen - off


PENDING = []    # frames from AROS no call has wanted yet (the next connection's)


def frames(p, secs, want):
    """Frames from AROS matching want(parsed): those already received, and
    those within secs: [(frame, parsed)]. The others are kept."""
    out = [y for y in PENDING if want(y[1])]
    PENDING[:] = [y for y in PENDING if not want(y[1])]
    end = time.time() + secs
    while time.time() < end:
        p.settimeout(max(0.01, end - time.time()))
        try:
            f, where = p.recvfrom(2048)
        except socket.timeout:
            break
        if where[2] == socket.PACKET_OUTGOING:
            continue
        x = parse(f)
        if x and want(x):
            out.append((f, x))
        elif x:
            PENDING.append((f, x))
    return out


def serve(result, host_ll):
    """The host side, as root: accept a connection per case, inject, record."""
    idx = socket.if_nametoindex(IFACE)
    p = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(0x0003))
    p.bind((IFACE, 0))
    l = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    l.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    l.bind((host_ll, PORT, 0, idx))
    l.listen(4)
    l.settimeout(200)
    res = {}
    for name, flags, delta, _, _, ackdelta, payload in CASES:
        r = res[name] = {}
        try:
            c, addr = l.accept()
        except socket.timeout:
            r["error"] = "no connection"
            break
        aport = addr[1]
        mine = lambda x: x[2] == aport and x[3] == PORT
        seen = frames(p, 0.5, lambda x: mine(x) and x[6] & 0x10)
        if not seen:
            r["error"] = "no ACK from AROS"
            c.close()
            continue
        f, x = seen[-1]
        rcv_nxt = x[5]
        PENDING[:] = [y for y in PENDING if not mine(y[1])]    # its handshake
        ack = 0 if ackdelta is None else (x[4] + ackdelta) & 0xffffffff
        for k in range(REPEAT.get(name, 1)):
            tcp = struct.pack("!HHIIBBHHH", PORT, aport, (rcv_nxt + delta + 100 * k) & 0xffffffff,
                              ack, 5 << 4, flags, 65535, 0, 0) + payload
            pseudo = x[1] + x[0] + struct.pack("!I3xB", len(tcp), 6)
            tcp = tcp[:16] + struct.pack("!H", cksum(pseudo + tcp)) + tcp[18:]
            ip = struct.pack("!IHBB", 6 << 28, len(tcp), 6, 255) + x[1] + x[0]
            p.send(f[6:12] + f[0:6] + b"\x86\xdd" + ip + tcp)
        after = frames(p, 0.5, mine)
        r["rcv_nxt"] = rcv_nxt
        r["challenge_acks"] = sum(1 for _, y in after if y[6] & 0x14 == 0x10 and y[5] == rcv_nxt and y[7] == 0)
        r["challenge_ack"] = r["challenge_acks"] > 0
        r["aros_rst"] = any(y[6] & 0x04 for _, y in after)
        r["after"] = ["flags=%#x seq=%d ack=%d len=%d" % (y[6], y[4], y[5], y[7]) for _, y in after]
        try:
            c.send(b"k")
        except OSError as e:
            r["host_send"] = str(e)
        time.sleep(1.0)
        c.close()
    with open(result, "w") as fo:
        json.dump(res, fo, indent=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--serve", nargs=2, metavar=("RESULT", "HOST_LL"), help=argparse.SUPPRESS)
    ap.add_argument("--image", default=os.environ.get("AROS_HOSTED_IMAGE",
        os.path.expanduser("~/aros-build-ipv6-hosted-claude/bin/linux-x86_64/AROS")))
    ap.add_argument("--arostcp")
    ap.add_argument("--out", default=os.path.join(HERE, "out", "rst-" + time.strftime("%Y%m%d-%H%M%S")))
    a = ap.parse_args()
    if a.serve:
        return serve(*a.serve)

    sys.path.insert(0, HERE)
    import run_tcp
    os.makedirs(a.out, exist_ok=True)
    exe = os.path.join(a.out, "tcpbench")
    subprocess.run([run_tcp.CROSS, "-std=gnu99", "-O2", "-Wall", "-Wno-pointer-sign", "-o", exe,
                    os.path.join(HERE, "tcpbench.c")], check=True, capture_output=True)
    subprocess.run([os.path.join(ROOT, "tools", "tap-up.sh")], check=True, stdout=subprocess.DEVNULL)
    host_ll = re.findall(r"inet6 (fe80::[0-9a-f:]+)/", subprocess.run(
        ["ip", "-6", "addr", "show", "dev", IFACE], capture_output=True, text=True).stdout)[0]
    run_tcp.kill_strays()
    hostres = os.path.join(a.out, "host.json")
    srv = subprocess.Popen(["sudo", "-n", sys.executable, "-I", os.path.abspath(__file__),
                            "--serve", hostres, host_ll])
    time.sleep(1)
    script = os.path.join(a.out, "rst.script")
    with open(script, "w") as f:
        f.write("Execute SYS:System/Network/AROSTCP/S/startnet\nWait 4\n")
        f.write("C:tcpbench eth0 %s hold %d %d >SYS:out/hold.log\n" % (host_ll, PORT, len(CASES)))
    env = dict(os.environ, AROS_HOSTED_IMAGE=a.image, AROS_TAP_IP="192.168.166.2", AROS_RUN_TIMEOUT="200")
    if a.arostcp:
        env["AROS_AROSTCP"] = os.path.abspath(a.arostcp)
    subprocess.run([os.path.join(ROOT, "tools", "hosted-run.sh"), os.path.join(a.out, "aros"), script, exe],
                   env=env, capture_output=True, text=True)
    try:
        srv.wait(timeout=30)
    except subprocess.TimeoutExpired:
        subprocess.run(["sudo", "-n", "kill", str(srv.pid)])
    host = json.load(open(hostres)) if os.path.exists(hostres) else {}
    log = open(os.path.join(a.out, "aros", "out", "hold.log")).read() \
        if os.path.exists(os.path.join(a.out, "aros", "out", "hold.log")) else ""
    holds = {int(m.group(1)): (int(m.group(2)), m.group(3), int(m.group(4)))
             for m in re.finditer(r"^hold (\d+) rc=(-?\d+) c=(.) errno=(\d+)", log, re.M)}
    res, ok_bench, fails = {}, True, 0
    for i, (name, _, _, survives, challenge, _, _) in enumerate(CASES):
        h = host.get(name, {})
        rc, c, e = holds.get(i, (None, None, None))
        alive = rc == 1 and c == "k"
        if rc == 1 and c != "k":
            fails += 1          # the injected data was taken
            res[name] = dict(h, aros_rc=rc, aros_byte=c, verdict="FAIL: took the injected data")
            continue
        reset = rc == -1 and e == ECONNRESET
        r = res[name] = dict(h, aros_rc=rc, aros_errno=e,
                             survived=alive, reset=reset)
        if "error" in h or not (alive or reset):
            r["verdict"] = "BENCH: no answer"
            ok_bench = False
            continue
        good = alive == survives and (not challenge or h.get("challenge_ack"))
        if name in REPEAT and h.get("challenge_acks", 0) > LIMIT:
            good = False
        r["verdict"] = "ok" if good else "FAIL"
        if name in ("exact", "beyond") and not good:
            ok_bench = False            # the controls: the bench itself is wrong
        elif not good:
            fails += 1
    res["bench_ok"] = ok_bench
    res["fails"] = fails
    json.dump(res, open(os.path.join(a.out, "result.json"), "w"), indent=1)
    for name, *_ in CASES:
        r = res[name]
        print("%-7s %-17s survived=%s challenge_acks=%s after=%s" % (
            name, r["verdict"], r.get("survived"), r.get("challenge_acks"), r.get("after")))
    print("bench_ok=%s fails=%d out=%s" % (ok_bench, fails, a.out))


if __name__ == "__main__":
    main()
