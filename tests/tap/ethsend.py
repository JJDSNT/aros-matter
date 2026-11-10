#!/usr/bin/env python3
"""ethsend.py IFACE TYPE INTERVAL SECS - broadcast an Ethernet frame of
ethertype TYPE (hex) on IFACE every INTERVAL seconds for SECS seconds (for
tests/tap/hold_probe.py; needs root for the raw socket)."""
import socket, sys, time

iface, etype, interval, secs = sys.argv[1], int(sys.argv[2], 16), float(sys.argv[3]), float(sys.argv[4])
s = socket.socket(socket.AF_PACKET, socket.SOCK_RAW)
s.bind((iface, 0))
src = s.getsockname()[4]
end = time.monotonic() + secs
n = 0
while time.monotonic() < end:
    s.send(b"\xff" * 6 + src + etype.to_bytes(2, "big") + b"hold-probe %06d" % n + b"\0" * 30)
    n += 1
    time.sleep(interval)
print("sent", n)
