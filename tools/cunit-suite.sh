#!/bin/sh
# cunit-suite.sh OUTDIR - run every cunit-net suite (developer/debug/test/net/
# socket/mmakefile.src) on hosted AROS with two taps (tools/tap-up.sh 0 and 1),
# then print per suite "name basic-run/failed automated-run/failed", and the
# suites with a failure or a missing run after "== FAIL".
# AROS_BUILD as in aros-bld.sh (AROS_SRC, if given, must be its tree); AROS_AROSTCP to boot another binary;
# PROTOCOLS (e.g. INET6) for a stack with only some families.
set -u
out=$1
here=$(cd "$(dirname "$0")" && pwd)
build=${AROS_BUILD:-$HOME/aros-build-ipv6-hosted-claude}
# the suites are those of the tree the build was made from (its Makefile's
# SRCDIR), never another worktree's: #2218's first clean run listed
# ~/AROS-ipv6's and left out four of the PR's new suites (Kal's review)
built=$(sed -n 's/^SRCDIR := //p' "$build/Makefile" 2>/dev/null)
src=${AROS_SRC:-$built}
[ -n "$src" ] || { echo "no source tree for $build" >&2; exit 1; }
if [ -n "$built" ] && [ "$(cd "$src" && pwd)" != "$(cd "$built" && pwd)" ]; then
  echo "AROS_SRC $src is not the tree $build was built from ($built)" >&2; exit 1
fi
echo "suites of $src ($(git -C "$src" rev-parse --short HEAD)), build $build" >&2
mkdir -p "$out"
# the taps go away when WSL restarts: without them tap.device does not open,
# the stack does not start and every suite skips itself
"$here/tap-up.sh" 0 >/dev/null && "$here/tap-up.sh" 1 >/dev/null || { echo "tap-up failed" >&2; exit 1; }
script=$out/suite.script
{ [ -n "${PROTOCOLS:-}" ] && echo "Echo \"PROTOCOLS=$PROTOCOLS\" >>SYS:System/Network/AROSTCP/db/general.config"
  echo "Execute SYS:System/Network/AROSTCP/S/startnet"; echo "Wait 6"
  for t in $(sed -n '/CUNITSOCKETTESTFILES/,/^$/p' "$src/developer/debug/test/net/socket/mmakefile.src" | grep -o "cunit-net-[a-z0-9]*"); do
    a=""; [ "$t" = cunit-net-tcpinfo ] && a=" eth0"
    echo "SYS:Developer/Debug/Tests/cunit/net/socket/$t$a >SYS:out/${t#cunit-net-}.log"
  done; } > "$script"
AROS_HOSTED_IMAGE=${AROS_HOSTED_IMAGE:-$build/bin/linux-x86_64/AROS} \
AROS_TAP_IP=192.168.166.2 AROS_TAP2_IP=192.168.167.2 AROS_RUN_TIMEOUT=${AROS_RUN_TIMEOUT:-1500} \
  "$here/hosted-run.sh" "$out/run" "$script" >/dev/null 2>&1
for f in "$out"/run/out/*.log; do n=$(basename "$f" .log); [ "$n" = done ] && continue
  printf "%s " "$n"; awk '/Tests  *:/{printf "%s/%s ", $3, $4} END{print ""}' "$f"; done > "$out/summary.txt"
cat "$out/summary.txt"
echo "== $(wc -l < "$out/summary.txt") suites; FAIL:"
awk '{split($2,a,"/"); split($3,b,"/"); if (a[2]!="0" || b[2]!="0" || NF<3) print}' "$out/summary.txt"
