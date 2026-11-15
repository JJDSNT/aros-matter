#!/bin/bash
# samesegment.sh OUTDIR - B60: hosted AROS with two interfaces on ONE segment
# (taps aros0 and aros1 put in a Linux bridge, arosbr): each interface hears
# what the other sends. mdnsd must take its own announcements, heard by the
# other interface, as its own: the host keeps its name (no "arosbox-2"), and
# its own name resolves on AROS. mDNS on the bridge is captured; the names AROS
# announces are listed. The bridge is taken down at the end. Prints PASS/FAIL.
set -u
out=$1; mkdir -p "$out"
root=$(cd "$(dirname "$0")/../.." && pwd)
"$root/tools/tap-up.sh" 0 >/dev/null
"$root/tools/tap-up.sh" 1 >/dev/null
undo() {
  sudo -n ip link set aros0 nomaster 2>/dev/null
  sudo -n ip link set aros1 nomaster 2>/dev/null
  sudo -n ip link del arosbr 2>/dev/null
}
trap undo EXIT
undo
sudo -n ip link add arosbr type bridge && sudo -n ip link set arosbr up &&
  sudo -n ip link set aros0 master arosbr && sudo -n ip link set aros1 master arosbr ||
  { echo "FAIL bridge"; exit 1; }
cat > "$out/s.script" <<'EOS'
Execute SYS:System/Network/AROSTCP/S/startnet
Wait 20
Run >NIL: C:dnssd -R SegTest _segtest._tcp . 8080 -t 40 >SYS:out/register.log
Wait 20
C:dnssd -G v4 arosbox.local >SYS:out/self.log
Wait 15
EOS
sudo -n timeout 150 tcpdump -i arosbr -n -s0 -U -w "$out/br.pcap" udp port 5353 >/dev/null 2>&1 &
AROS_TAP_IP=192.168.166.2 AROS_TAP2_IP=192.168.167.2 AROS_RUN_TIMEOUT=120 \
  "$root/tools/hosted-run.sh" "$out/aros" "$out/s.script" > "$out/run.txt" 2>&1
sudo -n pkill -INT -f "tcpdump -i arosbr -n -s0 -U -w $out/br.pcap" 2>/dev/null
sleep 1
tcpdump -r "$out/br.pcap" -n -vv 2>/dev/null > "$out/br.txt"
# what AROS sent, by either family (the payload lines of tcpdump -vv; the
# host's Avahi never sends these): probes (a query for its name, with
# authority records), announcements (responses with its A records), and any
# other name it took
cp "$out/br.txt" "$out/payloads.txt"   # IPv6: the payload is on the header line; IPv4: on the next
probes=$(grep -c "ANY (Q[UM])? arosbox.local\." "$out/payloads.txt")
announced=$(grep "\*- \[0q\]" "$out/payloads.txt" | grep -c "arosbox.local. (Cache flush) A 192.168.16[67].2")
others=$(grep -o "arosbox[^ .]\+\.local" "$out/payloads.txt" | sort -u | tr '\n' ' ')
echo "== AROS sent: $probes probes, $announced announcements of arosbox.local; other names: ${others:-none}"
echo "== AROS: dnssd -G v4 arosbox.local"; cat "$out/aros/out/self.log" 2>/dev/null
fails=0
# three probes on each interface (RFC 6762 section 8.1), a round again if
# another host's probe came at once: a few, not one a second throughout
[ "$probes" -le 12 ] && pass=1 || pass=0
[ $pass = 1 ] && echo "PASS probing ended ($probes probes)" ||
  { echo "FAIL probing never ended: $probes probes"; fails=$((fails + 1)); }
[ "$announced" -gt 0 ] && echo "PASS arosbox.local announced ($announced)" ||
  { echo "FAIL arosbox.local never announced"; fails=$((fails + 1)); }
[ -z "$others" ] && echo "PASS no other name taken" ||
  { echo "FAIL the host took another name: $others"; fails=$((fails + 1)); }
# a service registered once IPv4 is up: probed by both families on both
# interfaces, each heard by the other - it must keep its name
svc=$(grep "\*- \[0q\]" "$out/payloads.txt" | grep -c "SegTest._segtest._tcp.local.")
svcren=$(grep -o "SegTest ([0-9]*)" "$out/payloads.txt" | sort -u | tr '\n' ' ')
[ "$svc" -gt 0 ] && [ -z "$svcren" ] && echo "PASS the service SegTest announced ($svc) under its name" ||
  { echo "FAIL the service: $svc announcements, renamed: ${svcren:-no}; register: $(cat "$out/aros/out/register.log" 2>/dev/null | head -2 | tr '\n' ' ')"; fails=$((fails + 1)); }
grep -q "^arosbox.local *192.168.16[67].2" "$out/aros/out/self.log" 2>/dev/null &&
  echo "PASS arosbox.local resolves on AROS" ||
  { echo "FAIL arosbox.local on AROS: $(cat "$out/aros/out/self.log" 2>/dev/null)"; fails=$((fails + 1)); }
echo "samesegment: $fails failed"
