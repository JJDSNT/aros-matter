#!/bin/sh
# precodacy.sh BASE TIP - before pushing an AROS PR, what Codacy would add:
#  1. cppcheck findings TIP adds in each C file it changes (base and tip
#     lists compared with diff, duplicates counted; line numbers ignored);
#  2. calls flawfinder flags (strcpy, strncpy, strlen, strcat, sprintf, ...)
#     in the lines TIP adds, tests included.
# Run in the AROS tree (default ~/AROS-ipv6). Prints nothing when clean.
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
rm -rf "$T"
git diff "$1" "$2" -- '*.c' '*.h' | grep -nE '^\+.*\b(strcpy|strncpy|strlen|strcat|strncat|sprintf|vsprintf|gets|scanf)[[:space:]]*\(' \
  | sed 's/^/== flawfinder /'
exit 0
