#!/bin/sh
# alias_owner.sh OUTDIR - Kal's case on #2218: AROS (eth0 192.168.166.2)
# adds the host's own address 192.168.166.1/32 as an alias; it is marked
# duplicated; the host pings AROS all the while. Expected: every echo
# after the alias is in place is answered (before the fix: none).
set -u
out=$1; mkdir -p "$out"
root=$(cd "$(dirname "$0")/../.." && pwd)
img=${AROS_HOSTED_IMAGE:?}
"$root/tools/tap-up.sh" 0 >/dev/null
cc=$(python3 -c "import sys;sys.path.insert(0,'$root/tests/tcp');import run_tcp;print(run_tcp.CROSS)")
"$cc" --sysroot "$img/Developer" -O2 -o "$out/alias_owner" "$root/tests/ipv4/alias_owner.c" || exit 1
printf 'Execute SYS:System/Network/AROSTCP/S/startnet\nWait 8\nC:alias_owner eth0 192.168.166.1 20 >SYS:out/alias.log\n' > "$out/s.script"
( for i in $(seq 1 240); do [ -e "$out/aros/AROS/out/alias-ready" ] && break; sleep 0.5; done
  ping -c 10 -i 1 -W 1 192.168.166.2 > "$out/ping.txt" 2>&1 ) & p=$!
AROS_TAP_IP=192.168.166.2 AROS_RUN_TIMEOUT=120 "$root/tools/hosted-run.sh" "$out/aros" "$out/s.script" "$out/alias_owner" >/dev/null 2>&1
wait $p
cat "$out/aros/out/alias.log"; tail -3 "$out/ping.txt"
grep -q " 0% packet loss" "$out/ping.txt" && echo PASS || { echo FAIL; exit 1; }
