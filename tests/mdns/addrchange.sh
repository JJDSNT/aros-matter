#!/bin/sh
# addrchange.sh OUTDIR - what mdnsd sends for the host's name when its
# addresses change (B62's questions), hosted AROS with eth0 (IPv4 and IPv6)
# and eth1 (IPv6 only at first: AROS_TAP2_IP=none). Each step starts with a
# datagram to the host's port 9 ("mark", resolvtest -T) so that the capture
# (mDNS, ARP and the marks, on aros0 and aros1) splits into windows:
#   1. an IPv4 alias (192.168.166.79/32) added to eth0, ready after its
#      conflict detection, then deleted (b67wait addr);
#   2. eth0's IPv4 address set again, the same (ifconfig);
#   3. an IPv4 address (192.168.167.2) given to eth1, which had none;
#   4. mdnsd stopped and started again, both families ready on both links.
# Prints, per window and link, the probes for the host's name and the host's
# A/AAAA records sent (address, TTL, how many times).
# RESOLVTEST, B67WAIT: the test binaries (built for the target).
set -u
out=$1; mkdir -p "$out"
root=$(cd "$(dirname "$0")/../.." && pwd)
"$root/tools/tap-up.sh" 0 >/dev/null; "$root/tools/tap-up.sh" 1 >/dev/null
cat > "$out/s.script" <<EOS
Execute SYS:System/Network/AROSTCP/S/startnet
Wait 20
C:resolvtest -T 192.168.166.1 mark1.example >NIL:
C:b67wait addr eth0 192.168.166.79 >SYS:out/alias.txt
Wait 6
C:resolvtest -T 192.168.166.1 mark2.example >NIL:
C:ifconfig eth0 192.168.166.2 netmask 255.255.255.0
Wait 10
C:resolvtest -T 192.168.166.1 mark3.example >NIL:
C:ifconfig eth1 192.168.167.2 netmask 255.255.255.0
Wait 14
C:resolvtest -T 192.168.166.1 mark4.example >NIL:
C:resolvtest -k mdns >SYS:out/kill.txt
Wait 3
Run >NIL: SYS:System/Network/Services/mdnsd
Wait 12
C:resolvtest -T 192.168.166.1 mark5.example >NIL:
Wait 1
EOS
sudo -n tcpdump -i aros0 -n -w "$out/aros0.pcap" 'udp port 5353 or arp or udp port 9' >/dev/null 2>&1 & cap0=$!
sudo -n tcpdump -i aros1 -n -w "$out/aros1.pcap" 'udp port 5353 or arp' >/dev/null 2>&1 & cap1=$!
sleep 1
AROS_TAP_IP=192.168.166.2 AROS_TAP2_IP=none AROS_RUN_TIMEOUT=200 \
  "$root/tools/hosted-run.sh" "$out/aros" "$out/s.script" "$RESOLVTEST" "$B67WAIT" > "$out/run.txt" 2>&1
sleep 1
sudo -n kill $cap0 $cap1 2>/dev/null
sleep 1
for i in 0 1; do
  tcpdump -tt -n -r "$out/aros$i.pcap" 2>/dev/null > "$out/pcap$i.txt"
  python3 -I "$root/tests/mdns/mdns_pcap.py" "$out/aros$i.pcap" --name arosbox.local --rdata --time > "$out/rec$i.txt"
done
python3 -I "$root/tests/mdns/addrchange_report.py" "$out"
