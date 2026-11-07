# RTO granularity (group 7, item 1) - 2026-11-07

AROSTCP 5.37 (`review/arostcp-nd6-monotonic`), hosted linux-x86_64, tap. Bench:
`tests/tcp/rto_probe.py` (tcpbench `rto`): per connection 20 exchanges of 100 bytes
each way, 0.5 s idle, a 77-byte tail whose first copy the host drops; RTO = time
between the two copies. netem delay on the host's side; 8 connections per delay.
Self-checks: every tail dropped exactly once, RTT seen = delay set (within 20 ms).

| RTT | RTO min / median / max (s) | TSval step (ticks of 500 ms) | RFC 6298, fine clock | Linux |
|---|---|---|---|---|
| 0.4 ms | 1.08 / 1.28 / 1.28 | 3 | 1.00 | ~0.20 |
| 50 ms | 1.16 / 1.16 / 2.46 | 3 (one 5) | 1.00 | ~0.25 |
| 200 ms | 1.06 / 2.36 / 2.36 | 5 (one 3) | 1.00 | ~0.40 |
| 500 ms | 1.74 / 1.76 / 1.78 | 4 | 1.00 | ~0.70 |

Why (code, 4.4BSD as is): RTT samples are counted in slow ticks (`PR_SLOWHZ` 2,
`t_rtt` from 1, or `tcp_now - tsecr + 1`), so any RTT below 500 ms is 1 or 2
ticks depending on where it falls against the tick; `tcp_xmit_timer()` settles
at `srtt>>3` = 0 and `rttvar` = 3, RTO 3 ticks (1.5 s nominal); an RTT that
straddles the tick (200 ms here) gives samples of 1 and 2, rttvar grows, 5 ticks
(2.5 s). The timer itself only fires on a slow tick, so the RTO lands up to
500 ms before its nominal value (1.08-1.28 for 1.5). Matches a simulation of the
same arithmetic (median 1.24 / 1.31 / 1.86 / 1.75 s).

Conclusion: RTO is 1.1-2.5 s where RFC 6298 asks 1.0 s (its SHOULD minimum) and
Linux uses RTT + 200 ms; at a 200 ms RTT it is 2.4 times the RFC's. Every tail
loss, lost retransmission or loss with too few duplicate ACKs pays it. It is
also what RACK-TLP cannot work with (it needs per-segment send times and a
probe timer around 2 x SRTT). Next: a design note for millisecond RTT samples
and a finer retransmission timer, before any code.

Read in the code, not measured yet: Karn's rule holds on the t_rtt path (`tcp_subr.c` and the timer
clear `t_rtt` on retransmission); the timestamp path, the backoff table and the
64 s cap are part of the design note.
