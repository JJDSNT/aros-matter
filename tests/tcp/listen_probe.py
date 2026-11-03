#!/usr/bin/env python3
"""
listen_probe.py - what a listening AROS socket answers to segments that do
not open a connection (RFC 9293 section 3.10.7.2; AROS d6425105cc), on the
wire.

AROS listens (tcpserve 4 PORT recv). The host injects IPv4 segments from
made-up ports with a raw socket, and reads what AROS sends back:

  stray    an ACK, no SYN before it          a reset <SEQ=SEG.ACK><CTL=RST>
  rst      a reset                           nothing
  badack   SYN, AROS's SYN-ACK, then an ACK  a reset <SEQ=SEG.ACK><CTL=RST>
           that does not acknowledge it
  goodack  SYN, SYN-ACK, the right ACK, data AROS acknowledges the data, no
                                             reset (checks the bench)

The host's own stack would reset the SYN-ACKs of connections it does not
know: its resets to PORT are dropped on the way out (the injected segments
bypass the qdisc).

    listen_probe.py [--arostcp FILE] [--image DIR] [--out DIR]
Needs sudo -n for tc, ping and the raw socket.
"""
import argparse, json, os, random, re, socket, struct, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import run_tcp

IFACE = run_tcp.IFACE
PORT = 7081
HOST_IP = "192.168.166.1"
PACKET_QDISC_BYPASS = 20


def sh(*a):
    return subprocess.run(["sudo", "-n"] + list(a), capture_output=True, text=True)


def cksum(b):
    if len(b) % 2:
        b += b"\0"
    t = sum(struct.unpack("!%dH" % (len(b) // 2), b))
    while t >> 16:
        t = (t & 0xffff) + (t >> 16)
    return ~t & 0xffff


class Wire:
    def __init__(self, aros_ip, aros_mac):
        self.p = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(0x0003))
        self.p.setsockopt(socket.SOL_PACKET, PACKET_QDISC_BYPASS, 1)
        self.p.bind((IFACE, 0))
        self.src = socket.inet_aton(HOST_IP)
        self.dst = socket.inet_aton(aros_ip)
        self.hmac = bytes.fromhex(open("/sys/class/net/%s/address" % IFACE).read().strip().replace(":", ""))
        self.amac = bytes.fromhex(aros_mac.replace(":", ""))

    def send(self, sport, seq, ack, flags, data=b"", opts=b""):
        hl = 20 + len(opts)
        tcp = struct.pack("!HHIIBBHHH", sport, PORT, seq & 0xffffffff, ack & 0xffffffff,
                          (hl // 4) << 4, flags, 65535, 0, 0) + opts + data
        pseudo = self.src + self.dst + struct.pack("!BBH", 0, 6, len(tcp))
        tcp = tcp[:16] + struct.pack("!H", cksum(pseudo + tcp)) + tcp[18:]
        ip = struct.pack("!BBHHHBBH4s4s", 0x45, 0, 20 + len(tcp), random.randrange(65536), 0x4000, 64, 6, 0,
                         self.src, self.dst)
        ip = ip[:10] + struct.pack("!H", cksum(ip)) + ip[12:]
        self.p.send(self.amac + self.hmac + b"\x08\x00" + ip + tcp)

    def replies(self, sport, secs):
        """AROS's segments to sport within secs: [(flags, seq, ack, len)]."""
        out, end = [], time.time() + secs
        while time.time() < end:
            self.p.settimeout(max(0.01, end - time.time()))
            try:
                f, where = self.p.recvfrom(2048)
            except socket.timeout:
                break
            if where[2] == socket.PACKET_OUTGOING or f[12:14] != b"\x08\x00" or f[23] != 6:
                continue
            ihl = (f[14] & 15) * 4
            t = f[14 + ihl:]
            sp, dp, seq, ack = struct.unpack("!HHII", t[:12])
            if sp != PORT or dp != sport:
                continue
            tot = struct.unpack("!H", f[16:18])[0]
            out.append({"flags": t[13], "seq": seq, "ack": ack, "len": tot - ihl - (t[12] >> 4) * 4})
        return out


def serve(result, aros_ip, aros_mac):
    w = Wire(aros_ip, aros_mac)
    res = {}
    mss = struct.pack("!BBH", 2, 4, 1460)

    def case(name, fn):
        sport = random.randrange(40000, 60000)
        res[name] = fn(sport)

    def stray(sport):
        ack = random.randrange(1 << 32)
        w.send(sport, random.randrange(1 << 32), ack, 0x10)
        r = w.replies(sport, 0.5)
        rst = [x for x in r if x["flags"] & 0x04]
        return {"replies": r, "ok": bool(rst) and rst[0]["seq"] == ack and not rst[0]["flags"] & 0x10}

    def rst(sport):
        w.send(sport, random.randrange(1 << 32), 0, 0x04)
        r = w.replies(sport, 0.5)
        return {"replies": r, "ok": not r}

    def handshake(sport):
        iss = random.randrange(1 << 32)
        w.send(sport, iss, 0, 0x02, opts=mss)
        sa = [x for x in w.replies(sport, 1.0) if x["flags"] & 0x12 == 0x12]
        return iss, sa[0] if sa else None

    def badack(sport):
        iss, sa = handshake(sport)
        if not sa:
            return {"error": "no SYN-ACK", "ok": False}
        bad = (sa["seq"] + 1 + 100000) & 0xffffffff
        w.send(sport, iss + 1, bad, 0x10)
        r = w.replies(sport, 0.5)
        rst = [x for x in r if x["flags"] & 0x04]
        return {"replies": r, "ok": bool(rst) and rst[0]["seq"] == bad}

    def goodack(sport):
        iss, sa = handshake(sport)
        if not sa:
            return {"error": "no SYN-ACK", "ok": False}
        w.send(sport, iss + 1, sa["seq"] + 1, 0x10)
        w.send(sport, iss + 1, sa["seq"] + 1, 0x18, data=b"hello")
        r = w.replies(sport, 0.5)
        acked = any(x["ack"] == (iss + 1 + 5) & 0xffffffff and not x["flags"] & 0x04 for x in r)
        w.send(sport, iss + 6, sa["seq"] + 1, 0x11)          # FIN: tcpserve may finish
        return {"replies": r, "ok": acked and not any(x["flags"] & 0x04 for x in r)}

    time.sleep(0.5)
    for name, fn in (("stray", stray), ("rst", rst), ("badack", badack), ("goodack", goodack)):
        case(name, fn)
    with open(result, "w") as fo:
        json.dump(res, fo, indent=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--serve", nargs=3, help=argparse.SUPPRESS)
    ap.add_argument("--image", default=os.environ.get("AROS_HOSTED_IMAGE",
        os.path.expanduser("~/aros-build-ipv6-hosted-claude/bin/linux-x86_64/AROS")))
    ap.add_argument("--arostcp")
    ap.add_argument("--out", default=os.path.join(HERE, "out", "listen-" + time.strftime("%Y%m%d-%H%M%S")))
    a = ap.parse_args()
    if a.serve:
        return serve(*a.serve)
    os.makedirs(a.out, exist_ok=True)
    exes = [os.path.join(a.out, "tcpserve")]
    subprocess.run([run_tcp.CROSS, "-std=gnu99", "-O2", "-Wall", "-Wno-pointer-sign", "-o", exes[0],
                    os.path.join(HERE, "tcpserve.c")], check=True, capture_output=True)
    subprocess.run([os.path.join(ROOT, "tools", "tap-up.sh")], check=True, stdout=subprocess.DEVNULL)
    run_tcp.tc_clear()
    run_tcp.kill_strays()
    # the host's own resets to PORT do not leave (the injected segments bypass this)
    sh("tc", "qdisc", "add", "dev", IFACE, "root", "handle", "1:", "prio")
    sh("tc", "filter", "add", "dev", IFACE, "parent", "1:", "protocol", "ip", "prio", "1", "u32",
       "match", "ip", "protocol", "6", "0xff", "match", "ip", "dport", str(PORT), "0xffff",
       "match", "u8", "0x04", "0x04", "at", "33", "action", "gact", "drop")
    script = os.path.join(a.out, "listen.script")
    with open(script, "w") as f:
        f.write("Execute SYS:System/Network/AROSTCP/S/startnet\nWait 4\n")
        f.write("C:tcpserve 4 %d recv 100 >SYS:out/serve.log\n" % PORT)
    env = dict(os.environ, AROS_HOSTED_IMAGE=a.image, AROS_TAP_IP=run_tcp.AROS_IP, AROS_RUN_TIMEOUT="200")
    if a.arostcp:
        env["AROS_AROSTCP"] = os.path.abspath(a.arostcp)
    aros = subprocess.Popen([os.path.join(ROOT, "tools", "hosted-run.sh"), os.path.join(a.out, "aros"), script]
                            + exes, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    # wait until AROS answers on the tap, then learn its MAC
    mac, end = None, time.time() + 90
    while time.time() < end and mac is None:
        subprocess.run(["ping", "-c", "1", "-W", "1", run_tcp.AROS_IP], capture_output=True)
        m = re.search(r"lladdr ([0-9a-f:]{17})", subprocess.run(["ip", "neigh", "show", run_tcp.AROS_IP],
                                                               capture_output=True, text=True).stdout)
        mac = m.group(1) if m else None
    time.sleep(3)                       # tcpserve is listening by now
    hostres = os.path.join(a.out, "host.json")
    if mac:
        subprocess.run(["sudo", "-n", sys.executable, "-I", os.path.abspath(__file__), "--serve", hostres,
                        run_tcp.AROS_IP, mac], timeout=60)
    aros.wait(timeout=240)
    run_tcp.tc_clear()
    host = json.load(open(hostres)) if os.path.exists(hostres) else {}
    res = {"aros_mac": mac, "cases": host}
    res["bench_ok"] = bool(host) and host.get("goodack", {}).get("ok", False)
    res["fails"] = [n for n, r in host.items() if not r.get("ok")]
    json.dump(res, open(os.path.join(a.out, "result.json"), "w"), indent=1)
    for n, r in host.items():
        print("%-8s %-4s %s" % (n, "ok" if r.get("ok") else "FAIL",
                                [("%#x" % x["flags"], x["seq"], x["ack"], x["len"]) for x in r.get("replies", [])][:3]))
    print("bench_ok=%s fails=%s out=%s" % (res["bench_ok"], res["fails"], a.out))


if __name__ == "__main__":
    main()
