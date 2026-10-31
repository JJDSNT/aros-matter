#!/usr/bin/env python3
"""
pmtud_probe.py - how AROS reacts to an ICMPv6 Packet Too Big during a TCP transfer.

AROS (hosted, tap.device on aros0) sends SEND_BYTES to the host over link-local
with tcpbench. When its first full-sized data segment shows up, the host sends
AROS a Packet Too Big (RFC 4443 section 3.2) with MTU 1280, quoting that
segment. Then it reports, for AROS's packets before and after the Packet Too
Big: the largest IPv6 packet, the TCP segment sizes, and how many fragments.
After the transfer, a second connection shows the MSS a new connection offers.

    pmtud_probe.py [--arostcp FILE] [--image DIR] [--mtu 1280] [--out DIR]

Needs sudo -n for tcpdump and for the raw sockets (AF_PACKET, ICMPv6).
"""
import argparse, json, os, re, socket, struct, subprocess, sys, threading, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import run_tcp   # CROSS, IFACE, AROS_IP and the tcpbench build

IFACE = run_tcp.IFACE
SEND_BYTES = 2000000


def listener(port, log):
    s = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("::", port))
    s.listen(4)
    s.settimeout(120)
    try:
        while True:
            c, _ = s.accept()
            n = 0
            c.settimeout(30)
            try:
                while True:
                    b = c.recv(65536)
                    if not b:
                        break
                    n += len(b)
            except socket.timeout:
                pass
            log.append(n)
            c.close()
    except socket.timeout:
        pass


def inject_ptb(mtu, port, done, proto=6):
    """Wait on aros0 for a large IPv6 TCP segment to port; answer it with a
    Packet Too Big quoting it. done gets the time and the quoted header."""
    p = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(0x86dd))
    p.bind((IFACE, 0))
    p.settimeout(180)
    try:
        while True:
            f = p.recv(2048)
            ip = f[14:]
            if len(ip) < 48 or ip[6] != proto:
                continue
            dport = struct.unpack("!H", ip[42:44])[0]
            plen = struct.unpack("!H", ip[4:6])[0]
            if dport != port or 40 + plen <= mtu:
                continue
            src = socket.inet_ntop(socket.AF_INET6, ip[8:24])
            dst = socket.inet_ntop(socket.AF_INET6, ip[24:40])
            r = socket.socket(socket.AF_INET6, socket.SOCK_RAW, socket.IPPROTO_ICMPV6)
            idx = socket.if_nametoindex(IFACE)
            r.bind((dst, 0, 0, idx if dst.startswith("fe80") else 0))
            quoted = ip[:mtu - 40 - 8]          # as much as fits the minimum MTU
            msg = struct.pack("!BBHI", 2, 0, 0, mtu) + quoted
            r.sendto(msg, (src, 0, 0, idx if src.startswith("fe80") else 0))
            done.update(time=time.time(), aros=src, host=dst, quoted_len=len(quoted))
            return
    except socket.timeout:
        return


OFF_PREFIX = "2001:db8:4d55::"        # AROS's SLAAC prefix (autonomous, not on-link)
OFF_DST = ["2001:db8:4d54::1", "2001:db8:4d54::2"]   # "remote" addresses on the host


def send_ra(router_ll, count=3):
    """Router Advertisements from the host: default router, plus OFF_PREFIX
    for SLAAC only (A=1, L=0), so OFF_DST are reached through the router."""
    pio = struct.pack("!BBBBIII", 3, 4, 64, 0x40, 3600, 3600, 0) + socket.inet_pton(socket.AF_INET6, OFF_PREFIX)
    ra = struct.pack("!BBHBBHII", 134, 0, 0, 64, 0, 1800, 0, 0) + pio
    s = socket.socket(socket.AF_INET6, socket.SOCK_RAW, socket.IPPROTO_ICMPV6)
    idx = socket.if_nametoindex(IFACE)
    s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_MULTICAST_HOPS, 255)
    s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_MULTICAST_IF, idx)
    s.bind((router_ll, 0, 0, idx))
    for _ in range(count):
        s.sendto(ra, ("ff02::1", 0, 0, idx))
        time.sleep(1)


def analyse(text, res, a):
    """Add to res what AROS sent before and after the Packet Too Big."""
    ptb = res.get("ptb") or {}
    aros = ptb.get("aros")
    if not aros:
        return res
    t0 = ptb["time"]
    # AROS's IPv6 packets: time, packet length, fragment?, SYN mss, destination
    pkts = []
    for line in text.splitlines():
        m = re.match(r"^(\d+\.\d+) IP6 \((.*?payload length: (\d+))\) (\S+) > (\S+): ", line)
        if not m or m.group(4).rsplit(".", 1)[0] != aros and m.group(4) != aros:
            continue
        frag = "Fragment (44)" in m.group(2)
        first = not frag or re.search(r"frag \(0x[0-9a-f]+:0\|", line) is not None
        mss = re.search(r"Flags \[S\].*?mss (\d+)", line)
        dst = m.group(5)
        if not frag and dst.count(".") == 1 and not dst.startswith("fe80") and dst.rsplit(".", 1)[1].isdigit():
            dst = dst.rsplit(".", 1)[0]          # address.port
        pkts.append(dict(t=float(m.group(1)), len=40 + int(m.group(3)), frag=frag, first=first,
                         mss=int(mss.group(1)) if mss else None, dst=dst))

    def summary(ps):
        return {"packets": len(ps), "largest": max([p["len"] for p in ps] or [0]),
                "fragments": sum(1 for p in ps if p["frag"]),
                "over_mtu": sum(1 for p in ps if p["len"] > a.mtu)}
    res["before_ptb"] = summary([p for p in pkts if p["t"] < t0])
    res["after_ptb"] = summary([p for p in pkts if p["t"] >= t0])
    res["syn_mss"] = [p["mss"] for p in pkts if p["mss"]]
    if a.udp:
        # each datagram after the Packet Too Big, once (by its first fragment)
        res["udp_after_ptb"] = [{"dst": p["dst"], "fragmented": p["frag"], "length": p["len"]}
                                for p in pkts if p["t"] >= t0 and p["first"] and p["dst"] in OFF_DST]
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", default=os.environ.get("AROS_HOSTED_IMAGE",
        os.path.expanduser("~/aros-build-ipv6-hosted-claude/bin/linux-x86_64/AROS")))
    ap.add_argument("--arostcp")
    ap.add_argument("--mtu", type=int, default=1280)
    ap.add_argument("--udp", action="store_true",
                    help="with --offlink: 1452-byte UDP datagrams to OFF_DST[0], [1], [0]; Packet Too Big (--mtu, say 1400) about the first")
    ap.add_argument("--offlink", action="store_true",
                    help="reach the host through a default router (the host itself) at OFF_DST")
    ap.add_argument("--reanalyse", action="store_true", help="only analyse OUT/pmtud.txt and OUT/result.json again")
    ap.add_argument("--out", default=os.path.join(ROOT, "tests", "tcp", "out", "pmtud-" + time.strftime("%Y%m%d-%H%M%S")))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    if a.reanalyse:
        old = json.load(open(os.path.join(a.out, "result.json")))
        print(json.dumps(analyse(open(os.path.join(a.out, "pmtud.txt")).read(), old, a), indent=1))
        return
    prog = "udp6once" if a.udp else "tcpbench"
    exe = os.path.join(a.out, prog)
    subprocess.run([run_tcp.CROSS, "-std=gnu99", "-O2", "-Wall", "-Wno-pointer-sign", "-o", exe,
                    os.path.join(HERE, prog + ".c")], check=True)
    subprocess.run([os.path.join(ROOT, "tools", "tap-up.sh")], check=True, stdout=subprocess.DEVNULL)
    lls = []
    for line in subprocess.run(["ip", "-6", "addr", "show", "dev", IFACE], capture_output=True, text=True).stdout.splitlines():
        m = re.search(r"inet6 (fe80::\S+)/", line)
        if m:
            lls.append(m.group(1))
    if not lls:
        sys.exit("no IPv6 link-local address on %s" % IFACE)
    # the Packet Too Big is about the first; the second connection goes to
    # another of the host's addresses on the same link, if it has one
    host_ll, other_ll = lls[0], lls[-1]
    accept_ra = None
    if a.offlink:
        # the host must not configure itself from the RA it sends on the tap
        ra_path = "/proc/sys/net/ipv6/conf/%s/accept_ra" % IFACE
        accept_ra = open(ra_path).read().strip()
        subprocess.run(["sudo", "-n", "sysctl", "-q", "-w", "net.ipv6.conf.%s.accept_ra=0" % IFACE])
        for d in OFF_DST:
            subprocess.run(["sudo", "-n", "ip", "-6", "addr", "add", d + "/128", "dev", IFACE, "nodad"])
        subprocess.run(["sudo", "-n", "ip", "-6", "route", "add", OFF_PREFIX + "/64", "dev", IFACE])
        host_ll, other_ll = OFF_DST

    got = []
    threading.Thread(target=listener, args=(7002, got), daemon=True).start()
    ptb = {}
    pcap = os.path.join(a.out, "pmtud.pcap")
    dump = subprocess.Popen(["sudo", "-n", "tcpdump", "-U", "-i", IFACE, "-n", "-s", "128", "-w", pcap, "ip6"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1)
    script = os.path.join(a.out, "pmtud.script")
    with open(script, "w") as f:
        f.write("Execute SYS:System/Network/AROSTCP/S/startnet\nWait %d\n" % (12 if a.offlink else 4))
        if a.udp:
            f.write("C:udp6once eth0 %s 9999 1452 >SYS:out/u1.log\nWait 2\n" % host_ll)
            f.write("C:udp6once eth0 %s 9999 1452 >SYS:out/u2.log\n" % other_ll)
            f.write("C:udp6once eth0 %s 9999 1452 >SYS:out/u3.log\n" % host_ll)
        else:
            f.write("C:tcpbench eth0 %s send 7002 %d >SYS:out/send1.log\n" % (host_ll, SEND_BYTES))
            f.write("Wait 2\n")
            f.write("C:tcpbench eth0 %s send 7002 %d >SYS:out/send2.log\n" % (host_ll, SEND_BYTES))
            f.write("C:tcpbench eth0 %s send 7002 %d >SYS:out/send3.log\n" % (other_ll, SEND_BYTES))
    env = dict(os.environ, AROS_HOSTED_IMAGE=a.image, AROS_TAP_IP=run_tcp.AROS_IP, AROS_RUN_TIMEOUT="300")
    if a.arostcp:
        env["AROS_AROSTCP"] = a.arostcp
    # the injector needs root for AF_PACKET and raw ICMPv6: run it via sudo python
    inj_cmd = ["sudo", "-n", sys.executable, "-I", "-c",
               "import sys,json; sys.path.insert(0,%r); import pmtud_probe as p; d={}; p.inject_ptb(%d,%d,d,%d); print(json.dumps(d))" % (HERE, a.mtu, 9999 if a.udp else 7002, 17 if a.udp else 6)]
    injp = subprocess.Popen(inj_cmd, stdout=subprocess.PIPE, text=True)
    if a.offlink:
        # once AROS is up (startnet + DAD), advertise the router
        ra_cmd = ["sudo", "-n", sys.executable, "-I", "-c",
                  "import sys,time; sys.path.insert(0,%r); import pmtud_probe as p; time.sleep(9); p.send_ra(%r)" % (HERE, lls[0])]
        rap = subprocess.Popen(ra_cmd)
    r = subprocess.run([os.path.join(ROOT, "tools", "hosted-run.sh"), os.path.join(a.out, "aros"), script, exe],
                       env=env, capture_output=True, text=True)
    try:
        out, _ = injp.communicate(timeout=10)
        ptb = json.loads(out.strip() or "{}")
    except Exception:
        injp.kill()
    if a.offlink:
        rap.wait(timeout=30)
        subprocess.run(["sudo", "-n", "ip", "-6", "route", "del", OFF_PREFIX + "/64", "dev", IFACE])
        for d in OFF_DST:
            subprocess.run(["sudo", "-n", "ip", "-6", "addr", "del", d + "/128", "dev", IFACE])
        subprocess.run(["sudo", "-n", "sysctl", "-q", "-w", "net.ipv6.conf.%s.accept_ra=%s" % (IFACE, accept_ra)])
    time.sleep(1)
    for pid in subprocess.run(["pgrep", "-f", "^tcpdump -U -i %s -n -s 128 -w %s" % (IFACE, pcap)],
                              capture_output=True, text=True).stdout.split():
        subprocess.run(["sudo", "-n", "kill", "-INT", pid])
    dump.wait(timeout=10)
    text = subprocess.run(["sudo", "-n", "tcpdump", "-tt", "-nn", "-v", "-r", pcap],
                          capture_output=True, text=True).stdout
    open(os.path.join(a.out, "pmtud.txt"), "w").write(text)

    res = analyse(text, {"host_addresses": lls, "ptb": ptb, "host_bytes": got,
                         "boot": "ok" if "finished" in r.stdout else "did not finish"}, a)
    json.dump(res, open(os.path.join(a.out, "result.json"), "w"), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
