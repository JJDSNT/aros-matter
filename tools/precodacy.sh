#!/bin/sh
# precodacy.sh BASE TIP - before pushing an AROS PR, what Codacy would add:
#  1. cppcheck findings TIP adds in each C file it changes (base and tip
#     lists compared with diff, duplicates counted; line numbers ignored);
#  2. flawfinder hits TIP adds in each C/H file it changes (same diff);
#     without flawfinder, a grep of the calls it flags in the added lines.
# Run in the AROS tree (default ~/AROS-ipv6). Prints nothing when clean.
# Calibration (2026-11-09): Codacy failed #2179 on flawfinder strncpy and
# strlen and on cppcheck variableScope, and passed #2178 and #2179 with new
# level-2 char (static arrays), memcpy and bcopy hits: those are counted
# apart as "info", not shown as what would fail the gate.
cd "${AROS_SRC:-$HOME/AROS-ipv6}" || exit 1
T=$(mktemp -d)
for f in $(git diff --name-only "$1" "$2" -- '*.c'); do
  for v in base tip; do
    rev=$1; [ $v = tip ] && rev=$2
    mkdir -p "$T/$v/$(dirname "$f")"
    git show "$rev:$f" > "$T/$v/$f" 2>/dev/null || : > "$T/$v/$f"
    cppcheck -q --enable=style,warning,performance,portability --std=c99 \
      --template='{id}|{message}' "$T/$v/$f" 2>&1 | sed "s#$T/$v/##" | sort > "$T/$v.list"
  done
  n=$(diff "$T/base.list" "$T/tip.list" | sed -n 's/^> //p')
  [ -n "$n" ] && { echo "== cppcheck $f"; echo "$n"; }
done
if command -v flawfinder >/dev/null; then
  for f in $(git diff --name-only "$1" "$2" -- '*.c' '*.h'); do
    for v in base tip; do
      rev=$1; [ $v = tip ] && rev=$2
      mkdir -p "$T/$v/$(dirname "$f")"
      git show "$rev:$f" > "$T/$v/$f" 2>/dev/null || : > "$T/$v/$f"
      flawfinder --quiet --dataonly --singleline "$T/$v/$f" 2>/dev/null \
        | sed -E 's/^[^:]*:[0-9]+:([0-9]+:)? *//' | sort > "$T/$v.ff"
    done
    n=$(diff "$T/base.ff" "$T/tip.ff" | sed -n 's/^> //p')
    # what Codacy fails on, and level-2 char/memcpy/bcopy, which it passed
    gate=$(printf '%s\n' "$n" | grep -vE '^\[2\] \(buffer\) (char|memcpy|bcopy):' | grep .)
    info=$(printf '%s\n' "$n" | grep -cE '^\[2\] \(buffer\) (char|memcpy|bcopy):')
    [ -n "$gate" ] && { echo "== flawfinder $f"; echo "$gate"; }
    [ "$info" -gt 0 ] && echo "-- info $f: $info level-2 char/memcpy/bcopy hits (Codacy passes these)"
  done
  rm -rf "$T"
  exit 0
fi
rm -rf "$T"
git diff "$1" "$2" -- '*.c' '*.h' | grep -nE '^\+.*\b(strcpy|strncpy|strlen|strcat|strncat|sprintf|vsprintf|gets|scanf)[[:space:]]*\(' \
  | sed 's/^/== flawfinder /'
exit 0
