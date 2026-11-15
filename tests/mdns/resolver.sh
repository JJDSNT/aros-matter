#!/bin/bash
# resolver.sh OUTDIR - the system resolver's .local names (AROSTCP
# api/res_mdns.c) on hosted AROS with two links (taps aros0 and aros1),
# against the host's Avahi. Two boots:
#   1. with mdnsd: the host's name (Avahi), AROS's own, a name nobody has,
#      a name only the host table has, a name both have (the table wins),
#      getaddrinfo()'s IPv6 link-local addresses with their zones and a TCP
#      connect() to each address; tcpdump on port 53 of both links: a
#      control name goes to the DNS, no .local name does;
#   2. without mdnsd: a .local name fails at once (TRY_AGAIN, EAI_AGAIN),
#      the host table and the DNS work as before.
# MODE=amiga runs boot 1 and 2 on the emulated Amiga (one link). RESOLVTEST:
# the test binary built for the target. Prints PASS/FAIL per check.
set -u
out=$1; mkdir -p "$out"
root=$(cd "$(dirname "$0")/../.." && pwd)
mode=${MODE:-hosted}
"$root/tools/tap-up.sh" 0 >/dev/null
two=0
if [ "$mode" = hosted ]; then
  "$root/tools/tap-up.sh" 1 >/dev/null && { two=1; export AROS_TAP2_IP=192.168.167.2; }
fi
host=$(avahi-resolve -4 -a 192.168.166.1 2>/dev/null | awk '{print $2}')
host=${host%.local}
[ -n "$host" ] || host=$(hostname)
port=18080
fails=0
pass() { echo "PASS $*"; }
fail() { echo "FAIL $*"; fails=$((fails + 1)); }

boot() {    # boot NAME PRE...: run the script with PRE lines before startnet
  local name=$1; shift
  local pre="" l
  for l in "$@"; do pre="$pre$l"$'\n'; done
  [ "$mode" = amiga ] && pre="${pre}Delete >NIL: SYS:System/Network/AROSTCP/db/services.d/timesync QUIET"$'\n'
  cat > "$out/$name.script" <<EOS
Echo "NAMESERVER 192.168.166.1" >>SYS:System/Network/AROSTCP/db/netdb-myhost
Echo "HOST 192.168.166.77 hostsonly.local" >>SYS:System/Network/AROSTCP/db/netdb-myhost
Echo "HOST 192.168.166.77 both.local" >>SYS:System/Network/AROSTCP/db/netdb-myhost
$pre
Execute SYS:System/Network/AROSTCP/S/startnet
Wait 15
C:resolvtest $host.local arosbox.local nobody-here.local hostsonly.local both.local control.example >SYS:out/names.log
C:resolvtest -c $host.local $port >SYS:out/connect.log
C:resolvtest -b nobody-here.local >SYS:out/break.log
C:resolvtest -i eth0 eth1 >SYS:out/ifs.log
C:resolvtest -r $host.local 50 >SYS:out/repeat.log
C:resolvtest -k mdns >SYS:out/kill.log
Wait 3
C:resolvtest $host.local >SYS:out/stopped.log
Run >NIL: SYS:System/Network/Services/mdnsd
Wait 10
C:resolvtest $host.local >SYS:out/restarted.log
C:resolvtest -r $host.local 20 >SYS:out/repeat2.log
EOS
  local caps=""
  for i in aros0 aros1; do
    [ "$i" = aros1 ] && [ "$two" = 0 ] && continue
    sudo -n timeout 900 tcpdump -i $i -n -s0 -U -w "$out/$name-$i-dns.pcap" port 53 >/dev/null 2>&1 &
  done
  if [ "$mode" = amiga ]; then
    AMIGA_TAP_IP=192.168.166.2 AMIGA_RUN_TIMEOUT=600 \
      "$root/tools/amiga-run.sh" "$out/$name" "$out/$name.script" "$RESOLVTEST" > "$out/$name-run.txt" 2>&1
  else
    AROS_TAP_IP=192.168.166.2 AROS_RUN_TIMEOUT=200 \
      "$root/tools/hosted-run.sh" "$out/$name" "$out/$name.script" "$RESOLVTEST" > "$out/$name-run.txt" 2>&1
  fi
  sudo -n pkill -INT -f "tcpdump -i aros[01] -n -s0 -U -w $out/$name-" 2>/dev/null
  sleep 1
  for i in aros0 aros1; do
    [ -f "$out/$name-$i-dns.pcap" ] && tcpdump -r "$out/$name-$i-dns.pcap" -n 2>/dev/null > "$out/$name-$i-dns.txt"
  done
  cat "$out/$name/out/names.log" "$out/$name/out/connect.log" 2>/dev/null
}

line() { grep "^$1 $2 " "$out/$3/out/names.log" 2>/dev/null; }
ms() { line "$1" "$2" "$3" | awk '{print $3}'; }
dns_has() { cat "$out/$1"-aros*-dns.txt 2>/dev/null | grep -c "$2"; }

# the host answers on each link, and serves TCP on both families for -c
avahi-publish -a -R both.local 192.168.166.88 >/dev/null 2>&1 & pubboth=$!
# each connection accepted: "<local address> <tap it came in by> <peer>",
# the host's own record of the link, to hold the AROS side's zones against
python3 - "$port" "$out/accepted.txt" <<'PY' > /dev/null 2>&1 & srv=$!
import socket, sys
s = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
s.bind(("::", int(sys.argv[1]))); s.listen(16); s.settimeout(600)
log = open(sys.argv[2], "w", buffering=1)
while True:
    c, peer = s.accept()
    local = c.getsockname()
    ifn = socket.if_indextoname(local[3]) if local[3] else "-"
    log.write("%s %s %s\n" % (local[0], ifn, peer[0]))
    c.close()
PY

echo "== boot 1: with mdnsd"
boot with
b=with
l=$(line hbn $host.local $b)
echo "$l" | grep -q " 192.168.166.1" && pass "gethostbyname($host.local): $(echo $l | cut -d' ' -f4-)" || fail "gethostbyname($host.local): $l"
l=$(line hbn2 $host.local $b)
# the host's taps have link-local IPv6 addresses only: a hostent cannot carry
# their zone, so there is none to give (NO_DATA)
if ip -6 addr show dev aros0 scope global | grep -q inet6; then
  echo "$l" | grep -qv "none" && pass "gethostbyname2($host.local): global" || fail "gethostbyname2: $l"
else
  echo "$l" | grep -q "none h_errno=4" && pass "gethostbyname2($host.local): link-local only -> NO_DATA" || fail "gethostbyname2($host.local): $l"
fi
l=$(line gai $host.local $b)
echo "$l" | grep -q " 4:192.168.166.1" && pass "getaddrinfo($host.local) IPv4" || fail "getaddrinfo IPv4: $l"
zones=$(echo "$l" | grep -o " 6:fe80::[^ ]*%[0-9]*" | sed 's/.*%//' | sort -u | wc -l)
nozone=$(echo "$l" | grep -o " 6:fe80::[^ %]*\( \|$\)" | wc -l)
want=$((two + 1))
[ "$zones" -ge "$want" ] && [ "$nozone" -eq 0 ] && pass "getaddrinfo($host.local) link-local with a zone on each of $want links" || fail "getaddrinfo link-local zones $zones (want $want), without zone $nozone: $l"
# the zone is the interface the address was learned on: the host's own
# link-local address of each tap (not fe80::1, which both have) must come
# with that link's AROS interface index
ok=1
for t in aros0 aros1; do
  [ "$t" = aros1 ] && [ "$two" = 0 ] && continue
  e=$([ $t = aros0 ] && echo eth0 || echo eth1)
  idx=$(awk -v e=$e '$1=="if" && $2==e {print $3}' "$out/$b/out/ifs.log")
  for a in $(ip -6 addr show dev $t scope link | awk '/inet6/{sub("/.*","",$2); print $2}' | grep -v '^fe80::1$'); do
    echo "$l" | grep -q " 6:$a%$idx\( \|$\)" || { ok=0; echo "  $a of $t: want zone $idx ($e)"; }
  done
done
[ $ok = 1 ] && pass "each link-local address has the zone of the link it is on" || fail "zones do not match the links: $l"
l=$(line hbn arosbox.local $b)
echo "$l" | grep -q " 192.168.166.2" && pass "gethostbyname(arosbox.local), AROS's own" || fail "own name: $l"
l=$(line hbn nobody-here.local $b); t=$(ms hbn nobody-here.local $b)
echo "$l" | grep -q "none h_errno=1" && [ "${t:-0}" -ge 2500 ] && [ "${t:-0}" -le 4500 ] && pass "nobody-here.local: HOST_NOT_FOUND after ${t} ms" || fail "nobody-here.local: $l"
l=$(line gai nobody-here.local $b)
echo "$l" | grep -q "error 8" && pass "getaddrinfo(nobody-here.local): EAI_NONAME" || fail "getaddrinfo nobody: $l"
l=$(line hbn hostsonly.local $b); t=$(ms hbn hostsonly.local $b)
echo "$l" | grep -q " 192.168.166.77" && [ "${t:-9999}" -lt 500 ] && pass "hostsonly.local from the host table (${t} ms)" || fail "hostsonly.local: $l"
l=$(line hbn both.local $b)
echo "$l" | grep -q " 192.168.166.77" && ! echo "$l" | grep -q "\.88" && pass "both.local: the host table before mDNS" || fail "both.local: $l"
l=$(line gai both.local $b)
echo "$l" | grep -q "4:192.168.166.77" && ! echo "$l" | grep -q "\.88" && pass "getaddrinfo(both.local): the host table before mDNS" || fail "getaddrinfo both.local: $l"
c=$(grep -c "^conn .* ok" "$out/$b/out/connect.log" 2>/dev/null); n=$(grep -c "^conn " "$out/$b/out/connect.log" 2>/dev/null)
[ "$c" -ge $((want + 1)) ] && [ "$c" -eq "$n" ] && pass "connect() to each of $n addresses of $host.local" || fail "connect: $c of $n ok"
# fe80::1 is on both taps: each connect() to it must reach the host by the
# link its zone names - the host's record says which tap it came by
if [ "$two" = 1 ]; then
  i0=$(awk '$2=="eth0"{print $3}' "$out/$b/out/ifs.log"); i1=$(awk '$2=="eth1"{print $3}' "$out/$b/out/ifs.log")
  order=$(grep -o "^conn fe80::1%[0-9]* ok" "$out/$b/out/connect.log" | sed 's/.*%//; s/ ok//' | sed "s/^$i0\$/aros0/; s/^$i1\$/aros1/" | tr '\n' ' ')
  came=$(awk '$1 ~ /^fe80::1(%|$)/ {print $2}' "$out/accepted.txt" | tr '\n' ' ')
  [ -n "$order" ] && [ "$order" = "$came" ] && pass "fe80::1 by each zone reached the host by that link ($came)" || fail "fe80::1: zones say '$order', host saw '$came'"
fi
[ "$(dns_has $b control.example)" -ge 1 ] && pass "control.example went to the DNS" || fail "control.example not seen on port 53 (capture?)"
[ "$(dns_has $b '\.local')" -eq 0 ] && pass "no .local name went to the DNS" || fail ".local on port 53: $(cat "$out/$b"-aros*-dns.txt | grep '\.local' | head -3)"
l=$(cat "$out/$b/out/break.log" 2>/dev/null)
echo "$l" | grep -q "none h_errno=2 errno=4 gai=2" && [ "$(echo $l | awk '{print $3}')" -lt 1000 ] && pass "Ctrl-C: TRY_AGAIN, EINTR, EAI_AGAIN at once" || fail "Ctrl-C: $l"
l=$(cat "$out/$b/out/repeat.log" 2>/dev/null); d=$(echo "$l" | awk '{print $4}')
[ -n "$d" ] && [ "$d" -lt 4096 ] && pass "50 look-ups after the first: free memory down by $d bytes" || fail "repeated look-ups: $l"
# mdnsd stopped (Ctrl-C) and started again in the same boot
if grep -q "sent" "$out/$b/out/kill.log" 2>/dev/null; then
  l=$(grep "^hbn " "$out/$b/out/stopped.log"); t=$(echo "$l" | awk '{print $3}')
  echo "$l" | grep -q "none h_errno=2" && [ "${t:-9999}" -lt 500 ] && grep -q "error 2" "$out/$b/out/stopped.log" && pass "mdnsd stopped: TRY_AGAIN / EAI_AGAIN at once (${t} ms)" || fail "mdnsd stopped: $(cat "$out/$b/out/stopped.log")"
  grep -q "^hbn $host.local [0-9]* 192.168.166.1" "$out/$b/out/restarted.log" && grep -q "4:192.168.166.1" "$out/$b/out/restarted.log" && pass "mdnsd started again: found again" || fail "mdnsd restarted: $(cat "$out/$b/out/restarted.log")"
  l=$(cat "$out/$b/out/repeat2.log" 2>/dev/null); d=$(echo "$l" | awk '{print $4}')
  [ -n "$d" ] && [ "$d" -lt 4096 ] && pass "20 look-ups after the restart: free memory down by $d bytes" || fail "after restart: $l"
else
  fail "mdnsd's task not found to stop"
fi

echo "== boot 2: without mdnsd"
boot without "Delete >NIL: SYS:System/Network/AROSTCP/db/services.d/mdns QUIET"
b=without
l=$(line hbn $host.local $b); t=$(ms hbn $host.local $b)
echo "$l" | grep -q "none h_errno=2" && [ "${t:-9999}" -lt 500 ] && pass "no mdnsd: $host.local TRY_AGAIN at once (${t} ms)" || fail "no mdnsd hbn: $l"
l=$(line gai $host.local $b)
echo "$l" | grep -q "error 2" && pass "no mdnsd: getaddrinfo EAI_AGAIN" || fail "no mdnsd gai: $l"
l=$(line hbn hostsonly.local $b)
echo "$l" | grep -q " 192.168.166.77" && pass "no mdnsd: the host table as before" || fail "no mdnsd hostsonly: $l"
[ "$(dns_has $b control.example)" -ge 1 ] && pass "no mdnsd: the DNS as before" || fail "no mdnsd: control.example not on port 53"
[ "$(dns_has $b '\.local')" -eq 0 ] && pass "no mdnsd: no .local name went to the DNS" || fail "no mdnsd: .local on port 53"

kill $pubboth $srv 2>/dev/null
echo "resolver: $fails failed"
