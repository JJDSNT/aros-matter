#!/bin/sh
# dnssd.sh OUTDIR - dnssd.library against mdnsd on hosted AROS (tap aros0):
# tests/mdns/dnssdtest looks the host's name up (Avahi answers it), and a
# name nobody has. AROS_HOSTED_IMAGE as for tools/hosted-run.sh; MODE=amiga
# runs AROS m68k on the emulated Amiga (tools/amiga-run.sh), without
# timesyncd there (B35). DNSSDTEST: the test binary (built for the target).
set -u
out=$1; mkdir -p "$out"
root=$(cd "$(dirname "$0")/../.." && pwd)
"$root/tools/tap-up.sh" >/dev/null
host=$(hostname)
mode=${MODE:-hosted}
pre=""
[ "$mode" = amiga ] && pre="Delete >NIL: SYS:System/Network/AROSTCP/db/services.d/timesync QUIET"
cat > "$out/s.script" <<EOS
$pre
Execute SYS:System/Network/AROSTCP/S/startnet
Wait 12
C:dnssdtest $host.local nobody-here.local >SYS:out/dnssdtest.log
EOS
if [ "$mode" = amiga ]; then
  AMIGA_TAP_IP=192.168.166.2 AMIGA_RUN_TIMEOUT=240 \
    "$root/tools/amiga-run.sh" "$out/aros" "$out/s.script" "$DNSSDTEST" > "$out/run.txt" 2>&1
else
  AROS_TAP_IP=192.168.166.2 AROS_RUN_TIMEOUT=90 \
    "$root/tools/hosted-run.sh" "$out/aros" "$out/s.script" "$DNSSDTEST" > "$out/run.txt" 2>&1
fi
cat "$out/aros/out/dnssdtest.log" 2>/dev/null || { echo "no log"; tail -20 "$out/run.txt"; exit 1; }
grep -q ", 0 failed" "$out/aros/out/dnssdtest.log"
