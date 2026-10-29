#!/usr/bin/env python3
"""Host routers for the RFC 4191 bench, run as root by rfc4191.py.

  rasend.py IFACE T0
Two routers, A = fe80::4d54:a and B = fe80::4d54:b (added to IFACE by the
caller), send Router Advertisements to ff02::1 with hop limit 255 on the
schedule in PHASES: during phase p, [T0+4p, T0+4p+4), each of its RAs is sent
once a second ("once": only at the start of the phase).
"""
import socket, struct, sys, time

IFACE, T0 = sys.argv[1], float(sys.argv[2])
IDX = socket.if_nametoindex(IFACE)
A, B = "fe80::4d54:a", "fe80::4d54:b"
HIGH, MED, LOW, RSV = 0x08, 0x00, 0x18, 0x10

def rio(prefix, plen, prf, lifetime, length=None):
    if length is None:
        length = 1 if plen == 0 else (2 if plen <= 64 else 3)
    p = socket.inet_pton(socket.AF_INET6, prefix)[:(length - 1) * 8]
    return struct.pack("!BBBBI", 24, length, plen, prf, lifetime) + p

def ra(rl, prf, *opts):
    # type, code, cksum (kernel), cur hop limit 0, flags (prf), router lifetime, reachable, retrans
    return struct.pack("!BBHBBHII", 134, 0, 0, 0, prf, rl, 0, 0) + b"".join(opts)

P = "2001:db8:4d54:"
PHASES = [
    [(A, ra(0, MED, rio(P + "10::", 64, MED, 600)))],                                   # 0
    [(A, ra(0, MED, rio(P + "10::", 64, MED, 0)))],                                     # 1
    [(A, ra(0, MED, rio(P + "12::", 64, LOW, 600))), (B, ra(0, MED, rio(P + "12::", 64, HIGH, 600)))],  # 2
    [(A, ra(0, MED, rio(P + "12::", 64, LOW, 600))), (B, ra(0, MED, rio(P + "12::", 64, HIGH, 0)))],    # 3
    [(A, ra(0, MED, rio(P + "12::", 64, LOW, 0), rio(P + ":", 48, MED, 600))),
     (B, ra(0, MED, rio(P + "13::", 64, LOW, 600)))],                                    # 4
    [(A, ra(0, MED, rio(P + "14::", 64, RSV, 600), rio(P + "15::", 80, MED, 600, length=2),
            rio(P + ":", 48, MED, 0))), (B, ra(0, MED, rio(P + "13::", 64, LOW, 0)))],   # 5
    [(A, ra(600, LOW)), (B, ra(600, HIGH))],                                             # 6
    [(A, ra(600, LOW)), (B, ra(0, MED))],                                                # 7
    [(A, ra(0, MED))],                                                                   # 8
    [(A, ra(0, MED, rio("::", 0, MED, 600)))],                                           # 9
    [(A, ra(0, MED, rio("::", 0, MED, 0)))],                                             # 10
    [("once", A, ra(0, MED, rio(P + "20::", 64, MED, 3)))],                              # 11
    [],                                                                                  # 12
    [(A, ra(600, MED, rio(P + "21::", 64, MED, 600)))],                                  # 13
    [(A, ra(600, MED, rio(P + "21::", 64, MED, 600)))],                                  # 14 reload
    [(A, ra(0, MED, rio(P + "21::", 64, MED, 0)))],                                      # 15
]

socks = {}
for addr in (A, B):
    s = socket.socket(socket.AF_INET6, socket.SOCK_RAW, socket.IPPROTO_ICMPV6)
    s.bind((addr, 0, 0, IDX))
    s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_MULTICAST_IF, IDX)
    s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_MULTICAST_HOPS, 255)
    s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_MULTICAST_LOOP, 0)
    socks[addr] = s

for p, entries in enumerate(PHASES):
    for k in range(4):
        t = T0 + 4 * p + k
        while time.time() < t:
            time.sleep(max(0.0, t - time.time()))
        for e in entries:
            once = e[0] == "once"
            if once and k > 0:
                continue
            src, pkt = e[1:] if once else e
            socks[src].sendto(pkt, ("ff02::1", 0, 0, IDX))
print("rasend done", flush=True)
