#!/usr/bin/env python3
"""
addrchange_report.py OUTDIR - addrchange.sh's report: the capture split at
its marks (datagrams to the host's port 9), and per window and link the
probes for arosbox.local and the host's A/AAAA records sent - address, TTL
and how many times (from mdns_pcap.py --rdata --time). Plain Python.
"""
import sys

out = sys.argv[1]
l0 = open(out + "/pcap0.txt").read().splitlines()
t0 = float(l0[0].split()[0])
marks = [float(l.split()[0]) for l in l0 if "192.168.166.1.9: " in l]
names = ["0 boot", "1 alias add/delete", "2 same IPv4 again", "3 IPv4 on eth1", "4 mdnsd restart"]
edges = [t0] + marks + [1e18]
print("marks at (s):", ["%.1f" % (m - t0) for m in marks])
for i, link in ((0, "aros0"), (1, "aros1")):
    pl = open(out + "/pcap%d.txt" % i).read().splitlines()
    rec = [l.split() for l in open(out + "/rec%d.txt" % i)]
    for w in range(min(len(names), len(edges) - 1)):
        a, b = edges[w], edges[w + 1]
        probes = sum(1 for l in pl if a <= float(l.split()[0]) < b and "? arosbox.local." in l)
        sent = {}
        for r in rec:
            if len(r) >= 7 and a <= float(r[0]) < b:
                key = "%s %s ttl %s" % (r[3], r[6], r[5])
                sent[key] = sent.get(key, 0) + 1
        print("%-20s %s: %2d probes | %s" % (names[w], link, probes,
              "; ".join("%s x%d" % kv for kv in sorted(sent.items())) or "no host records"))
