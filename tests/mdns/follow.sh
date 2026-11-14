#!/bin/sh
# follow.sh OUTDIR - a browse that follows what it finds (sd_common's
# finder, dnssd -B and Nearby), against the host's Avahi
# (tests/mdns/avahi_follow.py drives it):
#   - 20 instances: 16 followed, 4 resolved once (1 + 16 + 4 operations of
#     the 24 a session has on the 68k); all change their TXT: at least the
#     16 followed say UPDATE; 16 go; the 4 left change again: each says
#     UPDATE (moved to the room the others left); no operation refused;
#   - an instance on a host whose addresses change: an IPv6 address added,
#     then removed, then the IPv4 one replaced - Nearby PORTS shows the
#     whole set each time, the removal included.
# MODE=amiga runs AROS m68k on the emulated Amiga (tools/amiga-run.sh),
# without timesyncd there (B35); otherwise hosted (AROS_HOSTED_IMAGE).
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
Wait 12
Run >NIL: C:dnssd -B _followtest._tcp >SYS:out/follow.log
Run >NIL: C:Nearby _addrtest._tcp PORTS >SYS:out/addr.log
Wait 90
EOS
if [ "$mode" = amiga ]; then
  delay=60
  AMIGA_TAP_IP=192.168.166.2 AMIGA_RUN_TIMEOUT=260 \
    "$root/tools/amiga-run.sh" "$out/aros" "$out/s.script" > "$out/run.txt" 2>&1 & run=$!
else
  delay=20
  AROS_TAP_IP=192.168.166.2 AROS_RUN_TIMEOUT=150 \
    "$root/tools/hosted-run.sh" "$out/aros" "$out/s.script" > "$out/run.txt" 2>&1 & run=$!
fi
# the browses start after the boot and startnet
( sleep $delay; python3 "$root/tests/mdns/avahi_follow.py" ) > "$out/avahi.txt" 2>&1 & host=$!
wait $run
kill $host 2>/dev/null

f=$out/aros/out/follow.log
n=$out/aros/out/addr.log
fails=0
count() { grep -c -- "$2" "$1" 2>/dev/null || true; }
expect() {  # expect NAME CONDITION
  if eval "$2"; then echo "PASS $1"; else echo "FAIL $1"; fails=$((fails + 1)); fi
}
adds=$(count "$f" '^ADD      F[0-9][0-9] .*v=1$')
up2=$(count "$f" '^UPDATE   F[0-9][0-9] .*v=2$')
gone=$(count "$f" '^REMOVE   F\(0[1-9]\|1[0-6]\) ')
up3=$(count "$f" '^UPDATE   F\(1[7-9]\|20\) .*v=3$')
echo "ADD v=1: $adds, UPDATE v=2: $up2, REMOVE: $gone, UPDATE v=3: $up3"
expect "20 instances found" '[ "$adds" -eq 20 ]'
# the 16 followed are told of the change at once; the other 4 (resolved
# once: the limit is a choice, sd_common.h) only if they are still there
# when room is made for them, then as they are by then
expect "the 16 followed told of the change (the others when followed)" '[ "$up2" -ge 16 ] && [ "$up2" -le 20 ]'
expect "16 withdrawn" '[ "$gone" -eq 16 ]'
expect "the 4 left, all followed now, told of the change" '[ "$up3" -eq 4 ]'
expect "no operation refused" '! grep -q "too much at once\|ended\|error" "$f"'
expect "address: IPv4 .81" 'grep -q "AddrTest .* port 7200  (192.168.166.81)$" "$n"'
expect "address added: .81 and 2001:db8::81" 'grep -q "AddrTest .* port 7200  (192.168.166.81, 2001:db8::81)$" "$n"'
expect "address removed: .81 alone again" '[ "$(grep -c "AddrTest .* port 7200  (192.168.166.81)$" "$n")" -ge 2 ]'
expect "address replaced: .82" 'grep -q "AddrTest .* port 7200  (192.168.166.82)$" "$n"'
echo "follow: $fails failed"
