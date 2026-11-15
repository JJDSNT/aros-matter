#!/bin/bash
# foreignaddr.sh OUTDIR - B60's other side: hosted AROS with two interfaces
# on SEPARATE segments (eth0 on aros0, eth1 on aros1, 192.168.167.2), and on
# aros0 another host that has the very address of AROS's eth1, 192.168.167.2
# (a separate network may reuse it; here the Linux host, the address put on
# aros0 for the test). Its packets are not AROS's own:
#   1. it announces foreign.local: AROS hears it and resolves the name;
#   2. it announces arosbox.local, AROS's name, with its own address: a real
#      conflict on eth0's segment - AROS takes another name.
# mDNS on aros0 is captured. The address is taken off aros0 at the end.
# Prints PASS/FAIL.
set -u
out=$1; mkdir -p "$out"
root=$(cd "$(dirname "$0")/../.." && pwd)
"$root/tools/tap-up.sh" 0 >/dev/null
"$root/tools/tap-up.sh" 1 >/dev/null
undo() { sudo -n ip addr del 192.168.167.2/32 dev aros0 2>/dev/null; }
trap undo EXIT
cat > "$out/s.script" <<'EOS'
Execute SYS:System/Network/AROSTCP/S/startnet
Wait 35
C:dnssd -G v4 foreign.local >SYS:out/foreign.log
Wait 35
EOS
sudo -n timeout 150 tcpdump -i aros0 -n -s0 -U -w "$out/aros0.pcap" udp port 5353 >/dev/null 2>&1 &
AROS_TAP_IP=192.168.166.2 AROS_TAP2_IP=192.168.167.2 AROS_RUN_TIMEOUT=120 \
  "$root/tools/hosted-run.sh" "$out/aros" "$out/s.script" > "$out/run.txt" 2>&1 & run=$!
# the other host: from 20 s after the boot, foreign.local for 25 s; from 50 s,
# arosbox.local for 15 s - each a second, cache-flush, TTL 120
sleep 20
sudo -n ip addr add 192.168.167.2/32 dev aros0
python3 - <<'PY' > "$out/sender.txt" 2>&1
import socket, struct, time
def announce(name, ip):
    q = b"".join(bytes([len(l)]) + l.encode() for l in name.split(".")) + b"\0"
    rr = q + struct.pack("!HHIH", 1, 0x8001, 120, 4) + socket.inet_aton(ip)
    return struct.pack("!HHHHHH", 0, 0x8400, 0, 1, 0, 0) + rr
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.setsockopt(socket.SOL_SOCKET, 25, b"aros0\0")          # SO_BINDTODEVICE
s.bind(("192.168.167.2", 5353))
s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton("192.168.167.2"))
s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 255)
for i in range(25):
    s.sendto(announce("foreign.local", "192.168.167.2"), ("224.0.0.251", 5353)); time.sleep(1)
time.sleep(5)
for i in range(15):
    s.sendto(announce("arosbox.local", "192.168.167.2"), ("224.0.0.251", 5353)); time.sleep(1)
print("sent")
PY
wait $run
sudo -n pkill -INT -f "tcpdump -i aros0 -n -s0 -U -w $out/aros0.pcap" 2>/dev/null
sleep 1
tcpdump -r "$out/aros0.pcap" -n -vv 2>/dev/null > "$out/aros0.txt"
fails=0
echo "== sender: $(cat "$out/sender.txt")"
echo "== AROS: dnssd -G v4 foreign.local"; cat "$out/aros/out/foreign.log" 2>/dev/null
grep -q "^foreign.local *192.168.167.2" "$out/aros/out/foreign.log" 2>/dev/null &&
  echo "PASS foreign.local, announced from 192.168.167.2 (AROS's eth1 address) on eth0's segment, resolves" ||
  { echo "FAIL foreign.local not heard: $(cat "$out/aros/out/foreign.log" 2>/dev/null)"; fails=$((fails + 1)); }
# AROS's own names after the conflict: what it probes or announces besides
# arosbox.local, from its eth0 address (IPv4 or IPv6)
renamed=$(grep -o "arosbox[^ .]\+\.local\|arosbox (2)\.local\|arosbox-[0-9]*\.local" "$out/aros0.txt" | sort -u | tr '\n' ' ')
[ -n "$renamed" ] && echo "PASS the conflict on eth0's segment was seen: AROS took $renamed" ||
  { echo "FAIL AROS kept arosbox.local though another host on eth0's segment has it"; fails=$((fails + 1)); }
echo "foreignaddr: $fails failed"
