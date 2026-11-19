#!/bin/sh
# addrreplace.sh OUTDIR - an IPv4 address of the host's that was announced
# and then goes (B62, point 2), hosted AROS on eth0, with a listener on IPv4
# alone (tests/mdns/ipv4_listen.py) and a capture; windows split by marks:
#   1. an alias, 192.168.166.79/32, added, kept 12 s (announced), deleted;
#   2. eth0's address replaced: 192.168.166.2 -> 192.168.166.3;
#   3. and back: 192.168.166.3 -> 192.168.166.2.
# Prints per window the host's A/AAAA records sent (address, TTL, count):
# an address that went should go from the others' caches - a goodbye, or
# the remaining set announced again with the cache-flush bit (RFC 6762
# 10.2) - and the IPv6 records stay as they were.
# RESOLVTEST, B67WAIT: the test binaries (built for the target).
set -u
out=$1; mkdir -p "$out"
root=$(cd "$(dirname "$0")/../.." && pwd)
"$root/tools/tap-up.sh" 0 >/dev/null
cat > "$out/s.script" <<EOS
Execute SYS:System/Network/AROSTCP/S/startnet
Wait 20
C:resolvtest -T 192.168.166.1 mark1.example >NIL:
C:b67wait addr eth0 192.168.166.79 12 >SYS:out/alias.txt
Wait 6
C:resolvtest -T 192.168.166.1 mark2.example >NIL:
C:ifconfig eth0 192.168.166.3 netmask 255.255.255.0
Wait 14
C:resolvtest -T 192.168.166.1 mark3.example >NIL:
C:ifconfig eth0 192.168.166.2 netmask 255.255.255.0
Wait 14
C:resolvtest -T 192.168.166.1 mark4.example >NIL:
Wait 1
EOS
sudo -n tcpdump -i aros0 -n -w "$out/aros0.pcap" 'udp port 5353 or arp or udp port 9' >/dev/null 2>&1 & cap0=$!
sudo -n tcpdump -i aros1 -n -w "$out/aros1.pcap" 'udp port 5353' >/dev/null 2>&1 & cap1=$!
sleep 1
AROS_TAP_IP=192.168.166.2 AROS_RUN_TIMEOUT=200 \
  "$root/tools/hosted-run.sh" "$out/aros" "$out/s.script" "$RESOLVTEST" "$B67WAIT" > "$out/run.txt" 2>&1
sleep 1
sudo -n kill $cap0 $cap1 2>/dev/null
sleep 1
for i in 0 1; do
  tcpdump -tt -n -r "$out/aros$i.pcap" 2>/dev/null > "$out/pcap$i.txt"
  python3 -I "$root/tests/mdns/mdns_pcap.py" "$out/aros$i.pcap" --name arosbox.local --rdata --time > "$out/rec$i.txt"
done
"$root/tests/mdns/pcap-clock.sh" "$out"/aros*.pcap || { echo "addrreplace: INVALID (the host's clock went back)"; exit 2; }
python3 -I "$root/tests/mdns/addrchange_report.py" "$out" | grep -v aros1 | \
  sed -e 's/^1 alias add\/delete  /1 alias 12 s, deleted/' -e 's/^2 same IPv4 again   /2 .2 replaced by .3/' \
      -e 's/^3 IPv4 on eth1      /3 .3 back to .2   /' -e '/^4 /d'
