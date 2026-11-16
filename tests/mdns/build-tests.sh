#!/bin/sh
# build-tests.sh OUTDIR [hosted|m68k]... - the mDNS test programs
# (dnssdtest, dnssd_gone, resolvtest, memsvc) for each target, all with the same
# flags: OUTDIR/<target>/<program>, and OUTDIR/<target>/<program>.log with
# the compiler's output (no warning expected; m68k's inline library calls
# give -Wvolatile-register-var, which is left out of the log check).
#
# -fno-common: the m68k cross compiler (GCC 6.5) makes COMMON symbols of
# uninitialised globals by default, and AROS m68k does not load a program
# that has them ("file is not executable"); the AROS build passes it too.
#
# AROS_HOSTED_BUILD / AROS_M68K_BUILD: the builds whose SDK (sysroot) the
# programs are compiled against (~/aros-build-ipv6-hosted-claude,
# ~/aros-build-ipv6-m68k-claude); HOSTED_CC / M68K_CC the compilers.
set -u
out=$1; shift
targets=${*:-hosted m68k}
here=$(cd "$(dirname "$0")" && pwd)
flags="-std=gnu99 -O2 -Wall -Wno-pointer-sign -fno-common"
fails=0
for t in $targets; do
  case $t in
    hosted)
      cc=${HOSTED_CC:-$HOME/aros-midihub/build-aros-linux/bin/linux-x86_64/tools/crosstools/x86_64-aros-gcc}
      sys=${AROS_HOSTED_BUILD:-$HOME/aros-build-ipv6-hosted-claude}/bin/linux-x86_64/AROS/Developer ;;
    m68k)
      cc=${M68K_CC:-$HOME/aros-build-emu68-m68k/bin/linux-x86_64/tools/crosstools/m68k-aros-gcc}
      sys=${AROS_M68K_BUILD:-$HOME/aros-build-ipv6-m68k-claude}/bin/amiga-m68k/AROS/Developer ;;
    *) echo "unknown target $t" >&2; exit 2 ;;
  esac
  mkdir -p "$out/$t"
  for p in dnssdtest dnssd_gone resolvtest memsvc; do
    if "$cc" --sysroot="$sys" -I"$sys/include" -L"$sys/lib" $flags \
         -o "$out/$t/$p" "$here/$p.c" > "$out/$t/$p.log" 2>&1 &&
       ! grep -v "Wvolatile-register-var\|^In file included\|^ *from \|note:\|^ *|\|^ *[0-9]* |" \
         "$out/$t/$p.log" | grep -q "warning\|error"; then
      echo "$t/$p ok"
    else
      echo "$t/$p FAILED: $out/$t/$p.log"; fails=$((fails + 1))
    fi
  done
done
exit $fails
