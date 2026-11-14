#!/bin/sh
# ifconf_grow.sh OUTDIR [N] - does ifconfig -a / ip addr see the whole
# SIOCGIFCONF list when it is long? (#2277: the buffers grow until it fits)
#
# How AROS takes IPv4 aliases (workbench/network/common/C/ifconfig.c,
# netinet/in.c): "ifconfig eth0 A netmask M alias" (or "alias A ...") is one
# SIOCAIFADDR - "alias" only stops ifconfig from deleting the current
# address first (SIOCDIFADDR). in_control() appends an in_ifaddr per new
# address, with no limit but memory; in_ifinit() adds the network's route,
# and a second address in the same network gets EEXIST from rtinit() - the
# address stays, ifconfig says "File exists". /32 masks give each its own
# route. Every address is an entry of SIOCGIFCONF (net/if.c ifconf()).
#
# Neither ifconfig nor ip prints the aliases: both print an interface's
# IPv4 address with SIOCGIFADDR (the first one), and use the list only for
# the interfaces' names, skipping repeated entries. What a cut-off list
# loses is what comes after the cut: eth1, after eth0 and its N aliases.
# So: N /32 aliases on eth0, then eth1 must be in ifconfig -a and in
# ip addr. Also 200 IPv6 addresses (ip addr prints those from the list).
# Hosted AROS, eth0 and eth1 (tools/tap-up.sh 0 and 1); AROS_HOSTED_IMAGE.
set -u
out=$1; n=${2:-300}; mkdir -p "$out"
root=$(cd "$(dirname "$0")/../.." && pwd)
"$root/tools/tap-up.sh" 0 >/dev/null && "$root/tools/tap-up.sh" 1 >/dev/null || exit 1
{ echo "Execute SYS:System/Network/AROSTCP/S/startnet"; echo "Wait 6"
  echo "C:ifconfig -a >SYS:out/if0.log"; echo "C:ip addr >SYS:out/ip0.log"
  i=1; while [ $i -le $n ]; do
    echo "C:ifconfig eth0 10.9.$((i / 250)).$((i % 250 + 1)) netmask 255.255.255.255 alias *>>SYS:out/alias.err"
    i=$((i + 1)); done
  echo "C:ifconfig -a >SYS:out/if4.log"; echo "C:ip addr >SYS:out/ip4.log"
  i=1; while [ $i -le 200 ]; do
    printf 'C:ifconfig eth0 inet6 2001:db8::%x prefixlen 128 alias *>>SYS:out/alias6.err\n' $i
    i=$((i + 1)); done
  echo "Wait 3"; echo "C:ip addr >SYS:out/ip6.log"; } > "$out/s.script"
AROS_TAP_IP=192.168.166.2 AROS_TAP2_IP=192.168.167.2 AROS_RUN_TIMEOUT=300 \
  "$root/tools/hosted-run.sh" "$out/run" "$out/s.script" > "$out/run.txt" 2>&1
o=$out/run/out
has() { grep -q "$2" "$o/$1" 2>/dev/null && echo yes || echo NO; }
echo "alias errors: $(cat "$o/alias.err" 2>/dev/null | grep -c .) (IPv4), $(cat "$o/alias6.err" 2>/dev/null | grep -c .) (IPv6)"
echo "before:          ifconfig -a eth1 $(has if0.log '^eth1:'), ip addr eth1 $(has ip0.log ': eth1:')"
echo "$n IPv4 aliases: ifconfig -a eth1 $(has if4.log '^eth1:'), ip addr eth1 $(has ip4.log ': eth1:')"
echo "200 IPv6:        ip addr shows $(grep -c 'inet6 2001:db8::' "$o/ip6.log" 2>/dev/null) of 200, eth1 $(has ip6.log ': eth1:')"
