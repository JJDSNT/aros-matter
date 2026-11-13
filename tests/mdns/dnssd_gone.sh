#!/bin/sh
# dnssd_gone.sh OUTDIR - dnssd.library clients that go without closing
# (tests/mdns/dnssd_gone.c): a child task removed by force, one that exits;
# mdnsd must let their sessions and operations go at once (TNA_REMOVED), and
# send the registered service's goodbye - the host's Avahi, watching
# _gonetest._tcp the whole time, sees it come ("+") and go ("-") each time.
# AROS_HOSTED_IMAGE as for tools/hosted-run.sh; MODE=amiga runs AROS m68k on
# the emulated Amiga (tools/amiga-run.sh). DNSSD_GONE: the test binary built
# for the target.
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
C:dnssd_gone removed >SYS:out/removed.log
Wait 3
C:dnssd_gone exits >SYS:out/exits.log
Wait 3
EOS
avahi-browse -p -k _gonetest._tcp > "$out/avahi.txt" 2>/dev/null & watch=$!
if [ "$mode" = amiga ]; then
    AMIGA_TAP_IP=192.168.166.2 AMIGA_RUN_TIMEOUT=300 \
        "$root/tools/amiga-run.sh" "$out/aros" "$out/s.script" "$DNSSD_GONE" > "$out/run.txt" 2>&1
else
    AROS_TAP_IP=192.168.166.2 AROS_RUN_TIMEOUT=120 \
        "$root/tools/hosted-run.sh" "$out/aros" "$out/s.script" "$DNSSD_GONE" > "$out/run.txt" 2>&1
fi
sleep 2
kill $watch 2>/dev/null
for c in removed exits; do echo "== $c"; cat "$out/aros/out/$c.log" 2>/dev/null; done
echo "== avahi (_gonetest._tcp on aros0)"
grep "aros0" "$out/avahi.txt" | grep "Gone"
adds=$(grep -c "^+;aros0;IPv4;Gone" "$out/avahi.txt")
gone=$(grep -c "^-;aros0;IPv4;Gone" "$out/avahi.txt")
echo "IPv4: came $adds times, went $gone times"
[ "$adds" -ge 2 ] && [ "$gone" -eq "$adds" ] && echo "PASS each went with its goodbye" || echo "FAIL goodbyes: $gone of $adds"
