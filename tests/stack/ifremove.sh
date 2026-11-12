#!/bin/sh
# ifremove.sh OUTDIR - B37: an interface that leaves a running stack gives
# its receive clusters back. Hosted AROS with eth0 and eth1 (taps aros0,
# aros1); eth1 leaves the configuration (reloaded in place), comes back and
# leaves again; "netstat -m" after each step. Expected: clusters in use go
# down by eth1's share when it leaves and the total does not grow when it
# comes back (before the fix: 512 -> 512 -> 768 -> 768).
set -u
out=$1; mkdir -p "$out"
root=$(cd "$(dirname "$0")/../.." && pwd)
"$root/tools/tap-up.sh" 0 >/dev/null && "$root/tools/tap-up.sh" 1 >/dev/null
cc=$(python3 -c "import sys;sys.path.insert(0,'$root/tests/tcp');import run_tcp;print(run_tcp.CROSS)")
"$cc" --sysroot "${AROS_HOSTED_IMAGE:?}/Developer" -O2 -o "$out/ifreload" "$root/tests/stack/ifreload.c" || exit 1
{ echo "Execute SYS:System/Network/AROSTCP/S/startnet"; echo "Wait 6"
  echo "C:netstat -m >SYS:out/1-start.log"
  echo "C:ifreload drop eth1"; echo "Wait 2"; echo "C:netstat -m >SYS:out/2-gone.log"
  echo "C:ifreload"; echo "Wait 2"; echo "C:netstat -m >SYS:out/3-back.log"
  echo "C:ifreload drop eth1"; echo "Wait 2"; echo "C:netstat -m >SYS:out/4-gone.log"; } > "$out/s.script"
AROS_TAP_IP=192.168.166.2 AROS_TAP2_IP=192.168.167.2 AROS_RUN_TIMEOUT=120 \
  "$root/tools/hosted-run.sh" "$out/run" "$out/s.script" "$out/ifreload" >/dev/null 2>&1
for f in "$out"/run/out/[0-9]-*.log; do printf '%s: ' "$(basename "$f" .log)"; grep 'clusters in use' "$f"; done
a=$(sed -n 's|^\([0-9]*\)/.*clusters in use|\1|p' "$out/run/out/1-start.log")
b=$(sed -n 's|^\([0-9]*\)/.*clusters in use|\1|p' "$out/run/out/2-gone.log")
c=$(sed -n 's|^\([0-9]*\)/.*clusters in use|\1|p' "$out/run/out/3-back.log")
[ -n "$a" ] && [ "$b" -lt "$a" ] && [ "$c" -le "$a" ] && echo PASS || { echo FAIL; exit 1; }
