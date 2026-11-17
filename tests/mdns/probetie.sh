#!/bin/sh
# probetie.sh OUTDIR LOSE|WIN|WIN4 - another host probes for arosbox.local
# while AROS does (RFC 6762 section 8.2): hosted AROS, eth0 on aros0 (eth1 on
# aros1, its own segment); from the Linux host on aros0, for the first 40 s
# of the run, a probe every 250 ms (tests/mdns/probetie.py) with
#   LOSE: A 192.168.166.1, by IPv4 and IPv6 - sorts before AROS's records in
#         either family: AROS wins, announces arosbox.local and keeps it;
#   WIN:  AAAA fe80::ffff:ffff:ffff:ffff, by IPv4 and IPv6 - sorts after
#         AROS's in either family: AROS defers on eth0 by both families
#         while the other probes; when it then announces the name, AROS takes
#         arosbox-2 (one other name, not more);
#   WIN4: A 192.168.166.250, by IPv4 alone - AROS's IPv6 has the name on eth0
#         before its IPv4 is ready (conflict detection), the other host's
#         IPv6 listeners being none: the name is AROS's on that link, so its
#         IPv4 answers the other's probes in its defence instead of deferring;
#         when the other announces anyway, AROS takes arosbox-2.
# Prints PASS/FAIL.
set -u
out=$1; case=$2; mkdir -p "$out"
root=$(cd "$(dirname "$0")/../.." && pwd)
"$root/tools/tap-up.sh" 0 >/dev/null; "$root/tools/tap-up.sh" 1 >/dev/null
case $case in
  LOSE) addr=192.168.166.1; fams=46; ann= ;;
  WIN) addr=fe80::ffff:ffff:ffff:ffff; fams=46; ann=announce ;;
  WIN4) addr=192.168.166.250; fams=4; ann=announce ;;
  *) echo "LOSE, WIN or WIN4" >&2; exit 2 ;;
esac
cat > "$out/s.script" <<EOS
Execute SYS:System/Network/AROSTCP/S/startnet
Wait 60
C:dnssd -G v4 arosbox.local >SYS:out/self.log
C:dnssd -G v4 arosbox-2.local >SYS:out/self2.log
EOS
sudo -n tcpdump -i aros0 -n -w "$out/aros0.pcap" udp port 5353 >/dev/null 2>&1 & c0=$!
sudo -n tcpdump -i aros1 -n -w "$out/aros1.pcap" udp port 5353 >/dev/null 2>&1 & c1=$!
python3 -I "$root/tests/mdns/probetie.py" 192.168.166.1 aros0 arosbox.local $addr 40 $fams $ann > "$out/inject.txt" 2>&1 & inj=$!
sleep 1
AROS_TAP_IP=192.168.166.2 AROS_TAP2_IP=192.168.167.2 AROS_RUN_TIMEOUT=150 \
  "$root/tools/hosted-run.sh" "$out/aros" "$out/s.script" > "$out/run.txt" 2>&1
wait $inj; sleep 1; sudo -n kill $c0 $c1 2>/dev/null; sleep 1
for i in 0 1; do python3 -I "$root/tests/mdns/mdns_pcap.py" "$out/aros$i.pcap" --name local --rdata --time > "$out/rec$i.txt"; done
fails=0
ok() { echo "PASS $*"; }
no() { echo "FAIL $*"; fails=$((fails + 1)); }
t_end=$(grep probe "$out/inject.txt" | tail -1 | cut -d' ' -f1)
# the Linux host's own addresses on aros0: what it sent is not AROS's
mine=$( (echo 192.168.166.1; ip -6 -o addr show dev aros0 | awk '{sub("/.*", "", $4); print $4}') | tr '\n' '|' | sed 's/|$//')
grep -Ev " ($mine) " "$out/rec0.txt" | awk '$6 != 0' > "$out/aros0.txt"
grep -Ev " ($mine) " "$out/rec1.txt" | awk '$6 != 0' > "$out/aros1.txt"
names=$(cat "$out/aros0.txt" "$out/aros1.txt" | awk '{print $3}' | grep "^arosbox" | sort -u | tr '\n' ' ')
echo "== AROS announced: $names"
early=$(awk -v e="$t_end" '$1 < e && $3 == "arosbox.local"' "$out/aros0.txt")
early4=$(echo "$early" | awk '$2 == "192.168.166.2"' | grep -c .)
early6=$(echo "$early" | awk '$2 != "192.168.166.2"' | grep -c .)
echo "== on eth0 while the other probed: arosbox.local records by IPv4 $early4, by IPv6 $early6"
case $case in
  LOSE)
    [ "$names" = "arosbox.local " ] && ok "kept arosbox.local, no other name" || no "names: $names"
    grep -q "^arosbox.local" "$out/aros/out/self.log" && ok "arosbox.local resolves on AROS" || no "self: $(cat "$out/aros/out/self.log")" ;;
  WIN)
    [ "$early4" -eq 0 ] && [ "$early6" -eq 0 ] && ok "deferred on eth0 by both families while the other probed" ||
      no "announced on eth0 while the other probed (IPv4 $early4, IPv6 $early6)" ;;
  WIN4)
    [ "$early6" -gt 0 ] && [ "$early4" -gt 0 ] && ok "the name AROS's on eth0 by IPv6 first, defended by IPv4 against the other's probes" ||
      no "IPv6 $early6, IPv4 defence $early4" ;;
esac
if [ "$case" != LOSE ]; then
  echo "$names" | grep -q "arosbox-2.local" && ! echo "$names" | grep -q "arosbox-3" && ok "took arosbox-2.local, and no further name" || no "names: $names"
  grep -q "^arosbox-2.local" "$out/aros/out/self2.log" && ok "arosbox-2.local resolves on AROS" || no "self2: $(cat "$out/aros/out/self2.log")"
fi
echo "probetie $case: $fails failed"
