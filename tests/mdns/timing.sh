#!/bin/sh
# timing.sh OUTDIR - mdnsd's timing as a look-up sees it (B69, B70), from a
# capture: the host's Avahi publishes t1..t3.local (cold: nobody asked for
# them before) and AROS looks up, three times at different moments of an
# idle mdnsd, an existing name (tN.local) and a missing one (nobodyN.local)
# with resolvtest -T, which prints the system time each look-up started and
# first sends a datagram to the host's port 9, whose time in the capture
# gives the offset between AROS's clock and the capture's; then:
#   - first query: from a look-up's start to mdnsd's first query for the
#     name (RFC 6762 section 5.2: 20-120 ms);
#   - an existing name: the look-up's time (its first query, the answer, and
#     the quarter of a second after the first address);
#   - a missing name: the look-up's time (the resolver's 3 s);
#   - probes of the host's name at start 250 ms apart, its announcements
#     at least 1 s apart (sections 8.1, 8.3).
# RESOLVTEST: the test binary (built for the target). MODE=amiga runs AROS
# m68k (tools/amiga-run.sh); FIRST_MAX: the most the first query may take,
# ms (default 120 + 30 for the wait's overshoot and a turn of mdnsd).
set -u
out=$1; mkdir -p "$out"
root=$(cd "$(dirname "$0")/../.." && pwd)
"$root/tools/tap-up.sh" >/dev/null
mode=${MODE:-hosted}
pre=""
[ "$mode" = amiga ] && pre="Delete >NIL: SYS:System/Network/AROSTCP/db/services.d/timesync QUIET"
cat > "$out/s.script" <<EOS
$pre
Execute SYS:System/Network/AROSTCP/S/startnet
Wait 15
C:resolvtest -T 192.168.166.1 t1.local nobody1.local >SYS:out/t1.txt
Wait 4
C:resolvtest -T 192.168.166.1 t2.local nobody2.local >SYS:out/t2.txt
Wait 7
C:resolvtest -T 192.168.166.1 t3.local nobody3.local >SYS:out/t3.txt
EOS
pids=""
for n in 1 2 3; do
  avahi-publish -a -R t$n.local 192.168.166.7$n >/dev/null 2>&1 & pids="$pids $!"
done
sudo -n tcpdump -i aros0 -n -w "$out/aros0.pcap" 'udp port 9 or udp port 5353' >/dev/null 2>&1 & cap=$!
sleep 1
if [ "$mode" = amiga ]; then
  AMIGA_TAP_IP=192.168.166.2 AMIGA_RUN_TIMEOUT=300 \
    "$root/tools/amiga-run.sh" "$out/aros" "$out/s.script" "$RESOLVTEST" > "$out/run.txt" 2>&1
else
  AROS_TAP_IP=192.168.166.2 AROS_RUN_TIMEOUT=150 \
    "$root/tools/hosted-run.sh" "$out/aros" "$out/s.script" "$RESOLVTEST" > "$out/run.txt" 2>&1
fi
sleep 1
sudo -n kill $cap 2>/dev/null
kill $pids 2>/dev/null
sleep 1
tcpdump -tt -n -r "$out/aros0.pcap" 2>/dev/null > "$out/pcap.txt"
cat "$out"/aros/out/t?.txt > "$out/t.txt" 2>/dev/null
python3 -I - "$out" "${FIRST_MAX:-150}" <<'EOF'
import re, sys
out, first_max = sys.argv[1], int(sys.argv[2])
lines = open(out + "/pcap.txt").read().splitlines()
def ts(l): return float(l.split()[0])
fails = 0
def expect(name, ok, detail=""):
    global fails
    print(("PASS " if ok else "FAIL ") + name + (": " + detail if detail else ""))
    if not ok: fails += 1
marks = [ts(l) for l in lines if "192.168.166.2." in l and "192.168.166.1.9: " in l]
runs = []
for l in open(out + "/t.txt"):
    p = l.split()
    if p and p[0] == "M":
        runs.append(("mark", float(p[1]), 0, ""))
    elif p and p[0] == "T":
        runs.append((p[1], float(p[2]), int(p[3]), p[4]))
offset = None
for name, t, ms, found in runs:
    if name == "mark":
        offset = marks.pop(0) - t if marks else None
        continue
    if offset is None:
        expect(name + ": the marker in the capture", False); continue
    start = t + offset
    q = [ts(l) for l in lines if ".5353: " in l and ("? %s." % name) in l and ts(l) >= start - 0.05
         and l.split()[2].startswith(("192.168.166.2.", "fe80"))]
    if name.startswith("t"):
        first = (q[0] - start) * 1000 if q else None
        expect("%s: first query %s ms after the look-up started" % (name, "none" if first is None else "%.0f" % first),
               first is not None and -5 <= first <= first_max)
        expect("%s: found in %d ms" % (name, ms), found == "found" and ms <= 250 + first_max + 50)
    else:
        expect("%s: not found after %d ms (3 s)" % (name, ms), found == "none" and 2950 <= ms <= 3150)
# the host name's probes and announcements at start, in each family (from
# AROS: the source of its first probe in that family)
for group in ("224.0.0.251.5353", "ff02::fb.5353"):
    pl = [l for l in lines if ("> %s:" % group) in l and "? arosbox.local." in l]
    if len(pl) < 3:
        continue
    src = pl[0].split()[2]
    probes = [ts(l) for l in pl if l.split()[2] == src][:3]
    gaps = [round((b - a) * 1000) for a, b in zip(probes, probes[1:])]
    expect("%s: probes of arosbox.local 250 ms apart (%s ms)" % (group, gaps),
           len(gaps) == 2 and all(240 <= g <= 300 for g in gaps))
    ann = [ts(l) for l in lines if l.split()[2] == src and ("> %s:" % group) in l
           and " 0*- " in l and ts(l) > probes[-1]][:2]
    expect("%s: announcements at least 1 s apart (%s ms)" % (group,
           round((ann[1] - ann[0]) * 1000) if len(ann) == 2 else "?"),
           len(ann) == 2 and ann[1] - ann[0] >= 0.99)
print("timing: %d failed" % fails)
EOF
