#!/bin/sh
# nd6_link.sh OUTDIR - the IPv6 neighbour cache through an interface's life,
# along the stack's own event path: tap.device reports the host's side of
# the tap going down and up (S2EVENT_DISCONNECT/CONNECT), sana_connect()
# makes them NFE_LINKDOWN/NFE_LINKUP, and IPv6 purges what was learned.
#
# Hosted AROS with eth0 and eth1 (taps aros0, aros1); eth1 is the one tested:
#   AROS adds a static entry on eth1 (nd6link add); the host pings AROS's
#   link-local address on eth1, which makes a learned entry (the host's);
#   before: static 1, dynamic >= 1
#   the host takes aros1 down (ip link set aros1 down): the link is lost
#   down:   static 1, dynamic 0    (the static one stays, the learned go)
#   the host brings it back up
#   up:     static 1, dynamic 0
#   eth1 leaves the configuration (reloaded in place, tests/stack/ifreload)
#   removed: static 0, dynamic 0   (all of a removed interface's go)
# Needs sudo -n (ip link). AROS_HOSTED_IMAGE as for tools/hosted-run.sh.
set -u
out=$1; mkdir -p "$out"
root=$(cd "$(dirname "$0")/../.." && pwd)
"$root/tools/tap-up.sh" 0 >/dev/null && "$root/tools/tap-up.sh" 1 >/dev/null || exit 1
cc=$(python3 -c "import sys;sys.path.insert(0,'$root/tests/tcp');import run_tcp;print(run_tcp.CROSS)")
for p in "tests/ipv6/nd6link" "tests/stack/ifreload"; do
    "$cc" --sysroot "${AROS_HOSTED_IMAGE:?}/Developer" -O2 -o "$out/$(basename $p)" "$root/$p.c" || exit 1
done
wait_go='Lab w%s\nIf NOT EXISTS SYS:out/go%s\n Wait 1\n Skip w%s BACK\nEndIf\n'
{ echo "Execute SYS:System/Network/AROSTCP/S/startnet"; echo "Wait 8"
  echo "C:nd6link add eth1 >SYS:out/add.log"; echo "Echo >SYS:out/ready1 r"
  printf "$wait_go" 1 1 1; echo "C:nd6link list eth1 before >>SYS:out/list.log"; echo "Echo >SYS:out/ready2 r"
  printf "$wait_go" 2 2 2; echo "C:nd6link list eth1 down >>SYS:out/list.log"; echo "Echo >SYS:out/ready3 r"
  printf "$wait_go" 3 3 3; echo "C:nd6link list eth1 up >>SYS:out/list.log"
  echo "C:ifreload drop eth1"; echo "Wait 2"
  echo "C:nd6link list eth1 removed >>SYS:out/list.log"; } > "$out/s.script"
AROS_TAP_IP=192.168.166.2 AROS_TAP2_IP=192.168.167.2 AROS_RUN_TIMEOUT=150 \
  "$root/tools/hosted-run.sh" "$out/run" "$out/s.script" "$out/nd6link" "$out/ifreload" \
  > "$out/run.txt" 2>&1 &
run=$!
d="$out/run/AROS/out"
wait_for() { t=0; while [ ! -f "$d/$1" ] && [ $t -lt 120 ]; do sleep 0.5; t=$((t+1)); done; [ -f "$d/$1" ]; }
wait_for ready1 || { echo "FAIL AROS did not start"; wait $run; exit 1; }
# AROS's eth1 link-local address, from its MAC (EUI-64, as in6.c makes it)
ping -c 2 -w 4 192.168.167.2 >/dev/null
mac=$(ip neigh show 192.168.167.2 dev aros1 | sed -n 's/.*lladdr \([0-9a-f:]*\).*/\1/p')
ll=$(python3 -c "
import socket;b=bytes.fromhex('$mac'.replace(':',''));e=bytes([b[0]^2])+b[1:3]+b'\xff\xfe'+b[3:]
print(socket.inet_ntop(socket.AF_INET6,bytes.fromhex('fe80000000000000')+e))")
ping -6 -c 2 -w 4 "$ll%aros1" > "$out/ping6.txt" 2>&1
touch "$d/go1"
wait_for ready2 || { echo "FAIL no ready2"; wait $run; exit 1; }
sudo -n ip link set aros1 down; sleep 2; touch "$d/go2"
wait_for ready3 || { echo "FAIL no ready3"; sudo -n ip link set aros1 up; wait $run; exit 1; }
sudo -n ip link set aros1 up; sleep 2; touch "$d/go3"
wait $run
cat "$out/run/out/add.log" "$out/run/out/list.log"
grep -a -E "link lost|eth1" "$out/run/serial.log" | grep -a -i "link" | head -4
l() { sed -n "s/^$1 static \([0-9]*\) dynamic \([0-9]*\).*/\1 \2/p" "$out/run/out/list.log"; }
set -- $(l before) $(l down) $(l up) $(l removed)
[ $# -eq 8 ] || { echo "FAIL missing steps"; exit 1; }
ok=1
[ "$1" = 1 ] && [ "$2" -ge 1 ] || { echo "FAIL before: static $1 dynamic $2"; ok=0; }
[ "$3" = 1 ] && [ "$4" = 0 ] || { echo "FAIL down: static $3 dynamic $4"; ok=0; }
[ "$5" = 1 ] && [ "$6" = 0 ] || { echo "FAIL up: static $5 dynamic $6"; ok=0; }
[ "$7" = 0 ] && [ "$8" = 0 ] || { echo "FAIL removed: static $7 dynamic $8"; ok=0; }
[ $ok = 1 ] && echo "PASS static kept through the link going, learned ones gone, all gone with the interface"
