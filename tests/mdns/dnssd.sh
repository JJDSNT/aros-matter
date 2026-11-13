#!/bin/sh
# dnssd.sh OUTDIR - dnssd.library against mdnsd on hosted AROS (tap aros0):
# tests/mdns/dnssdtest looks the host's name up (Avahi answers it), and a
# name nobody has, and browses/resolves services the host publishes (Avahi). AROS_HOSTED_IMAGE as for tools/hosted-run.sh; MODE=amiga
# runs AROS m68k on the emulated Amiga (tools/amiga-run.sh), without
# timesyncd there (B35). DNSSDTEST: the test binary (built for the target).
set -u
out=$1; mkdir -p "$out"
root=$(cd "$(dirname "$0")/../.." && pwd)
"$root/tools/tap-up.sh" >/dev/null
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
C:dnssdtest $host.local nobody-here.local _hosttest._tcp >SYS:out/dnssdtest.log
EOS
# what the host offers: Browse/Resolve find it; an instance with a dot in it
avahi-publish-service HostTest _hosttest._tcp 9999 vers=1 >/dev/null 2>&1 & pub1=$!
avahi-publish-service Dot.Test _hosttest._tcp 9998 "path=/a b" >/dev/null 2>&1 & pub2=$!
# while AROS holds its registration (SYS:out/registered): the host looks
( for i in $(seq 1 600); do [ -e "$out/aros/AROS/out/registered" ] && break; sleep 0.5; done
  sleep 2; timeout 10 avahi-browse -rpt _arostest._tcp > "$out/host-browse.txt" 2>&1
  avahi-resolve -4 -n proxyhost.local > "$out/host-proxy4.txt" 2>&1
  avahi-resolve -6 -n proxyhost.local > "$out/host-proxy6.txt" 2>&1 ) & look=$!
if [ "$mode" = amiga ]; then
  AMIGA_TAP_IP=192.168.166.2 AMIGA_RUN_TIMEOUT=240 \
    "$root/tools/amiga-run.sh" "$out/aros" "$out/s.script" "$DNSSDTEST" > "$out/run.txt" 2>&1
else
  AROS_TAP_IP=192.168.166.2 AROS_RUN_TIMEOUT=90 \
    "$root/tools/hosted-run.sh" "$out/aros" "$out/s.script" "$DNSSDTEST" > "$out/run.txt" 2>&1
fi
kill $pub1 $pub2 2>/dev/null
echo "== host browse of AROS's registration"; cat "$out/host-browse.txt" 2>/dev/null
echo "== host resolves the proxied host"; cat "$out/host-proxy4.txt" "$out/host-proxy6.txt" 2>/dev/null
cat "$out/aros/out/dnssdtest.log" 2>/dev/null || { echo "no log"; tail -20 "$out/run.txt"; exit 1; }
wait $look 2>/dev/null
grep -q ", 0 failed" "$out/aros/out/dnssdtest.log" &&
  grep -q ';7777;' "$out/host-browse.txt" &&
  grep -q '192.168.166.78' "$out/host-proxy4.txt" &&
  grep -qE '2001:db8::77|fe80::77' "$out/host-proxy6.txt" &&
  grep -q 'Big\\.Txt;_arostest._tcp;local;arosbox.local;.*;7783;"k=' "$out/host-browse.txt"
