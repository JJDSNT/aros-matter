#!/bin/sh
# acd_linkup.sh OUTDIR - an address configured by hand through the link
# going and coming back (tap.device's link events, #2258):
#   - it stays (master ddc6446f76: IPv4 keeps the static configuration);
#   - it is probed again when the link is back (RFC 5227 section 2.1, as
#     NetBSD's in_if_link_up(): #2218's arp_dad_linkup()): ARP probes for
#     it - sender 0.0.0.0 - leave on the link after it comes back, and
#     ifconfig shows it tentative meanwhile, ready afterwards.
# CONFLICT=1: while the link is down the host takes the address on aros1,
# so it answers the probes when the link is back: the address must come
# out duplicated - not used - instead of ready (RFC 5227 section 2.1.1):
# tests/ipv4/srcprobe.c then cannot bind it, and a datagram AROS sends to
# the host (192.168.167.1:9, captured on aros1) does not leave from it.
# Hosted AROS with eth0 and eth1 (taps aros0, aros1); eth1 (192.168.167.2,
# static) is the one tested. Needs sudo -n (ip link, tcpdump).
# AROS_HOSTED_IMAGE as for tools/hosted-run.sh.
set -u
out=$1; mkdir -p "$out"
root=$(cd "$(dirname "$0")/../.." && pwd)
"$root/tools/tap-up.sh" 0 >/dev/null && "$root/tools/tap-up.sh" 1 >/dev/null || exit 1
addr=192.168.167.2
cc=$(python3 -c "import sys;sys.path.insert(0,'$root/tests/tcp');import run_tcp;print(run_tcp.CROSS)")
"$cc" --sysroot "${AROS_HOSTED_IMAGE:?}/Developer" -O2 -o "$out/srcprobe" "$root/tests/ipv4/srcprobe.c" || exit 1
wait_go='Lab w%s\nIf NOT EXISTS SYS:out/go%s\n Wait 1\n Skip w%s BACK\nEndIf\n'
{ echo "Execute SYS:System/Network/AROSTCP/S/startnet"; echo "Wait 10"
  echo "C:ifconfig eth1 >SYS:out/before.log"; echo "Echo >SYS:out/ready1 r"
  printf "$wait_go" 1 1 1
  echo "C:ifconfig eth1 >SYS:out/up0.log"
  echo "Wait 8"
  echo "C:ifconfig eth1 >SYS:out/up8.log"
  echo "C:srcprobe $addr 192.168.167.1 >SYS:out/srcprobe.log"; } > "$out/s.script"
AROS_TAP_IP=192.168.166.2 AROS_TAP2_IP=$addr AROS_RUN_TIMEOUT=120 \
  "$root/tools/hosted-run.sh" "$out/run" "$out/s.script" "$out/srcprobe" > "$out/run.txt" 2>&1 &
run=$!
d="$out/run/AROS/out"
wait_for() { t=0; while [ ! -f "$d/$1" ] && [ $t -lt 120 ]; do sleep 0.5; t=$((t+1)); done; [ -f "$d/$1" ]; }
wait_for ready1 || { echo "FAIL AROS did not start"; wait $run; exit 1; }
sudo -n ip link set aros1 down; sleep 2
[ "${CONFLICT:-0}" = 1 ] && sudo -n ip addr add $addr/24 dev aros1
sudo -n timeout 15 tcpdump -i aros1 -n -l arp > "$out/arp.txt" 2>/dev/null & cap=$!
sudo -n timeout 40 tcpdump -i aros1 -n -l "udp dst port 9" > "$out/udp9.txt" 2>/dev/null & cap9=$!
sudo -n ip link set aros1 up; sleep 1
touch "$d/go1"
wait $run
sudo -n pkill -INT -f "tcpdump -i aros1 -n -l arp" 2>/dev/null; wait $cap 2>/dev/null
sudo -n pkill -INT -f "tcpdump -i aros1 -n -l udp dst port 9" 2>/dev/null; wait $cap9 2>/dev/null
cat "$out/run/out/srcprobe.log" 2>/dev/null; cat "$out/udp9.txt"
[ "${CONFLICT:-0}" = 1 ] && sudo -n ip addr del $addr/24 dev aros1
grep -a -i "link lost\|probing\|probed" "$out/run/serial.log" | head -6
probes=$(grep -c "Request who-has $addr tell 0.0.0.0" "$out/arp.txt")
echo "after the link came back: $probes ARP probes for $addr"
f=$out/run/out
ok=1
grep -q "inet $addr" "$f/before.log" && grep -q "inet $addr" "$f/up8.log" ||
  { echo "FAIL the address did not stay"; ok=0; }
[ "$probes" -ge 1 ] || { echo "FAIL not probed again"; ok=0; }
if [ "${CONFLICT:-0}" = 1 ]; then
  grep -q "duplicated" "$f/up8.log" || { echo "FAIL not duplicated though the host has it"; ok=0; }
  grep -q "bind $addr: refused" "$f/srcprobe.log" || { echo "FAIL a socket could still bind it"; ok=0; }
  grep -q "IP $addr\." "$out/udp9.txt" && { echo "FAIL a datagram still left from it"; ok=0; }
  [ $ok = 1 ] && echo "PASS the address stayed, was probed again, and is duplicated (the host has it)"
else
  grep -q "tentative" "$f/up0.log" || { echo "FAIL not tentative right after the link came back"; ok=0; }
  grep -q "tentative\|duplicated" "$f/up8.log" && { echo "FAIL not ready 8 s later"; ok=0; }
  [ $ok = 1 ] && echo "PASS the address stayed, was probed again, and is ready"
fi
