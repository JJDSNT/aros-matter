#!/bin/bash
# resolver-stack.sh OUTDIR - how much of a 4 KB stack (a Shell command's on
# an Amiga) the resolver's look-ups take, the whole chain - bsdsocket.library,
# the resolver module, dnssd.library - measured by tests/mdns/resolvtest -s
# (the free stack painted before, read after). One boot, mdnsd running:
#   palerma.local     a .local name a host answers (mDNS)
#   nobody-here.local a .local name nobody has (mDNS, the whole 3 s)
#   hostsonly.local   a .local name in the host table (IPv4 only: its
#                     IPv6 look-up goes on to mDNS)
#   onlyhosts         a name in the host table only (no mDNS, no DNS)
#   control.example   another name: the DNS (a NAMESERVER that does not answer)
# MODE=amiga (default here) or hosted. RESOLVTEST: the binary for the target.
set -u
out=$1; mkdir -p "$out"
root=$(cd "$(dirname "$0")/../.." && pwd)
mode=${MODE:-amiga}
"$root/tools/tap-up.sh" 0 >/dev/null
host=$(avahi-resolve -4 -a 192.168.166.1 2>/dev/null | awk '{print $2}')
host=${host%.local}
[ -n "$host" ] || host=$(hostname)
pre=""
[ "$mode" = amiga ] && pre="Delete >NIL: SYS:System/Network/AROSTCP/db/services.d/timesync QUIET"
cat > "$out/s.script" <<EOS
Echo "NAMESERVER 192.168.166.1" >>SYS:System/Network/AROSTCP/db/netdb-myhost
Echo "HOST 192.168.166.77 hostsonly.local" >>SYS:System/Network/AROSTCP/db/netdb-myhost
Echo "HOST 192.168.166.78 onlyhosts" >>SYS:System/Network/AROSTCP/db/netdb-myhost
$pre
Execute SYS:System/Network/AROSTCP/S/startnet
Wait 15
C:resolvtest -S 4096 $host.local nobody-here.local hostsonly.local onlyhosts control.example >SYS:out/stack.log
C:resolvtest -S 16384 $host.local nobody-here.local hostsonly.local onlyhosts control.example >SYS:out/stack16.log
EOS
if [ "$mode" = amiga ]; then
  AMIGA_TAP_IP=192.168.166.2 AMIGA_RUN_TIMEOUT=300 \
    "$root/tools/amiga-run.sh" "$out/aros" "$out/s.script" "$RESOLVTEST" > "$out/run.txt" 2>&1
else
  AROS_TAP_IP=192.168.166.2 AROS_RUN_TIMEOUT=150 \
    "$root/tools/hosted-run.sh" "$out/aros" "$out/s.script" "$RESOLVTEST" > "$out/run.txt" 2>&1
fi
echo "== a process with 4096 bytes of stack: name size at-entry most left"; cat "$out/aros/out/stack.log" 2>/dev/null
echo "== the same with 16384"; cat "$out/aros/out/stack16.log" 2>/dev/null
grep -h "TLSF\|UserAlert\|Program failed" "$out/aros/serial.log" 2>/dev/null | head -3
