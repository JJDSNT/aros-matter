#!/bin/sh
# clockstep.sh OUTDIR - mdnsd and a change of the time of day (B72): three
# cases on hosted AROS against the host's Avahi, each with the clock set an
# hour away and back (C:clockstep, tests/stack/clockstep.c):
#   1. a look-up of a missing name (3 s deadline), the clock set back an
#      hour a second in, and forward again 10 s later: how long it took;
#   2. a browse (dnssd -B) of a service the host's Avahi publishes, the
#      clock set forward an hour: whether the browse is told the service
#      went (a REMOVE), and the host's records' goodbye or not;
#   3. a rename (C:rexxhost) and the clock set back an hour at once: when
#      the new name's probes and announcement go out (the capture).
# RESOLVTEST, REXXHOST, CLOCKSTEP: the test binaries (built for the target).
# MODE=amiga runs AROS m68k on the emulated Amiga (tools/amiga-run.sh).
# Prints what happened; with mdnsd on the monotonic clock: 1. 3 s, 2. no
# REMOVE, 3. probes 280 ms apart (MDNS_PROBE_TICKS) right after the rename.
set -u
out=$1; mkdir -p "$out"
root=$(cd "$(dirname "$0")/../.." && pwd)
"$root/tools/tap-up.sh" >/dev/null
mode=${MODE:-hosted}
pre=""
[ "$mode" = amiga ] && pre="Delete >NIL: SYS:System/Network/AROSTCP/db/services.d/timesync QUIET"
cat > "$out/s.script" <<EOS
$pre
Execute SYS:System/Network/AROSTCP/S/startnet
Wait 15
Run >NIL: C:resolvtest -T 192.168.166.1 nobody-clock.local >SYS:out/c1.txt
Wait 1
C:clockstep -3600 >SYS:out/c1a.txt
Wait 10
C:clockstep 3600 >SYS:out/c1b.txt
Wait 4
Run >NIL: C:dnssd -B _clocktest._tcp >SYS:out/browse.log
Wait 6
C:clockstep 3600 >SYS:out/c2a.txt
Wait 8
C:clockstep -3600 >SYS:out/c2b.txt
Wait 4
C:rexxhost clockname >SYS:out/c3.txt
C:clockstep -3600 >SYS:out/c3a.txt
Wait 10
C:clockstep 3600 >SYS:out/c3b.txt
Wait 6
C:rexxhost arosbox >SYS:out/c4.txt
Wait 4
EOS
avahi-publish-service ClockSvc _clocktest._tcp 7799 >/dev/null 2>&1 & pub=$!
sudo -n tcpdump -i aros0 -n -w "$out/aros0.pcap" 'udp port 5353 or udp port 9' >/dev/null 2>&1 & cap=$!
sleep 1
if [ "$mode" = amiga ]; then
  AMIGA_TAP_IP=192.168.166.2 AMIGA_RUN_TIMEOUT=300 \
    "$root/tools/amiga-run.sh" "$out/aros" "$out/s.script" "$RESOLVTEST" "$REXXHOST" "$CLOCKSTEP" > "$out/run.txt" 2>&1
else
  AROS_TAP_IP=192.168.166.2 AROS_RUN_TIMEOUT=200 \
    "$root/tools/hosted-run.sh" "$out/aros" "$out/s.script" "$RESOLVTEST" "$REXXHOST" "$CLOCKSTEP" > "$out/run.txt" 2>&1
fi
sleep 1
sudo -n kill $cap 2>/dev/null
kill $pub 2>/dev/null
sleep 1                 # tcpdump writes out what it still holds
o=$out/aros/out
echo "1. look-up of a missing name, clock back 1 h after 1 s, forward again 10 s later:"
grep "^T " "$o/c1.txt" | awk '{print "   took " $4 " ms (" $5 ")"}'
echo "2. browse, clock forward 1 h:"
echo "   $(grep -c "^ADD" "$o/browse.log") ADD, $(grep -c "^REMOVE" "$o/browse.log") REMOVE"
echo "3. rename to clockname, clock back 1 h at once (forward again 10 s later):"
tcpdump -tt -n -r "$out/aros0.pcap" 2>/dev/null | grep "? clockname.local." | awk '{print $1}' > "$out/c3probes.txt"
t0=$(tcpdump -tt -n -r "$out/aros0.pcap" 2>/dev/null | grep "? clockname.local." | head -1 | awk '{print $1}')
echo "   probes for clockname.local: $(wc -l < "$out/c3probes.txt"), at (s after the first):" \
  $(awk -v t0="${t0:-0}" '{printf "%.2f ", $1 - t0}' "$out/c3probes.txt")
grep -h "step" "$o"/c*.txt | sort | uniq -c | awk '{print "   clockstep:", $0}'
