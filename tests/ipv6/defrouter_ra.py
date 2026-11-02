#!/usr/bin/env python3
"""Host routers for the default router bench, run as root by defrouter.py.

  defrouter_ra.py IFACE T0 LIVE DEAD BACK SECONDS
DEAD, the preferred router (high preference), sends one Router Advertisement
at T0, with a Source Link-Layer Address option naming a MAC nobody has, and
is gone: the address is added to IFACE only to send it. LIVE, the host's
own link-local address (low preference), advertises every 2 s, with the
prefix 2001:db8:4d54:1::/64 for AROS's address. At T0+BACK DEAD comes back -
added to IFACE, so the host answers Neighbor Solicitations for it - but
sends no Router Advertisements: only AROS's probe can find it.
"""
import socket, struct, subprocess, sys, time

IFACE, T0, LIVE, DEAD = sys.argv[1], float(sys.argv[2]), sys.argv[3], sys.argv[4]
BACK, SECONDS = float(sys.argv[5]), float(sys.argv[6])
IDX = socket.if_nametoindex(IFACE)
HIGH, LOW = 0x08, 0x18
FAKE_MAC = bytes.fromhex("02004d54000d")


def ra(rl, prf, *opts):
    return struct.pack("!BBHBBHII", 134, 0, 0, 0, prf, rl, 0, 0) + b"".join(opts)


def sllao(mac):
    return struct.pack("!BB", 1, 1) + mac


def pio(prefix, plen, valid, preferred):
    return struct.pack("!BBBBIII", 3, 4, plen, 0xc0, valid, preferred, 0) + \
        socket.inet_pton(socket.AF_INET6, prefix)


def sock(addr):
    s = socket.socket(socket.AF_INET6, socket.SOCK_RAW, socket.IPPROTO_ICMPV6)
    s.bind((addr, 0, 0, IDX))
    s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_MULTICAST_IF, IDX)
    s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_MULTICAST_HOPS, 255)
    s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_MULTICAST_LOOP, 0)
    return s


def addr(op):
    subprocess.run(["ip", "-6", "addr", op, DEAD + "/64", "dev", IFACE] + (["nodad"] if op == "add" else []),
                   stderr=subprocess.DEVNULL)


while time.time() < T0:
    time.sleep(0.05)
if DEAD != "none":           # "none": the control run, LIVE alone
    addr("add")
    time.sleep(0.2)
    d = sock(DEAD)
    d.sendto(ra(600, HIGH, sllao(FAKE_MAC)), ("ff02::1", 0, 0, IDX))
    d.close()
    time.sleep(0.2)
    addr("del")
    print("dead advertised", flush=True)

live = sock(LIVE)
back = False
t = T0 + 0.5
while t < T0 + SECONDS:
    while time.time() < t:
        time.sleep(max(0.0, t - time.time()))
    if not back and DEAD != "none" and time.time() >= T0 + BACK:
        addr("add")
        back = True
        print("dead back at %.1f" % (time.time() - T0), flush=True)
    live.sendto(ra(600, LOW, pio("2001:db8:4d54:1::", 64, 3600, 3600)), ("ff02::1", 0, 0, IDX))
    t += 2
if DEAD != "none":
    addr("del")
print("defrouter_ra done", flush=True)
