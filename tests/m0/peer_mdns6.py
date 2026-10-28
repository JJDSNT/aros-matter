#!/usr/bin/env python3
"""Host side of ipv6probe's link test: joins ff02::fb on IFACE, reports what
AROS sends, and sends 'host-mdns6' to the group once a second (no loopback)."""
import socket, struct, sys, time, select
iface = sys.argv[1] if len(sys.argv) > 1 else "aros0"
secs = int(sys.argv[2]) if len(sys.argv) > 2 else 90
idx = socket.if_nametoindex(iface)
s = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
s.bind(("::", 5353))
s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_JOIN_GROUP, socket.inet_pton(socket.AF_INET6, "ff02::fb") + struct.pack("@I", idx))
s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_MULTICAST_IF, idx)
s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_MULTICAST_LOOP, 0)
end, seen, sent, next_send = time.time() + secs, False, 0, 0.0
while time.time() < end:
    now = time.time()
    if now >= next_send:
        next_send = now + 1.0
        try:
            s.sendto(b"host-mdns6", ("ff02::fb", 5353, 0, idx)); sent += 1
        except OSError:
            pass  # tap is down until AROS opens it
    r, _, _ = select.select([s], [], [], max(0.0, next_send - time.time()))
    if r:
        data, src = s.recvfrom(256)
        if data == b"aros-mdns6" and not seen:
            print(f"HOST got aros-mdns6 from {src[0]} port {src[1]}", flush=True)
            seen = True
print(f"HOST result: {'received' if seen else 'nothing from AROS'}; sent {sent} datagrams", flush=True)
