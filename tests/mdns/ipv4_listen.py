#!/usr/bin/env python3
"""
ipv4_listen.py IFADDR NAME SECS ASK_AT - an mDNS listener and asker on IPv4
alone (B62), on the host interface with address IFADDR: for SECS seconds it
prints every response from another host that carries an A record for NAME
("t=<s> at=<epoch> unsolicited|answer A NAME <addr> ttl <ttl>": t from
its own start, at the host's clock - the one tcpdump stamps with), and at ASK_AT seconds
it asks for NAME's A record once, multicast, over IPv4 ("t=<s> asked"); a
response that comes within 2 s after the question counts as its answer.
Plain Python, no packages.
"""
import socket, struct, sys, time

ifaddr, name, secs, ask_at = sys.argv[1], sys.argv[2].rstrip(".").lower(), float(sys.argv[3]), float(sys.argv[4])
GROUP = "224.0.0.251"

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
if hasattr(socket, "SO_REUSEPORT"):
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
s.bind(("", 5353))
s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP,
             socket.inet_aton(GROUP) + socket.inet_aton(ifaddr))
s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(ifaddr))
s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 0)
s.settimeout(0.2)


def name_at(msg, at):
    labels, end, jumps = [], None, 0
    while True:
        n = msg[at]
        if n & 0xC0 == 0xC0:
            if end is None:
                end = at + 2
            at = ((n & 0x3F) << 8) | msg[at + 1]
            jumps += 1
            if jumps > 20:
                raise ValueError
            continue
        if n == 0:
            return ".".join(labels).lower(), (end if end is not None else at + 1)
        labels.append(msg[at + 1:at + 1 + n].decode("latin-1"))
        at += 1 + n


def question(qname):
    q = b"".join(bytes([len(p)]) + p.encode() for p in qname.split(".")) + b"\0"
    return struct.pack(">HHHHHH", 0, 0, 1, 0, 0, 0) + q + struct.pack(">HH", 1, 1)


t0 = time.time()
asked = None
while time.time() - t0 < secs:
    now = time.time() - t0
    if asked is None and now >= ask_at:
        s.sendto(question(name), (GROUP, 5353))
        asked = now
        print("t=%.2f at=%.6f asked" % (now, time.time()), flush=True)
    try:
        msg, src = s.recvfrom(9000)
    except socket.timeout:
        continue
    if src[0] == ifaddr or len(msg) < 12:
        continue
    flags, qd, an, ns, ar = struct.unpack(">HHHHH", msg[2:12])
    if not flags & 0x8000:
        continue
    try:
        at = 12
        for _ in range(qd):
            _, at = name_at(msg, at)
            at += 4
        for _ in range(an + ns + ar):
            rname, at = name_at(msg, at)
            rtype, rclass, ttl, rdlen = struct.unpack(">HHIH", msg[at:at + 10])
            at += 10
            if rtype == 1 and rname == name and rdlen == 4:
                t = time.time() - t0
                kind = "answer" if asked is not None and t - asked <= 2 else "unsolicited"
                print("t=%.2f at=%.6f %s A %s %s ttl %d from %s" % (t, time.time(), kind, name,
                      socket.inet_ntoa(msg[at:at + 4]), ttl, src[0]), flush=True)
            at += rdlen
    except (IndexError, ValueError, struct.error):
        pass
