#!/bin/sh
# netmidid.sh OUTDIR - netmidid's discovery on dnssd.library, on hosted AROS
# (tap aros0) against the host's Avahi.
#
# netmidid advertises "AROS MIDI" (AppleMIDI, _apple-midi._udp; Network MIDI
# 2.0, _midi2._udp with a time to live of 60 s) and browses _midi2._udp for
# the host its configuration names. The host:
#   - already has "AROS MIDI" on both types: netmidid is renamed "AROS MIDI
#     (2)" (RFC 6762 section 9), must say so, must see the host's "AROS MIDI"
#     as a peer and not report its own instance;
#   - publishes HostMIDI2 (endpoint HostEP) on port 5674, withdraws it (its
#     goodbye: "is gone") and publishes it again on 5675: found again, with
#     the new port (the resolve follows it);
#   - browses AROS's AppleMIDI session; a capture gives its records' TTL.
# Prints PASS/FAIL per check. AROS_HOSTED_IMAGE as for tools/hosted-run.sh.
set -u
out=$1; mkdir -p "$out"
root=$(cd "$(dirname "$0")/../.." && pwd)
"$root/tools/tap-up.sh" >/dev/null
cat > "$out/NetMIDI" <<EOC
session_name=AROS MIDI
local_port=5004
midi2_port=5673
midi2_peer_name=HostEP
EOC
cat > "$out/s.script" <<EOS
Copy SYS:C/NetMIDI ENV:NetMIDI
Echo >ENV:netmidid.log "SYS:out/netmidid.log" NOLINE
Execute SYS:System/Network/AROSTCP/S/startnet
Wait 10
Run >NIL: SYS:System/Network/Services/netmidid
Wait 75
EOS
avahi-publish-service "AROS MIDI" _apple-midi._udp 5004 >/dev/null 2>&1 & twin1=$!
avahi-publish-service "AROS MIDI" _midi2._udp 5676 UMPEndpointName=HostTwin ProductInstanceId=t1 >/dev/null 2>&1 & twin2=$!
avahi-publish-service HostMIDI2 _midi2._udp 5674 UMPEndpointName=HostEP ProductInstanceId=h1 >/dev/null 2>&1 & peer=$!
sudo -n timeout 130 tcpdump -i aros0 -n -s0 -U -w "$out/aros0.pcap" udp port 5353 >/dev/null 2>&1 &
AROS_TAP_IP=192.168.166.2 AROS_RUN_TIMEOUT=120 \
  "$root/tools/hosted-run.sh" "$out/aros" "$out/s.script" "$out/NetMIDI" > "$out/run.txt" 2>&1 & run=$!
sleep 45
kill $peer 2>/dev/null                  # its goodbye
sleep 8
avahi-publish-service HostMIDI2 _midi2._udp 5675 UMPEndpointName=HostEP ProductInstanceId=h1 >/dev/null 2>&1 & peer=$!
sleep 10
timeout 10 avahi-browse -rptk _apple-midi._udp > "$out/host-applemidi.txt" 2>&1
timeout 10 avahi-browse -rptk _midi2._udp > "$out/host-midi2.txt" 2>&1
wait $run
kill $peer $twin1 $twin2 2>/dev/null
sudo -n pkill -INT -f "tcpdump -i aros0 -n -s0 -U -w $out/aros0.pcap" 2>/dev/null
sleep 1
python3 "$root/tests/mdns/mdns_pcap.py" "$out/aros0.pcap" --from 192.168.166.2 \
  --name "._midi2._udp.local" > "$out/ttl.txt" 2>&1

log=$out/aros/out/netmidid.log
fails=0
check() {   # check NAME FILE PATTERN
  if grep -q -- "$3" "$2" 2>/dev/null; then echo "PASS $1"; else echo "FAIL $1"; fails=$((fails + 1)); fi
}
absent() {  # absent NAME FILE PATTERN
  if grep -q -- "$3" "$2" 2>/dev/null; then echo "FAIL $1"; fails=$((fails + 1)); else echo "PASS $1"; fi
}
check "advertised" "$log" 'advertised by the system mDNS service'
check "renamed after the conflict" "$log" '"AROS MIDI" (_midi2._udp) is advertised as "AROS MIDI (2)"'
check "host sees AROS MIDI (2), AppleMIDI" "$out/host-applemidi.txt" ';AROS\\032MIDI\\032\\0402\\041;_apple-midi._udp;local;arosbox.local;192.168.166.2;5004;'
check "host sees AROS MIDI (2), MIDI 2.0" "$out/host-midi2.txt" ';AROS\\032MIDI\\032\\0402\\041;_midi2._udp;local;arosbox.local;192.168.166.2;5673;'
check "the host's twin is a peer" "$log" 'MIDI 2.0 host "HostTwin" ("AROS MIDI") found at 192.168.166.1'
absent "its own instance is not a peer" "$log" '("AROS MIDI (2)") found'
check "peer found" "$log" 'MIDI 2.0 host "HostEP" ("HostMIDI2") found at 192.168.166.1'
check "peer's IPv6 address too" "$log" 'MIDI 2.0 host "HostEP" ("HostMIDI2") found at 192.168.166.1, fe80::'
check "peer on 5674" "$log" '("HostMIDI2") found at .* port 5674'
check "peer gone (goodbye)" "$log" 'MIDI 2.0 host "HostMIDI2" is gone'
check "peer again on 5675" "$log" '("HostMIDI2") found at .* port 5675'
check "MIDI 2.0 records: SRV TTL 60" "$out/ttl.txt" 'SRV IN-flush 60$'
check "MIDI 2.0 records: TXT TTL 60" "$out/ttl.txt" 'TXT IN-flush 60$'
echo "netmidid: $fails failed"
