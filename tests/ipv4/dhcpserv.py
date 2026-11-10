#!/usr/bin/env python3
"""
dhcpserv.py IFACE SERVER-IP POOL-FIRST POOL-LAST SECS LOG - a minimal DHCPv4
server for tests/ipv4/dhcp_decline_probe.py, on one interface only.

It offers the lowest address of the pool not declined and not leased to
another client, acknowledges a request for it, and on a DHCPDECLINE marks
the address declined (RFC 2131 section 4.3.3: not offered again). Each
message received or sent is a JSON line in LOG. Runs SECS seconds. Needs
root (port 67, SO_BINDTODEVICE).
"""
import ipaddress, json, socket, struct, sys, time

iface, server, first, last, secs, logpath = sys.argv[1:7]
server_b = socket.inet_aton(server)
pool = [str(ipaddress.IPv4Address(i)) for i in range(int(ipaddress.IPv4Address(first)), int(ipaddress.IPv4Address(last)) + 1)]
declined, leases = set(), {}
names = {1: "DISCOVER", 2: "OFFER", 3: "REQUEST", 4: "DECLINE", 5: "ACK", 6: "NAK", 7: "RELEASE", 8: "INFORM"}
log = open(logpath, "a", buffering=1)


def note(**kw):
    kw["t"] = round(time.time(), 3)
    log.write(json.dumps(kw) + "\n")


def options(raw):
    out, i = {}, 0
    while i < len(raw):
        code = raw[i]
        if code == 255:
            break
        if code == 0:
            i += 1
            continue
        n = raw[i + 1]
        out[code] = raw[i + 2:i + 2 + n]
        i += 2 + n
    return out


def reply(sock, req, mtype, yiaddr):
    xid, chaddr = req[4:8], req[28:44]
    pkt = struct.pack("!BBBB", 2, 1, 6, 0) + xid + b"\x00\x00" + b"\x80\x00" + b"\x00" * 4
    pkt += socket.inet_aton(yiaddr) + server_b + b"\x00" * 4 + chaddr + b"\x00" * 192
    pkt += b"\x63\x82\x53\x63"
    pkt += bytes([53, 1, mtype, 54, 4]) + server_b + bytes([51, 4]) + struct.pack("!I", 3600)
    pkt += bytes([1, 4]) + socket.inet_aton("255.255.255.0") + b"\xff"
    sock.sendto(pkt, ("255.255.255.255", 68))
    note(sent=names[mtype], yiaddr=yiaddr)


s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
s.setsockopt(socket.SOL_SOCKET, 25, iface.encode() + b"\0")    # SO_BINDTODEVICE
s.bind(("0.0.0.0", 67))
s.settimeout(0.5)
end = time.time() + float(secs)
while time.time() < end:
    try:
        req, _ = s.recvfrom(1500)
    except socket.timeout:
        continue
    if len(req) < 240 or req[0] != 1 or req[236:240] != b"\x63\x82\x53\x63":
        continue
    opt = options(req[240:])
    mtype = opt.get(53, b"\x00")[0]
    mac = req[28:34].hex(":")
    asked = socket.inet_ntoa(opt[50]) if 50 in opt else None
    note(got=names.get(mtype, str(mtype)), mac=mac, requested=asked)
    if mtype == 4:                      # DECLINE: the address is in use
        if asked:
            declined.add(asked)
            leases.pop(mac, None)
        continue
    free = [a for a in pool if a not in declined and (leases.get(mac) == a or a not in leases.values())]
    if mtype == 1 and free:
        addr = leases.get(mac) if leases.get(mac) in free else free[0]
        leases[mac] = addr
        reply(s, req, 2, addr)
    elif mtype == 3:
        want = asked or socket.inet_ntoa(req[12:16])
        if want in free:
            leases[mac] = want
            reply(s, req, 5, want)
        else:
            reply(s, req, 6, "0.0.0.0")
