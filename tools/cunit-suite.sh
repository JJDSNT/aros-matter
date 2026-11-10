#!/bin/sh
# cunit-suite.sh OUTDIR - run every cunit-net suite (developer/debug/test/net/
# socket/mmakefile.src) on hosted AROS with two taps (tools/tap-up.sh 0 and 1),
# then print per suite "name basic-run/failed automated-run/failed", and the
# suites with a failure or a missing run after "== FAIL".
# AROS_SRC, AROS_BUILD as in aros-bld.sh; AROS_AROSTCP to boot another binary.
set -u
out=$1
src=${AROS_SRC:-$HOME/AROS-ipv6}
here=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$out"
script=$out/suite.script
{ echo "Execute SYS:System/Network/AROSTCP/S/startnet"; echo "Wait 6"
  for t in $(sed -n '/CUNITSOCKETTESTFILES/,/^$/p' "$src/developer/debug/test/net/socket/mmakefile.src" | grep -o "cunit-net-[a-z0-9]*"); do
    a=""; [ "$t" = cunit-net-tcpinfo ] && a=" eth0"
    echo "SYS:Developer/Debug/Tests/cunit/net/socket/$t$a >SYS:out/${t#cunit-net-}.log"
  done; } > "$script"
AROS_HOSTED_IMAGE=${AROS_HOSTED_IMAGE:-${AROS_BUILD:-$HOME/aros-build-ipv6-hosted-claude}/bin/linux-x86_64/AROS} \
AROS_TAP_IP=192.168.166.2 AROS_TAP2_IP=192.168.167.2 AROS_RUN_TIMEOUT=${AROS_RUN_TIMEOUT:-1500} \
  "$here/hosted-run.sh" "$out/run" "$script" >/dev/null 2>&1
for f in "$out"/run/out/*.log; do n=$(basename "$f" .log); [ "$n" = done ] && continue
  printf "%s " "$n"; awk '/Tests  *:/{printf "%s/%s ", $3, $4} END{print ""}' "$f"; done > "$out/summary.txt"
cat "$out/summary.txt"
echo "== $(wc -l < "$out/summary.txt") suites; FAIL:"
awk '{split($2,a,"/"); split($3,b,"/"); if (a[2]!="0" || b[2]!="0" || NF<3) print}' "$out/summary.txt"
