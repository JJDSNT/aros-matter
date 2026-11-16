#!/bin/sh
# ipv4only.sh OUTDIR - the host's name to a listener on IPv4 alone (B62).
# The host listens to mDNS on IPv4 only (tests/mdns/ipv4_listen.py, from
# before AROS starts) and, once AROS's IPv4 address is long ready, asks
# for arosbox.local's A record over IPv4. A capture (mDNS and ARP) gives:
#   - when the IPv4 address was ready: AROS's ARP announcement of it after
#     its probes (RFC 5227);
#   - what mdnsd sent for the host's name over IPv4 and over IPv6.
# Expected (RFC 6762 section 8.3, announcing on a change of connectivity):
# the name announced over IPv4 once the address is ready, so that the IPv4
# listener hears it unasked; and the IPv4 question answered.
# AROS_HOSTED_IMAGE as for tools/hosted-run.sh; MODE=amiga runs AROS m68k.
set -u
out=$1; mkdir -p "$out"
root=$(cd "$(dirname "$0")/../.." && pwd)
"$root/tools/tap-up.sh" >/dev/null
mode=${MODE:-hosted}
pre=""
[ "$mode" = amiga ] && pre="Delete >NIL: SYS:System/Network/AROSTCP/db/services.d/timesync QUIET"
# AROS stays up past the question (the m68k boot is longer)
[ "$mode" = amiga ] && stay=110 || stay=40
cat > "$out/s.script" <<EOS
$pre
Execute SYS:System/Network/AROSTCP/S/startnet
Wait $stay
EOS
if [ "$mode" = amiga ]; then secs=150; ask=100; else secs=60; ask=40; fi
sudo -n tcpdump -i aros0 -n -w "$out/aros0.pcap" 'udp port 5353 or arp' >/dev/null 2>&1 & cap=$!
python3 -I "$root/tests/mdns/ipv4_listen.py" 192.168.166.1 arosbox.local $secs $ask > "$out/listen.txt" 2>&1 & lis=$!
sleep 1
if [ "$mode" = amiga ]; then
  AMIGA_TAP_IP=192.168.166.2 AMIGA_RUN_TIMEOUT=260 \
    "$root/tools/amiga-run.sh" "$out/aros" "$out/s.script" > "$out/run.txt" 2>&1 &
else
  AROS_TAP_IP=192.168.166.2 AROS_RUN_TIMEOUT=100 \
    "$root/tools/hosted-run.sh" "$out/aros" "$out/s.script" > "$out/run.txt" 2>&1 &
fi
run=$!
wait $lis
wait $run
sleep 1
sudo -n kill $cap 2>/dev/null
sleep 1
tcpdump -tt -n -r "$out/aros0.pcap" 2>/dev/null > "$out/pcap.txt"
python3 -I - "$out" <<'EOF'
import sys
out = sys.argv[1]
lines = open(out + "/pcap.txt").read().splitlines()
t0 = float(lines[0].split()[0]) if lines else 0
def t(l): return float(l.split()[0]) - t0
ready = [t(l) for l in lines if " ARP, " in l and "Announcement 192.168.166.2" in l
         or (" ARP, Request who-has 192.168.166.2 tell 192.168.166.2" in l)]
probes = [t(l) for l in lines if " ARP, " in l and "who-has 192.168.166.2 tell 0.0.0.0" in l]
print("IPv4 ACD probes at: %s" % ["%.1f" % x for x in probes])
print("IPv4 ready (ARP announcement) at: %s" % ["%.1f" % x for x in ready[:2]])
for fam, src in (("IPv4", "192.168.166.2.5353 > 224.0.0.251"), ("IPv6", ".5353 > ff02::fb")):
    hp = [t(l) for l in lines if src in l and "? arosbox.local." in l]
    ha = [t(l) for l in lines if src in l and " 0*- " in l and (" A 192.168.166.2" in l or "AAAA" in l)
          and not "PTR" in l]
    print("%s: host-name probes %s, host announcements/answers %s" % (fam,
          ["%.1f" % x for x in hp][:6], ["%.1f" % x for x in ha][:8]))
EOF
# the listener's packets on the capture's time (both the host's clock)
python3 -I - "$out" <<'EOF'
import sys
out = sys.argv[1]
lines = open(out + "/pcap.txt").read().splitlines()
t0 = float(lines[0].split()[0]) if lines else 0
print("IPv4-only listener (seconds on the capture's time):")
for l in open(out + "/listen.txt"):
    p = l.split()
    at = [x for x in p if x.startswith("at=")]
    print("  %.2f %s" % (float(at[0][3:]) - t0, " ".join(x for x in p if not x.startswith(("t=", "at=")))) if at else "  " + l.strip())
EOF
