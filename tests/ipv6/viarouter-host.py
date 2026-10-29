import socket, struct, sys, time, threading
IDX = socket.if_nametoindex("aros0")
r = socket.socket(socket.AF_INET6, socket.SOCK_RAW, socket.IPPROTO_ICMPV6)
r.bind(("fe80::4d54:a", 0, 0, IDX))
r.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_MULTICAST_IF, IDX)
r.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_MULTICAST_HOPS, 255)
r.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_MULTICAST_LOOP, 0)
pio = struct.pack("!BBBBIII", 3, 4, 64, 0xc0, 600, 600, 0) + socket.inet_pton(socket.AF_INET6, "2001:db8:4d54:1::")
ra = struct.pack("!BBHBBHII", 134, 0, 0, 0, 0, 600, 0, 0) + pio
u = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM); u.bind(("2001:db8:4d54:77::1", 4000)); u.settimeout(0.2)
end = time.time() + float(sys.argv[1]); got = 0; nxt = 0
while time.time() < end:
    if time.time() >= nxt:
        try: r.sendto(ra, ("ff02::1", 0, 0, IDX))
        except OSError: pass
        nxt = time.time() + 1
    try:
        data, src = u.recvfrom(100); got += 1; print("HOST got", data, "from", src[0], flush=True)
    except socket.timeout: pass
    except OSError: time.sleep(0.2)
# finish: withdraw default
try: r.sendto(struct.pack("!BBHBBHII", 134, 0, 0, 0, 0, 0, 0, 0), ("ff02::1", 0, 0, IDX))
except OSError: pass
print("HOST total", got, flush=True)
