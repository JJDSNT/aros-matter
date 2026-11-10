#!/usr/bin/env python3
"""arpsend.py IFACE MAC IP - broadcast one gratuitous ARP request from MAC
claiming IP (sender = target = IP) on IFACE: another host using IP, for
tests/ipv4/acd_probe.py. Needs root for the raw socket."""
import socket, sys

iface, mac, ip = sys.argv[1], bytes.fromhex(sys.argv[2].replace(":", "")), socket.inet_aton(sys.argv[3])
s = socket.socket(socket.AF_PACKET, socket.SOCK_RAW)
s.bind((iface, 0))
arp = (b"\x00\x01" b"\x08\x00" b"\x06\x04" b"\x00\x01" + mac + ip + b"\x00" * 6 + ip)
s.send(b"\xff" * 6 + mac + b"\x08\x06" + arp + b"\x00" * 18)
