#!/bin/sh
# memory.sh OUTDIR MDNSD - what registered services cost (B60-B76 work,
# architecture B): AROS boots with MDNSD as its mdnsd, and tests/mdns/memsvc
# registers 0, 1, 10 and 50 services in turn, each time printing the free
# memory before, with them registered, held 5 s, and after their cancel.
# MODE=amiga for AROS m68k (one link); hosted: one link (eth0), or two with
# LINKS=2 (eth1 too). MEMSVC: the memsvc binary for the target.
# Prints per count: cost (before - held) and what was not given back
# (before - after), in bytes.
set -u
out=$1; mdnsd=$2; mkdir -p "$out"
root=$(cd "$(dirname "$0")/../.." && pwd)
mode=${MODE:-hosted}; links=${LINKS:-1}
"$root/tools/tap-up.sh" 0 >/dev/null; "$root/tools/tap-up.sh" 1 >/dev/null
cp "$mdnsd" "$out/mdnsd.new"
{
  echo "Copy C:mdnsd.new SYS:System/Network/Services/mdnsd QUIET"
  [ "$mode" = amiga ] && echo "Delete >NIL: SYS:System/Network/AROSTCP/db/services.d/timesync QUIET"
  echo "Execute SYS:System/Network/AROSTCP/S/startnet"
  [ "$mode" = amiga ] && echo "Wait 60" || echo "Wait 20"
  for n in 0 1 10 50; do echo "C:memsvc $n 5 >SYS:out/m$n.txt"; done
} > "$out/s.script"
if [ "$mode" = amiga ]; then
  AMIGA_TAP_IP=192.168.166.2 AMIGA_RUN_TIMEOUT=900 \
    "$root/tools/amiga-run.sh" "$out/aros" "$out/s.script" "$MEMSVC" "$out/mdnsd.new" > "$out/run.txt" 2>&1
else
  # one link: no eth1 at all (AROS_TAP2_IP=none would still bring it up,
  # with IPv6 alone)
  [ "$links" = 2 ] && export AROS_TAP2_IP=192.168.167.2 || unset AROS_TAP2_IP
  AROS_TAP_IP=192.168.166.2 AROS_RUN_TIMEOUT=300 \
    "$root/tools/hosted-run.sh" "$out/aros" "$out/s.script" "$MEMSVC" "$out/mdnsd.new" > "$out/run.txt" 2>&1
fi
for n in 0 1 10 50; do
  f=$out/aros/out/m$n.txt
  [ -f "$f" ] || { echo "$n services: no output"; continue; }
  awk -v n=$n '
    $2 == "before" { b = $3 }
    $2 == "registered" { r = $3 " of " $5 " in " $8 " s" }
    $2 == "held" { h = $3; hl = $4 }
    $2 == "after" { a = $3 }
    END { printf "%2d services: registered %s; cost %d B; not given back %d B; largest block %d\n", n, r, b - h, b - a, hl }' "$f"
done
