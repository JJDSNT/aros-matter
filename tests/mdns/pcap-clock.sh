#!/bin/sh
# pcap-clock.sh PCAP... - whether the host's clock went only forward while
# each capture was taken. The tests that time mdnsd read the gaps between
# packets from these timestamps; under WSL the host's clock is now and then
# set back (2.2 s, 2026-11-19: timing.sh "failed" twice - probes 2197 ms
# "before" the one before, announcements "before" the probes they followed,
# though tcpdump had them in the right order). Prints, for a capture whose
# timestamps go back, "INVALID: <pcap>: the host's clock went back N ms
# (packet K); its timings cannot be trusted - run again", and exits 1.
bad=0
for p in "$@"; do
  [ -f "$p" ] || continue
  tcpdump -tt -n -r "$p" 2>/dev/null | awk -v f="$p" '
    { t = $1 + 0; if (NR > 1 && t < prev) { printf "INVALID: %s: the host'"'"'s clock went back %d ms (packet %d); its timings cannot be trusted - run again\n", f, (prev - t) * 1000, NR; bad = 1; exit }
      prev = t }
    END { exit bad }' || bad=1
done
exit $bad
