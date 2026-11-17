#!/usr/bin/env python3
"""
probetie.py IFADDR IFNAME NAME ADDR PROBE_SECS FAMILIES [announce]

Another host probing for NAME at the same time as AROS (RFC 6762 section
8.2): a probe for NAME (QU question, type ANY) with one address record
NAME -> ADDR in the authority section (A if ADDR is IPv4, AAAA if IPv6),
every 250 ms for PROBE_SECS seconds, to the group by FAMILIES ("4", "6" or
"46"): IPv4 from IFADDR, IPv6 from interface IFNAME's link-local address.
With "announce" it then announces NAME -> ADDR (cache-flush, TTL 120) twice,
a second apart, by the same families, as the winner of the tie-break would.
Prints one line per packet: "<epoch> probe|announce <family>". Plain Python.
"""
import socket, struct, sys, time

ifaddr, ifname, name, addr, secs, fams = sys.argv[1:7]
secs = float(secs)
announce = len(sys.argv) > 7 and sys.argv[7] == "announce"
qname = b"".join(bytes([len(p)]) + p.encode() for p in name.rstrip(".").split(".")) + b"\0"
if ":" in addr:
    rtype, rdata = 28, socket.inet_pton(socket.AF_INET6, addr)
else:
    rtype, rdata = 1, socket.inet_aton(addr)


def record(rclass):
    return qname + struct.pack(">HHIH", rtype, rclass, 120, len(rdata)) + rdata


probe = struct.pack(">HHHHHH", 0, 0, 1, 0, 1, 0) + qname + struct.pack(">HH", 255, 0x8001) + record(1)
answer = struct.pack(">HHHHHH", 0, 0x8400, 0, 1, 0, 0) + record(0x8001)
socks = []
if "4" in fams:
    s4 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s4.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s4.bind((ifaddr, 5353))
    s4.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(ifaddr))
    s4.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 255)
    socks.append(("4", s4, ("224.0.0.251", 5353)))
if "6" in fams:
    index = socket.if_nametoindex(ifname)
    s6 = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
    s6.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s6.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_MULTICAST_IF, index)
    s6.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_MULTICAST_HOPS, 255)
    try:
        s6.bind(("::", 5353))
    except OSError:
        s6.bind(("::", 0))      # another responder holds it: a legacy sender
        print("ipv6: not from port 5353", file=sys.stderr, flush=True)
    socks.append(("6", s6, ("ff02::fb", 5353, 0, index)))


def send(pkt, kind):
    for fam, s, to in socks:
        s.sendto(pkt, to)
        print("%.6f %s %s" % (time.time(), kind, fam), flush=True)


end = time.time() + secs
while time.time() < end:
    send(probe, "probe")
    time.sleep(0.25)
if announce:
    for _ in range(2):
        send(answer, "announce")
        time.sleep(1.0)
