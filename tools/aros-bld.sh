#!/bin/sh
# aros-bld.sh TARGET... - make each target in the hosted build; fail loudly on
# any compiler/linker error (make -s can exit 0 with them); print the AROSTCP
# binary's time, to check it is new before testing.
# After switching branches, start with network-includes-copy (the headers in
# workbench/network/common/include are copied into the build).
cd "${AROS_BUILD:-$HOME/aros-build-ipv6-hosted-claude}" || exit 1
for t in "$@"; do
  out=$(make -s "$t" 2>&1); rc=$?
  if [ $rc -ne 0 ] || echo "$out" | grep -qE "error:|Error [0-9]|undefined reference|multiple definition"; then
    echo "BUILD FAILED: $t (rc $rc)"
    echo "$out" | grep -E -B2 -A3 "error:|Error [0-9]|undefined reference|multiple definition" | head -30
    exit 1
  fi
done
ls -la --time-style=+%T bin/linux-x86_64/AROS/System/Network/AROSTCP/C/AROSTCP | awk '{print "AROSTCP", $6}'
