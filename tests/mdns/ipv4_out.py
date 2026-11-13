#!/usr/bin/env python3
"""
ipv4_out.py - where mdnsd's IPv4 answers leave, with one socket for every
link: the packets on the wire, captured on both host taps.

AROS has eth0 on tap aros0 and eth1 on tap aros1. The host asks over mDNS
from aros1 only, and tcpdump on both taps records every answer AROS sends:
which tap it came out by, and from which address.

Cases (--case):
  route   eth0 192.168.166.2/24, eth1 192.168.167.2/24; AROS has a host
          route to 192.168.167.1 (the asker, on aros1) through
          192.168.166.1 (aros0), so its routing table prefers eth0 for the
          asker. A unicast answer (QU and legacy) must still leave by eth1.
  ll      both interfaces IP=AUTO (IPv4 link-local, RFC 3927); the host has
          169.254.1.1/16 on aros0 and 169.254.2.1/16 on aros1: 169.254/16 is
          routed by one interface only. The answer must leave by eth1.
  alias   eth0 192.168.166.2/24 plus 192.168.166.50/24; the host asks on
          aros0. Every answer's source must be one of eth0's addresses, and
          the A records it carries must be eth0's.

Each case asks three ways: a QU question (unicast answer to 5353), a legacy
question from another port (unicast answer to that port, RFC 6762 section
6.7), a QM question (multicast answer). Acceptance (per answer): the tap it
left by, its source, no copy on the other tap. Prints JSON.

    ipv4_out.py --case route|ll|alias [--image DIR] [--out DIR]
Needs sudo -n (tcpdump, ip addr, SO_BINDTODEVICE).
"""
import argparse, json, os, socket, struct, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
NAME = "arosbox.local"


def sh(*a):
    return subprocess.run(["sudo", "-n"] + list(a), capture_output=True, text=True)


def query(name, qu, qid=0):
    labels = b"".join(bytes([len(p)]) + p.encode() for p in name.split(".")) + b"\0"
    qclass = 0x8001 if qu else 1
    return struct.pack("!6H", qid, 0, 1, 0, 0, 0) + labels + struct.pack("!2H", 1, qclass)


def ask(dev, src, sport, qu, qid=0):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, dev.encode())
    s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(src))
    s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 255)
    s.bind((src, sport))
    s.sendto(query(NAME, qu, qid), ("224.0.0.251", 5353))
    s.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", choices=("route", "ll", "alias"), required=True)
    ap.add_argument("--image", default=os.environ.get("AROS_HOSTED_IMAGE",
        os.path.expanduser("~/aros-build-ipv6-hosted-claude/bin/linux-x86_64/AROS")))
    ap.add_argument("--out", default=os.path.join(HERE, "out", "ipv4out-" + time.strftime("%Y%m%d-%H%M%S")))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    for n in ("0", "1"):
        subprocess.run([os.path.join(ROOT, "tools", "tap-up.sh"), n], check=True, stdout=subprocess.DEVNULL)
    host = {"route": ("192.168.166.1", "192.168.167.1"), "ll": ("169.254.1.1", "169.254.2.1"),
            "alias": ("192.168.166.1", "192.168.167.1")}[a.case]
    added = []
    if a.case == "ll":
        for dev, addr in (("aros0", "169.254.1.1/16"), ("aros1", "169.254.2.1/16")):
            sh("ip", "addr", "add", addr, "dev", dev)
            added.append((dev, addr))
    script = os.path.join(a.out, "s.script")
    with open(script, "w") as f:
        f.write("Execute SYS:System/Network/AROSTCP/S/startnet\nWait 12\n")
        if a.case == "route":
            f.write("C:route add -host 192.168.167.1 192.168.166.1 >SYS:out/route.log\n")
        if a.case == "alias":
            f.write("Run >NIL: C:alias_owner eth0 192.168.166.50 50 >SYS:out/alias.log\nWait 8\n")
        f.write("C:netstat -rn >SYS:out/routes.log\nC:ifconfig -a >SYS:out/if.log\n")
        f.write("Echo >SYS:out/ready ready\nWait 40\n")
    files = []
    if a.case == "alias":
        cc = subprocess.run([sys.executable, "-c", "import sys;sys.path.insert(0,%r);import run_tcp;print(run_tcp.CROSS)"
                             % os.path.join(ROOT, "tests", "tcp")], capture_output=True, text=True).stdout.strip()
        exe = os.path.join(a.out, "alias_owner")
        subprocess.run([cc, "--sysroot", os.path.join(a.image, "Developer"), "-O2", "-o", exe,
                        os.path.join(ROOT, "tests", "ipv4", "alias_owner.c")], check=True)
        files.append(exe)
    env = dict(os.environ, AROS_HOSTED_IMAGE=a.image, AROS_RUN_TIMEOUT="120")
    if a.case == "ll":
        env.update(AROS_TAP_IP="AUTO", AROS_TAP2_IP="AUTO")
    else:
        env.update(AROS_TAP_IP="192.168.166.2", AROS_TAP2_IP="192.168.167.2")
    caps = {}
    try:
        aros = subprocess.Popen([os.path.join(ROOT, "tools", "hosted-run.sh"), os.path.join(a.out, "aros"), script] + files,
                                env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ready = os.path.join(a.out, "aros", "AROS", "out", "ready")
        t0 = time.time()
        while not os.path.exists(ready) and time.time() - t0 < 90:
            time.sleep(0.5)
        time.sleep(6 if a.case == "ll" else 3)   # IPv4LL probes; mdnsd announced
        for dev in ("aros0", "aros1"):
            pcap = os.path.join(a.out, dev + ".pcap")
            caps[dev] = (pcap, subprocess.Popen(["sudo", "-n", "tcpdump", "-i", dev, "-U", "-w", pcap,
                                                 "udp and src port 5353"],
                                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        time.sleep(1.5)
        dev, src = ("aros0", host[0]) if a.case == "alias" else ("aros1", host[1])
        ask(dev, src, 5353, qu=True)              # QU: unicast to 5353
        time.sleep(1.5)
        ask(dev, src, 40053, qu=False, qid=0x4d54)  # legacy: unicast to 40053
        time.sleep(1.5)
        ask(dev, src, 5353, qu=False)             # QM: multicast
        time.sleep(2.5)
    finally:
        for dev, (pcap, p) in caps.items():
            sh("pkill", "-INT", "-f", "tcpdump -i %s -U -w %s" % (dev, pcap))
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        for dev, addr in added:
            sh("ip", "addr", "del", addr, "dev", dev)
    aros.wait(timeout=200)
    res = {"case": a.case, "asked_by": "aros0" if a.case == "alias" else "aros1", "packets": {}}
    for dev, (pcap, _) in caps.items():
        r = sh("tcpdump", "-nn", "-r", pcap, "udp and src port 5353")
        res["packets"][dev] = [l.split(" ", 1)[1] for l in r.stdout.splitlines() if " IP " in l]
    for name in ("routes", "if"):
        p = os.path.join(a.out, "aros", "out", name + ".log")
        if os.path.exists(p):
            res[name] = open(p).read()
    json.dump(res, open(os.path.join(a.out, "result.json"), "w"), indent=1)
    print(json.dumps(res["packets"], indent=1))


if __name__ == "__main__":
    main()
