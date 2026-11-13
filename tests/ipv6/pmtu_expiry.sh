#!/bin/sh
# pmtu_expiry.sh OUTDIR - tests/ipv6/pmtu_expiry.c on hosted AROS with eth0
# and eth1 (taps aros0, aros1): the same link-local destination's path MTU
# on two links, across the real 600 s expiry. About 12 minutes.
set -u
out=$1; mkdir -p "$out"
root=$(cd "$(dirname "$0")/../.." && pwd)
img=${AROS_HOSTED_IMAGE:?}
"$root/tools/tap-up.sh" 0 >/dev/null && "$root/tools/tap-up.sh" 1 >/dev/null
cc=$(python3 -c "import sys;sys.path.insert(0,'$root/tests/tcp');import run_tcp;print(run_tcp.CROSS)")
"$cc" --sysroot "$img/Developer" -std=gnu99 -O2 -o "$out/pmtu_expiry" "$root/tests/ipv6/pmtu_expiry.c" || exit 1
printf 'Execute SYS:System/Network/AROSTCP/S/startnet\nWait 8\nC:pmtu_expiry >SYS:out/pmtu.log\n' > "$out/s.script"
AROS_TAP_IP=192.168.166.2 AROS_TAP2_IP=192.168.167.2 AROS_RUN_TIMEOUT=900 \
  "$root/tools/hosted-run.sh" "$out/aros" "$out/s.script" "$out/pmtu_expiry" >/dev/null 2>&1
cat "$out/aros/out/pmtu.log"
grep -q '^PASS' "$out/aros/out/pmtu.log"
