#!/bin/sh
# interop.sh OUTDIR - mdnsd on hosted AROS (tap aros0) against the host's
# Avahi, both ways: the host resolves AROS's name (A, AAAA) and browses a
# service AROS registers; AROS browses a service the host publishes and looks
# the host's name up. AROS_HOSTED_IMAGE as for tools/hosted-run.sh; MODE=amiga
# runs AROS m68k on the emulated Amiga instead (tools/amiga-run.sh, A2065 on
# aros0), without timesyncd there (B35). TWO=1 (hosted) adds eth1 on tap
# aros1 (192.168.167.2): each link must see that link's address.
set -u
out=$1; mkdir -p "$out"
root=$(cd "$(dirname "$0")/../.." && pwd)
"$root/tools/tap-up.sh" >/dev/null
[ "${TWO:-0}" = 1 ] && { "$root/tools/tap-up.sh" 1 >/dev/null; export AROS_TAP2_IP=192.168.167.2; }
# the name the host's Avahi holds on aros0: after a conflict (another
# machine of the same name, e.g. Windows under WSL) it is not hostname's
host=$(avahi-resolve -4 -a 192.168.166.1 2>/dev/null | awk '{print $2}')
host=${host%.local}
[ -n "$host" ] || host=$(hostname)
mode=${MODE:-hosted}
pre=""
[ "$mode" = amiga ] && pre="Delete >NIL: SYS:System/Network/AROSTCP/db/services.d/timesync QUIET"
cat > "$out/s.script" <<EOS
$pre
Execute SYS:System/Network/AROSTCP/S/startnet
Wait 12
Run >NIL: C:dnssd -R AROSTest _arostest._tcp . 8080 -t 60 path=/ >SYS:out/register.log
Run >NIL: C:dnssd -B _hosttest._tcp >SYS:out/browse.log
Wait 15
C:dnssd -G v4 $host.local >SYS:out/lookup.log
Wait 20
EOS
avahi-publish-service HostTest _hosttest._tcp 9999 vers=1 >/dev/null 2>&1 & pub=$!
if [ "$mode" = amiga ]; then
  AMIGA_TAP_IP=192.168.166.2 AMIGA_RUN_TIMEOUT=200 \
    "$root/tools/amiga-run.sh" "$out/aros" "$out/s.script" > "$out/run.txt" 2>&1 & run=$!
  sleep 70
else
  AROS_TAP_IP=192.168.166.2 AROS_RUN_TIMEOUT=150 \
    "$root/tools/hosted-run.sh" "$out/aros" "$out/s.script" > "$out/run.txt" 2>&1 & run=$!
  sleep 40
fi
avahi-resolve -4 -n arosbox.local > "$out/host-resolve4.txt" 2>&1
avahi-resolve -6 -n arosbox.local > "$out/host-resolve6.txt" 2>&1
timeout 10 avahi-browse -rpt _arostest._tcp > "$out/host-browse.txt" 2>&1
wait $run
kill $pub 2>/dev/null
for f in host-resolve4 host-resolve6 host-browse; do echo "== $f"; cat "$out/$f.txt"; done
for f in register browse lookup; do echo "== aros $f"; cat "$out/aros/out/$f.log" 2>/dev/null; done
