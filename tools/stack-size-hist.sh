#!/bin/sh
# stack-size-hist.sh OUTDIR COMMIT... - build AROSTCP for m68k (and, with
# HOSTED=1, x86_64 hosted) at each commit, in a separate worktree, and keep
# the binary and its object files: OUTDIR/<commit>/{m68k,x86_64}/.
# Only workbench/network (stack, headers, tools) is taken from the commit;
# the rest of the tree is the worktree's (upstream master), so the compiler
# and flags are the same for every commit.
# HIST_SRC (~/AROS-hist), HIST_M68K (~/aros-build-hist-m68k),
# HIST_HOSTED (~/aros-build-hist-hosted).
set -u
out=$1; shift
src=${HIST_SRC:-$HOME/AROS-hist}
m68k=${HIST_M68K:-$HOME/aros-build-hist-m68k}
hosted=${HIST_HOSTED:-$HOME/aros-build-hist-hosted}
gen=gen/workbench/network/stacks/AROSTCP/bsdsocket
for c in "$@"; do
  d=$out/$c; mkdir -p "$d"
  # a checkout of a path does not remove the files the commit lacks: clear it first
  rm -rf "$src/workbench/network"
  git -C "$src" checkout -q "$c" -- workbench/network || { echo "$c: checkout failed"; continue; }
  for t in m68k x86_64; do
    if [ $t = m68k ]; then b=$m68k; arch=amiga-m68k; else [ "${HOSTED:-0}" = 1 ] || continue; b=$hosted; arch=linux-x86_64; fi
    rm -rf "$b/bin/$arch/$gen" "$b/bin/$arch/AROS/System/Network/AROSTCP/C/AROSTCP" \
           "$b/bin/$arch/AROS/System/Network/AROSTCP/Libs"
    # the network headers installed in the SDK are the commit's own; a public
    # header the commit did not have yet (net/bpf.h, from 2026-10) would hide
    # the stack's private one of the same name, so it is put aside meanwhile
    sdkbpf=$b/bin/$arch/AROS/Developer/include/net/bpf.h
    hid=0
    if ! git -C "$src" cat-file -e "$c:workbench/network/common/include/net/bpf.h" 2>/dev/null && [ -f "$sdkbpf" ]; then
      mv "$sdkbpf" "$sdkbpf.hist"; hid=1
    fi
    ( cd "$b" && make -s network-includes-copy && { [ $hid = 0 ] || rm -f "$sdkbpf"; } &&
      make -s workbench-network-stacks-arostcp ) > "$d/build-$t.log" 2>&1
    [ $hid = 1 ] && mv "$sdkbpf.hist" "$sdkbpf"
    bin=$b/bin/$arch/AROS/System/Network/AROSTCP/C/AROSTCP
    if [ -f "$bin" ]; then
      mkdir -p "$d/$t/obj"; cp "$bin" "$d/$t/AROSTCP"; cp "$b/bin/$arch/$gen"/*.o "$d/$t/obj/" 2>/dev/null
      # the modular stack (2026-11-12 on): its protocol and feature modules
      libs=$(dirname "$(dirname "$bin")")/Libs
      if [ -d "$libs" ]; then mkdir -p "$d/$t/Libs"; cp "$libs"/* "$d/$t/Libs/"; fi
      echo "$c $t: ok"
    else
      echo "$c $t: FAILED (see $d/build-$t.log)"
    fi
  done
done
rm -rf "$src/workbench/network"
git -C "$src" checkout -q HEAD -- workbench/network
