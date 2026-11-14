#!/bin/sh
# tools.sh OUTDIR - the mDNS tools on dnssd.library (dnssd, Nearby, Share,
# Handshake), on hosted AROS (tap aros0) against the host's Avahi.
#
# AROS: dnssd -R with -t 45 (the records' time to live) and a binary TXT
# value, -P for another host (IPv4, and IPv6), Share; dnssd -L (of the
# host's service, and of its own binary TXT), -G v4v6, -q, -Z (A and AAAA)
# and -B of the types; Nearby (kinds, and web with PORTS: every address);
# Handshake of a service there is and of one there is not; dnssd -B of a
# service whose TXT the host changes in place (avahi_update.py): ADD, then
# UPDATE with what it says now, then REMOVE (followed, as BonAmi's browse did).
# The host publishes HostTest (_hosttest._tcp) and HostWeb (_http._tcp),
# browses what AROS registered, resolves the other host's name, and a capture
# on aros0 gives the TTL of AROS's records. Prints PASS/FAIL per check.
# AROS_HOSTED_IMAGE as for tools/hosted-run.sh; MODE=amiga runs AROS m68k on
# the emulated Amiga (tools/amiga-run.sh, without timesyncd there: B35), the
# host's side later by what the slower boot takes.
set -u
out=$1; mkdir -p "$out"
root=$(cd "$(dirname "$0")/../.." && pwd)
"$root/tools/tap-up.sh" >/dev/null
host=$(avahi-resolve -4 -a 192.168.166.1 2>/dev/null | awk '{print $2}')
host=${host%.local}
[ -n "$host" ] || host=$(hostname)
mode=${MODE:-hosted}
pre=""
off=0
[ "$mode" = amiga ] && { pre="Delete >NIL: SYS:System/Network/AROSTCP/db/services.d/timesync QUIET"; off=45; }
cat > "$out/s.script" <<EOS
$pre
Execute SYS:System/Network/AROSTCP/S/startnet
Wait 12
Run >NIL: C:dnssd -R ToolReg _arostest._tcp . 8080 -t 45 path=/ >SYS:out/register.log
Run >NIL: C:dnssd -R BinReg _arostest._tcp . 8083 bin=\\x00\\xffz >SYS:out/binary.log
Run >NIL: C:dnssd -P ProxyReg _arostest._tcp . 8081 proxyhost 192.168.166.77 >SYS:out/proxy.log
Run >NIL: C:dnssd -P Proxy6 _arostest._tcp . 8084 proxysix 2001:db8::77 >SYS:out/proxy6.log
Run >NIL: C:Share "AROS Share" web 8082 TEXT "path=/share" >SYS:out/share.log
Run >NIL: C:dnssd -B _services._dns-sd._udp >SYS:out/types.log
Run >NIL: C:dnssd -Z _hosttest._tcp >SYS:out/zone.log
Run >NIL: C:dnssd -q $host.local A >SYS:out/query.log
Run >NIL: C:dnssd -B _changetest._tcp >SYS:out/change.log
Wait 6
C:dnssd -L HostTest _hosttest._tcp >SYS:out/resolve.log
C:dnssd -L BinReg _arostest._tcp >SYS:out/resolve-binary.log
C:dnssd -G v4v6 $host.local >SYS:out/lookup.log
C:dnssd -G v4 arosbox.local >SYS:out/lookup-self.log
C:Nearby TIME 6 >SYS:out/nearby-kinds.log
C:Nearby web PORTS RAW TIME 6 >SYS:out/nearby-web.log
C:Handshake HostTest _hosttest._tcp TIME 8 >SYS:out/handshake.log
C:Handshake Nobody web TIME 3 >SYS:out/handshake-none.log
Wait 15
EOS
avahi-publish-service HostTest _hosttest._tcp 9999 vers=1 >/dev/null 2>&1 & pub1=$!
avahi-publish-service HostWeb _http._tcp 8000 path=/w >/dev/null 2>&1 & pub2=$!
# ChangeTest: v=1 from 20 s after the boot, v=2 at 35 s, withdrawn at 50 s
( sleep $((20 + off)); python3 "$root/tests/mdns/avahi_update.py" ChangeTest _changetest._tcp 7001 v=1 v=2 15 15 ) & upd=$!
sudo -n timeout $((140 + 2 * off)) tcpdump -i aros0 -n -s0 -U -w "$out/aros0.pcap" udp port 5353 >/dev/null 2>&1 & cap=$!
if [ "$mode" = amiga ]; then
  AMIGA_TAP_IP=192.168.166.2 AMIGA_RUN_TIMEOUT=260 \
    "$root/tools/amiga-run.sh" "$out/aros" "$out/s.script" > "$out/run.txt" 2>&1 & run=$!
else
  AROS_TAP_IP=192.168.166.2 AROS_RUN_TIMEOUT=130 \
    "$root/tools/hosted-run.sh" "$out/aros" "$out/s.script" > "$out/run.txt" 2>&1 & run=$!
fi
sleep $((45 + off))
timeout 10 avahi-browse -rptk _arostest._tcp > "$out/host-arostest.txt" 2>&1
timeout 10 avahi-browse -rptk _http._tcp > "$out/host-http.txt" 2>&1
avahi-resolve -4 -n proxyhost.local > "$out/host-proxy.txt" 2>&1
avahi-resolve -6 -n proxysix.local > "$out/host-proxy6.txt" 2>&1
wait $run
wait $upd 2>/dev/null
kill $pub1 $pub2 2>/dev/null
sudo -n pkill -INT -f "tcpdump -i aros0 -n -s0 -U -w $out/aros0.pcap" 2>/dev/null
sleep 1
python3 "$root/tests/mdns/mdns_pcap.py" "$out/aros0.pcap" --from 192.168.166.2 \
  --name ToolReg._arostest._tcp.local > "$out/ttl.txt" 2>&1

a=$out/aros/out
fails=0
check() {   # check NAME FILE PATTERN
  if grep -q -- "$3" "$2" 2>/dev/null; then echo "PASS $1"; else echo "FAIL $1"; fails=$((fails + 1)); fi
}
check "dnssd -R registered" "$a/register.log" 'Registered "ToolReg" _arostest._tcp port 8080 txt="path=/"'
check "host sees ToolReg" "$out/host-arostest.txt" '^=;aros0;IPv4;ToolReg;_arostest._tcp;local;arosbox.local;192.168.166.2;8080;"path=/"'
check "dnssd -t 45: SRV TTL 45" "$out/ttl.txt" 'SRV IN-flush 45$'
check "dnssd -t 45: TXT TTL 45" "$out/ttl.txt" 'TXT IN-flush 45$'
check "dnssd -P registered" "$a/proxy.log" 'Registered "ProxyReg"'
check "host sees ProxyReg on proxyhost" "$out/host-arostest.txt" ';ProxyReg;_arostest._tcp;local;proxyhost.local;192.168.166.77;8081;'
check "host resolves proxyhost" "$out/host-proxy.txt" '192.168.166.77'
check "dnssd -P IPv6 registered" "$a/proxy6.log" 'Registered "Proxy6"'
check "host resolves proxysix (AAAA)" "$out/host-proxy6.txt" '2001:db8::77'
check "binary TXT registered" "$a/binary.log" 'Registered "BinReg"'
check "binary TXT read back" "$a/resolve-binary.log" 'TXT     bin=\\x00\\xffz'
check "Share advertised" "$a/share.log" 'Now sharing "AROS Share"'
check "host sees AROS Share" "$out/host-http.txt" ';AROS\\032Share;_http._tcp;local;arosbox.local;192.168.166.2;8082;"path=/share"'
check "dnssd -L resolved" "$a/resolve.log" 'RESOLVED'
check "dnssd -L address" "$a/resolve.log" 'address 192.168.166.1'
check "dnssd -L TXT" "$a/resolve.log" 'TXT     vers=1'
check "dnssd -G v4" "$a/lookup.log" "$host.local  192.168.166.1"
check "dnssd -G v6" "$a/lookup.log" "$host.local  fe80:"
check "dnssd -G of this host's own name" "$a/lookup-self.log" "arosbox.local  192.168.166.2"
check "dnssd -q A" "$a/query.log" "$host.local.  type 1 .* 192.168.166.1"
check "dnssd -Z PTR" "$a/zone.log" '_hosttest._tcp.local.	PTR	HostTest._hosttest._tcp.local.'
check "dnssd -Z SRV" "$a/zone.log" "HostTest._hosttest._tcp.local.	SRV	0 0 9999 $host.local."
check "dnssd -Z A" "$a/zone.log" "$host.local.	A	192.168.166.1"
check "dnssd -Z AAAA" "$a/zone.log" "$host.local.	AAAA	fe80:"
check "dnssd -B types" "$a/types.log" 'TYPE     _hosttest._tcp'
check "Nearby kinds" "$a/nearby-kinds.log" 'Web server (HTTP)'
check "Nearby web PORTS" "$a/nearby-web.log" 'HostWeb .* port 8000  (192.168.166.1, fe80:'
check "Nearby web info" "$a/nearby-web.log" 'info: path=/w'
check "Handshake reached" "$a/handshake.log" 'Reached "HostTest"'
check "Handshake port" "$a/handshake.log" 'Port:  9999'
check "Handshake IPv4" "$a/handshake.log" 'IP:    192.168.166.1'
check "Handshake IPv6" "$a/handshake.log" 'IP:    fe80:'
check "Handshake nobody" "$a/handshake-none.log" 'Could not reach "Nobody"'
check "browse: ADD v=1" "$a/change.log" '^ADD      ChangeTest .* 7001  v=1$'
check "browse: UPDATE v=2 (followed)" "$a/change.log" '^UPDATE   ChangeTest .* 7001  v=2$'
check "browse: REMOVE" "$a/change.log" '^REMOVE   ChangeTest'
echo "tools: $fails failed"
