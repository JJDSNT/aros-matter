#!/usr/bin/env python3
"""
avail.py IFADDR NAME ADDR SECS [TYPE] - whether a host keeps answering for
NAME on one link (B76): every 100 ms, for SECS seconds, a question for NAME's
A record (or TYPE: a number, 33 for a service's SRV, answered with the
address of its host) goes to 224.0.0.251 from the host interface with address IFADDR,
from a port other than 5353 - a legacy question (RFC 6762 section 6.7),
answered straight back by unicast, which no multicast rate limit holds
back. Prints one line per question: "<epoch> ok|none" (ok: an answer with
ADDR came within 80 ms), then the stretches with no answer. Plain Python.
"""
import socket, struct, sys, time

ifaddr, name, want, secs = sys.argv[1], sys.argv[2].rstrip("."), sys.argv[3], float(sys.argv[4])
qtype = int(sys.argv[5]) if len(sys.argv) > 5 else 1
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.bind((ifaddr, 0))
s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(ifaddr))
s.settimeout(0.02)
qname = b"".join(bytes([len(p)]) + p.encode() for p in name.split(".")) + b"\0"


def answered(msg, ident):
    if len(msg) < 12 or struct.unpack(">H", msg[:2])[0] != ident:
        return False
    return socket.inet_aton(want) in msg


t0 = time.time()
ident = 1
results = []
while time.time() - t0 < secs:
    start = time.time()
    ident = (ident % 65535) + 1
    s.sendto(struct.pack(">HHHHHH", ident, 0, 1, 0, 0, 0) + qname + struct.pack(">HH", qtype, 1),
             ("224.0.0.251", 5353))
    ok = False
    while time.time() - start < 0.08:
        try:
            msg, _ = s.recvfrom(9000)
        except socket.timeout:
            continue
        if answered(msg, ident):
            ok = True
            break
    results.append((start, ok))
    print("%.6f %s" % (start, "ok" if ok else "none"), flush=True)
    time.sleep(max(0.0, 0.1 - (time.time() - start)))
# the stretches without an answer
gap = None
for t, ok in results:
    if not ok and gap is None:
        gap = t
    if ok and gap is not None:
        print("gap %.6f %.3f" % (gap, t - gap), flush=True)
        gap = None
if gap is not None:
    print("gap %.6f %.3f open" % (gap, results[-1][0] - gap), flush=True)
