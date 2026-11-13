#!/bin/sh
# onevent.sh OUTDIR - tap.device's link events (S2_ONEVENT) straight to the
# device, without the stack (tests/tap/onevent.c, on unit 1 = tap aros1):
# two openers told of the host taking aros1 down, abort, an opener closing
# with a request waiting, the link coming back, S2_ONLINE, the last close.
# Needs sudo -n (ip link). AROS_HOSTED_IMAGE as for tools/hosted-run.sh.
set -u
out=$1; mkdir -p "$out"
root=$(cd "$(dirname "$0")/../.." && pwd)
"$root/tools/tap-up.sh" 1 >/dev/null || exit 1
cc=$(python3 -c "import sys;sys.path.insert(0,'$root/tests/tcp');import run_tcp;print(run_tcp.CROSS)")
"$cc" --sysroot "${AROS_HOSTED_IMAGE:?}/Developer" -O2 -o "$out/onevent" "$root/tests/tap/onevent.c" || exit 1
echo "C:onevent 1 >SYS:out/onevent.log" > "$out/s.script"
AROS_RUN_TIMEOUT=90 "$root/tools/hosted-run.sh" "$out/run" "$out/s.script" "$out/onevent" > "$out/run.txt" 2>&1 &
run=$!
d="$out/run/AROS/out"
wait_for() { t=0; while [ ! -f "$d/$1" ] && [ $t -lt 120 ]; do sleep 0.5; t=$((t+1)); done; [ -f "$d/$1" ]; }
if wait_for ready1; then sudo -n ip link set aros1 down; touch "$d/go1"; fi
if wait_for ready2; then sudo -n ip link set aros1 up; touch "$d/go2"; fi
sudo -n ip link set aros1 up
wait $run
cat "$out/run/out/onevent.log"
grep -q "RESULT [0-9]* passed, 0 failed" "$out/run/out/onevent.log"
