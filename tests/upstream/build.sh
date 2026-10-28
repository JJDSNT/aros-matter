#!/bin/sh
# build.sh OUTDIR - cross-compile the upstream-style cunit tests in this tree
# against an AROS hosted build (AROS_BUILD, default ~/aros-build-ipv6-hosted)
# and the upstream socktest.h (AROS_SRC, default ~/AROS-ipv6).
set -eu
here=$(cd "$(dirname "$0")" && pwd)
out=${1:-$here/out}; mkdir -p "$out"
build=${AROS_BUILD:-$HOME/aros-build-ipv6-hosted}
src=${AROS_SRC:-$HOME/AROS-ipv6}
cc=${AROS_CROSS:-$HOME/aros-midihub/build-aros-linux/bin/linux-x86_64/tools/crosstools/x86_64-aros-gcc}
sdk=$build/bin/linux-x86_64/AROS/Developer/SDK/Extras
for f in "$here"/developer/debug/test/net/socket/cunit-*.c; do
    n=$(basename "$f" .c)
    "$cc" --sysroot "$build/bin/linux-x86_64/AROS/Developer" -O2 -Wall -Wno-pointer-sign \
        -I"$src/developer/debug/test/net/socket" -I"$sdk/include" \
        -iquote "$src/workbench/network/stacks/AROSTCP/bsdsocket/net" \
        -o "$out/$n" "$f" -L"$sdk/lib" -lcunit
    echo "built $out/$n"
done
