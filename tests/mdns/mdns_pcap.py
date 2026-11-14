#!/usr/bin/env python3
"""
mdns_pcap.py - the mDNS records in a capture, as they were sent.

    mdns_pcap.py PCAP [--from ADDR] [--name SUFFIX] [--type TYPE]

Reads a pcap (Ethernet, IPv4 or IPv6, UDP 5353) and prints one line per
resource record of each response: source address, owner name, type, class
(with the cache-flush bit) and TTL. --from keeps the packets of one source,
--name the records whose owner ends with SUFFIX (case ignored), --type the
records of one type (A, AAAA, PTR, SRV, TXT or a number). Plain Python, no
packages.
"""
import argparse
import ipaddress
import struct
import sys

TYPES = {1: "A", 12: "PTR", 16: "TXT", 28: "AAAA", 33: "SRV", 255: "ANY"}


def packets(path):
    with open(path, "rb") as f:
        head = f.read(24)
        magic = struct.unpack("<I", head[:4])[0]
        endian = "<" if magic in (0xa1b2c3d4, 0xa1b23c4d) else ">"
        while True:
            rec = f.read(16)
            if len(rec) < 16:
                return
            _, _, incl, _ = struct.unpack(endian + "IIII", rec)
            yield f.read(incl)


def udp_5353(frame):
    """(source address, DNS message) of an mDNS datagram, or None."""
    if len(frame) < 14:
        return None
    ethertype = struct.unpack(">H", frame[12:14])[0]
    data = frame[14:]
    if ethertype == 0x0800 and len(data) >= 20:
        ihl = (data[0] & 15) * 4
        if data[9] != 17:
            return None
        src = str(ipaddress.IPv4Address(data[12:16]))
        udp = data[ihl:]
    elif ethertype == 0x86dd and len(data) >= 40:
        if data[6] != 17:
            return None
        src = str(ipaddress.IPv6Address(data[8:24]))
        udp = data[40:]
    else:
        return None
    if len(udp) < 8 or struct.unpack(">H", udp[2:4])[0] != 5353:
        return None
    return src, udp[8:]


def name_at(msg, at):
    labels, end, jumps = [], None, 0
    while at < len(msg) and jumps < 64:
        n = msg[at]
        if n & 0xc0 == 0xc0:
            if end is None:
                end = at + 2
            at = ((n & 0x3f) << 8) | msg[at + 1]
            jumps += 1
            continue
        if n == 0:
            return ".".join(labels), (end if end is not None else at + 1)
        labels.append(msg[at + 1:at + 1 + n].decode("utf-8", "replace"))
        at += 1 + n
    raise ValueError("bad name")


def records(msg):
    """The answer, authority and additional records of a response."""
    if len(msg) < 12:
        return
    _, flags, qd, an, ns, ar = struct.unpack(">HHHHHH", msg[:12])
    if not flags & 0x8000:
        return
    at = 12
    for _ in range(qd):
        _, at = name_at(msg, at)
        at += 4
    for _ in range(an + ns + ar):
        owner, at = name_at(msg, at)
        rtype, rclass, ttl, length = struct.unpack(">HHIH", msg[at:at + 10])
        at += 10 + length
        yield owner, rtype, rclass, ttl


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pcap")
    ap.add_argument("--from", dest="source")
    ap.add_argument("--name")
    ap.add_argument("--type")
    args = ap.parse_args()
    want = None
    if args.type:
        want = int(args.type) if args.type.isdigit() else \
            {v: k for k, v in TYPES.items()}[args.type.upper()]
    for frame in packets(args.pcap):
        got = udp_5353(frame)
        if got is None:
            continue
        src, msg = got
        if args.source and src != args.source:
            continue
        try:
            for owner, rtype, rclass, ttl in records(msg):
                if args.name and not owner.lower().endswith(args.name.lower()):
                    continue
                if want is not None and rtype != want:
                    continue
                print(src, owner, TYPES.get(rtype, rtype),
                      ("IN-flush" if rclass & 0x8000 else "IN"), ttl)
        except (ValueError, struct.error, IndexError):
            continue


if __name__ == "__main__":
    sys.exit(main())
