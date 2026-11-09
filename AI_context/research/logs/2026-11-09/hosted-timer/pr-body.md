The unix-hosted timer.device advanced the system time, the uptime and the EClock by a fixed period for each SIGALRM of its interval timer. A signal that is already pending is not queued again, so the ticks that came while AROS was not running (the host did not schedule it, or interrupts were disabled) counted as one, and the clocks fell behind the host's for good.

Each tick now reads the host's `CLOCK_MONOTONIC` (`clock_gettime()`, looked up in libc as `setitimer()` already is) and advances the clocks by the time that actually went by; the EClock (`tb_ticks_total`) is derived from the same count, so `ReadEClock()` stays consistent with it. The handler calls the host the same way the unixio hidd's SIGIO handler calls `poll()`. Without `clock_gettime()` a tick still counts as its period.

## Validation

Linux host (WSL2). AROS sends its `GetUpTime()` over UDP every 250 ms and the host stamps each arrival with its own monotonic clock; the difference should not move (`clock_probe.py` in aros-matter):

| | before | after |
|---|---|---|
| idle, 60 s | AROS 15.5 ms behind | 0.1 ms |
| 8 host CPUs busy, 60 s | 24.9 ms behind | 0.6 ms |
| 8 host CPUs busy, 180 s | 25.0 ms behind | 0.1 ms |

About 1-1.5 s an hour before. All 51 network socket suites (many of them timed: keepalive, user timeout, sblock, clock steps) pass in both runs with it.

One thing found on the way, not changed here: on WSL2 the host's wall clock (`CLOCK_REALTIME`) is resynchronised with Windows in steps of +1.1-1.3 s every ~32 s, so packet captures (tcpdump stamps with it) show intervals that cross one ~1.2 s too long; the monotonic clock this uses is not affected.
