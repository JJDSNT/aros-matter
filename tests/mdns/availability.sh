#!/bin/sh
# availability.sh OUTDIR - does the host keep answering on a link whose
# addresses did not change (B76)? Hosted AROS with eth0 (192.168.166.2) and
# eth1 (192.168.167.2); the host asks for arosbox.local on aros1 every
# 100 ms (tests/mdns/avail.py, legacy questions answered by unicast) while,
# on eth0 only, an alias is added, kept 6 s and deleted. A capture of both
# links gives the probes and announcements on each. Expected: eth1 answers
# all along and sees no probes; eth0's records change only in what changed.
# Prints the stretches on aros1 without an answer (on the capture's clock)
# and the probes per link after the alias was added.
# RESOLVTEST, B67WAIT: the test binaries (built for the target).
set -u
out=$1; mkdir -p "$out"
root=$(cd "$(dirname "$0")/../.." && pwd)
"$root/tools/tap-up.sh" 0 >/dev/null; "$root/tools/tap-up.sh" 1 >/dev/null
cat > "$out/s.script" <<EOS
Execute SYS:System/Network/AROSTCP/S/startnet
Wait 20
C:resolvtest -T 192.168.166.1 mark1.example >NIL:
C:b67wait addr eth0 192.168.166.79 6 >SYS:out/alias.txt
Wait 6
C:resolvtest -T 192.168.166.1 mark2.example >NIL:
Wait 1
EOS
sudo -n tcpdump -i aros0 -n -w "$out/aros0.pcap" 'udp port 5353 or arp or udp port 9' >/dev/null 2>&1 & cap0=$!
sudo -n tcpdump -i aros1 -n -w "$out/aros1.pcap" 'udp port 5353' >/dev/null 2>&1 & cap1=$!
python3 -I "$root/tests/mdns/avail.py" 192.168.167.1 arosbox.local 192.168.167.2 60 > "$out/avail.txt" 2>&1 & av=$!
sleep 1
AROS_TAP_IP=192.168.166.2 AROS_TAP2_IP=192.168.167.2 AROS_RUN_TIMEOUT=200 \
  "$root/tools/hosted-run.sh" "$out/aros" "$out/s.script" "$RESOLVTEST" "$B67WAIT" > "$out/run.txt" 2>&1
wait $av
sleep 1
sudo -n kill $cap0 $cap1 2>/dev/null
sleep 1
for i in 0 1; do tcpdump -tt -n -r "$out/aros$i.pcap" 2>/dev/null > "$out/pcap$i.txt"; done
python3 -I - "$out" <<'PYEOF'
import sys
out = sys.argv[1]
l0 = open(out + "/pcap0.txt").read().splitlines()
t0 = float(l0[0].split()[0])
marks = [float(l.split()[0]) for l in l0 if "192.168.166.1.9: " in l]
print("alias added at %.1f s, done at %.1f s (capture's clock)" % (marks[0] - t0, marks[1] - t0))
first_ok = None
for l in open(out + "/avail.txt"):
    p = l.split()
    if p and p[1] == "ok" and first_ok is None:
        first_ok = float(p[0])
gaps = [l.split() for l in open(out + "/avail.txt") if l.startswith("gap ")]
print("aros1 without an answer, after it first answered:")
n = 0
for g in gaps:
    t = float(g[1])
    if first_ok is not None and t > first_ok:
        print("  at %.2f s for %.2f s%s" % (t - t0, float(g[2]), " (still)" if len(g) > 3 else ""))
        n += 1
if not n:
    print("  none")
for i, link in ((0, "aros0"), (1, "aros1")):
    pl = open(out + "/pcap%d.txt" % i).read().splitlines()
    pr = [float(l.split()[0]) - t0 for l in pl if "? arosbox.local." in l and float(l.split()[0]) >= marks[0]
          and l.split()[2].startswith(("192.168.166.2.", "192.168.167.2.", "fe80"))]
    print("%s: %d probes after the alias was added%s" % (link, len(pr),
          (" (at " + ", ".join("%.1f" % x for x in pr[:12]) + ")") if pr else ""))
PYEOF
