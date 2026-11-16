#!/bin/sh
# hostname.sh OUTDIR - mdnsd follows the system's host name while it runs
# (B42: the stack's SBTC_SIG_HOSTNAME_CHANGE_MASK). AROS sets the name
# through AROSTCP's ARexx port (C:rexxhost, tests/stack/rexxhost.c: the
# HOSTNAME variable, set in the NETTRACE task) with no interface or address
# change; tcpdump
# records what mdnsd sends, and the checks read it in order (SYS:out/ reaches
# the host only when the run ends, so the host cannot follow the steps as
# they happen):
#   1. arosbox -> b42one: arosbox.local's goodbye (TTL 0), b42one.local
#      announced, the service registered before (_b42test._tcp) with its SRV
#      on b42one.local;
#   2. b42two then b42three at once: b42one's goodbye, b42three announced,
#      b42two never announced (the name as it is when mdnsd looks);
#   3. an IPv6 address added (its DAD running) and the name set to b42four
#      in the same moment: b42three's goodbye, b42four announced;
#   4. back to arosbox: b42four's goodbye, arosbox announced.
# The AAAA records go as the A ones; the SRV is sent again with the
# cache-flush bit and the new target (RFC 6762 sections 8.4, 10.2).
# After the run the host's Avahi resolves arosbox.local and none of the
# names given up. With RESOLVTEST (tests/mdns/resolvtest.c, the stack's
# .local resolver), AROS itself looks its new name and its old one up
# after steps 1, 3 and 4: the new one is its address, the old one is none.
# REXXHOST, RESOLVTEST: the test binaries (built for the target). AROS_HOSTED_IMAGE as for
# tools/hosted-run.sh; MODE=amiga runs AROS m68k (tools/amiga-run.sh).
set -u
out=$1; mkdir -p "$out"
root=$(cd "$(dirname "$0")/../.." && pwd)
"$root/tools/tap-up.sh" >/dev/null
mode=${MODE:-hosted}
# without RESOLVTEST its lines are comments
res=";"; files=$REXXHOST
[ -n "${RESOLVTEST:-}" ] && res="" && files="$REXXHOST $RESOLVTEST"
pre=""
[ "$mode" = amiga ] && pre="Delete >NIL: SYS:System/Network/AROSTCP/db/services.d/timesync QUIET"
cat > "$out/s.script" <<EOS
$pre
Execute SYS:System/Network/AROSTCP/S/startnet
Wait 12
Run >NIL: C:dnssd -R B42Svc _b42test._tcp . 7742 >SYS:out/register.log
Wait 4
C:rexxhost b42one >SYS:out/step1.txt
Wait 10
$res C:resolvtest b42one.local arosbox.local >SYS:out/res1.txt
C:rexxhost b42two >SYS:out/step2a.txt
C:rexxhost b42three >SYS:out/step2.txt
Wait 10
C:ifconfig eth0 inet6 2001:db8:42::5 prefixlen 64 alias
C:rexxhost b42four >SYS:out/step3.txt
Wait 10
$res C:resolvtest b42four.local b42three.local >SYS:out/res3.txt
C:rexxhost arosbox >SYS:out/step4.txt
Wait 8
$res C:resolvtest arosbox.local b42four.local >SYS:out/res4.txt
EOS
sudo -n tcpdump -i aros0 -n -w "$out/aros0.pcap" udp port 5353 >/dev/null 2>&1 & cap=$!
sleep 1
if [ "$mode" = amiga ]; then
  AMIGA_TAP_IP=192.168.166.2 AMIGA_RUN_TIMEOUT=400 \
    "$root/tools/amiga-run.sh" "$out/aros" "$out/s.script" $files > "$out/run.txt" 2>&1
else
  AROS_TAP_IP=192.168.166.2 AROS_RUN_TIMEOUT=200 \
    "$root/tools/hosted-run.sh" "$out/aros" "$out/s.script" $files > "$out/run.txt" 2>&1
fi
sleep 1
sudo -n kill $cap 2>/dev/null
sleep 1
o=$out/aros/out

# the A records mdnsd sent, in order, "NAME TTL"; the SRV targets
python3 -I "$root/tests/mdns/mdns_pcap.py" "$out/aros0.pcap" --from 192.168.166.2 --type A |
  awk '{ sub(/\.local$/, "", $2); print $2, $5 }' | uniq > "$out/a.txt"
python3 -I "$root/tests/mdns/mdns_pcap.py" "$out/aros0.pcap" --from 192.168.166.2 --type AAAA |
  awk '{ sub(/\.local$/, "", $2); print $2, $5 }' | uniq > "$out/aaaa.txt"
tcpdump -n -r "$out/aros0.pcap" src 192.168.166.2 2>/dev/null |
  grep -o "SRV [a-z0-9-]*\.local" | uniq > "$out/srv.txt"
# whether the line WANT comes after the line PREV
after() {
  awk -v prev="$1" -v want="$2" 'f && $0 == want { found = 1 } $0 == prev { f = 1 } END { exit !found }' "$out/a.txt"
}
for n in arosbox b42one b42two b42three b42four; do
  echo "$n: $(timeout 6 avahi-resolve-host-name -4 $n.local 2>/dev/null | cut -f2)"
done > "$out/host.txt"

fails=0
expect() {  # expect NAME CONDITION
  if eval "$2"; then echo "PASS $1"; else echo "FAIL $1"; fails=$((fails + 1)); fi
}
h=$out/host.txt
expect "the stack signals the name change (step 1)" 'grep -q "signal yes" "$o/step1.txt"'
expect "1: arosbox goodbye, then b42one announced" 'after "arosbox 0" "b42one 120"'
expect "1: the service's SRV on b42one.local" 'grep -q "SRV b42one.local" "$out/srv.txt"'
expect "2: b42one goodbye, then b42three announced" 'after "b42one 0" "b42three 120"'
expect "2: b42two never announced" '! grep -q "^b42two " "$out/a.txt"'
expect "3: b42three goodbye, then b42four announced" 'after "b42three 0" "b42four 120"'
expect "4: b42four goodbye, then arosbox announced" 'after "b42four 0" "arosbox 120"'
expect "AAAA: the same goodbyes and announcements as A" 'cmp -s "$out/a.txt" "$out/aaaa.txt"'
expect "after: arosbox.local resolves" 'grep -q "^arosbox: 192.168.166.2" "$h"'
expect "after: the names given up do not" '[ "$(grep -c "^b42[a-z]*: 192" "$h")" -eq 0 ]'
if [ -n "${RESOLVTEST:-}" ]; then
  own() { grep -q "^hbn $2 [0-9]* 192.168.166.2" "$o/$1"; }
  none() { grep -q "^hbn $2 [0-9]* none" "$o/$1"; }
  expect "resolver 1: b42one.local is AROS, arosbox.local none" 'own res1.txt b42one.local && none res1.txt arosbox.local'
  expect "resolver 3: b42four.local is AROS, b42three.local none" 'own res3.txt b42four.local && none res3.txt b42three.local'
  expect "resolver 4: arosbox.local is AROS, b42four.local none" 'own res4.txt arosbox.local && none res4.txt b42four.local'
fi
echo "hostname: $fails failed"
