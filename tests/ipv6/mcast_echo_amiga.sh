#!/bin/sh
# mcast_echo_amiga.sh OUT - B40: boot the m68k build (tools/amiga-run.sh), ping
# ff02::1 and AROS's link-local address from the host while capturing on aros0;
# prints how many replies came from AROS and the echo lines
set -u
o=$1; rm -rf "$o"; mkdir -p "$o"
cd ~/aros-matter
printf 'Delete >NIL: SYS:System/Network/AROSTCP/db/services.d/#? QUIET\nExecute SYS:System/Network/AROSTCP/S/startnet\nEcho >SYS:out/up u\nWait 60\n' > "$o/s.script"
AMIGA_TAP_IP=192.168.166.2 AMIGA_RUN_TIMEOUT=150 tools/amiga-run.sh "$o/run" "$o/s.script" >/dev/null 2>&1 &
t=0; while [ ! -f "$o/run/AROS/out/up" ] && [ $t -lt 240 ]; do sleep 1; t=$((t+1)); done
sleep 15
ping -c2 -w4 192.168.166.2 >/dev/null
mac=$(ip neigh show 192.168.166.2 dev aros0 | grep -o "lladdr [0-9a-f:]*" | cut -d' ' -f2)
ll=$(python3 -c "
import socket;b=bytes.fromhex('$mac'.replace(':',''));e=bytes([b[0]^2])+b[1:3]+b'\xff\xfe'+b[3:];print(socket.inet_ntop(socket.AF_INET6,bytes.fromhex('fe80000000000000')+e))")
sudo -n tcpdump -ni aros0 -U -w "$o/c.pcap" icmp6 >/dev/null 2>&1 &
sleep 1
echo "AROS $ll"
echo "multicast replies from AROS: $(ping -6 -w 4 "ff02::1%aros0" | grep -c "from $ll")"
echo "unicast replies: $(ping -6 -c 2 -w 4 "$ll%aros0" | grep -c "from $ll")"
sleep 1; sudo -n pkill -INT -f "tcpdump -ni aros0 -U -w $o/c.pcap"; sleep 1
sudo -n tcpdump -nn -r "$o/c.pcap" 2>/dev/null | awk '/echo/' | head -10
wait
