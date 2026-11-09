Group 7, congestion: how slow start grows and ends, and where CUBIC starts after it. Three commits and a test; each change with its test; bsdsocket.library 5.39, kernel v0.78.

## 1. Slow start counts the bytes acknowledged

Slow start added one SMSS per ACK whatever it acknowledged. It now adds the bytes acknowledged, at most L·SMSS (Appropriate Byte Counting, RFC 3465), L from the new `net.inet.tcp.abc_l`. The default, 1, is RFC 5681's min(N, SMSS): as before, except that an ACK of a few bytes no longer counts as a segment. L = 2 (FreeBSD's default) was measured and not taken: behind a 20 Mbit bottleneck with a 100 KB queue it dropped 216-218 segments at the end of slow start against 148-162 with L = 1, for the same throughput.

## 2. HyStart++ in the first slow start

RFC 9406, in `tcp_ss.c`, on by default (`net.inet.tcp.hystart`): the minimum RTT of each round, from the samples `tcp_ack_rtt()` now hands over; a rise of max(4 ms, min(RTT/8, 16 ms)) moves to Conservative Slow Start for 5 rounds, then congestion avoidance with ssthresh = cwnd; an RTT back below the CSS baseline resumes slow start. Only while ssthresh has its initial value. Not paced, so L = 8 (the RFC's value for that case).

A/B in one binary, two runs each, 20 Mbit token bucket, ACKs delayed 20 ms. "L = 8, no detection" has the same growth without the exit, so it isolates the detection:

| queue | L = 1 | L = 8, no detection | HyStart++ |
|---|---|---|---|
| none | no exit | no exit | no exit (no early exit) |
| 100 KB, drops | 165 / 164 | 190 / 169 | 82 / 78 |
| 256 KB, drops | 163 / 144 | 167 / 166 | 62 / 64 |
| 1 MB | slow start never ends | never ends | ends without a loss |

Throughput the same or slightly higher (100 KB queue: 23.4 MB in 10 s against 22.9). Without pacing the detector sees bursts: with a queue shallower than the BDP it cannot exit before the overflow, as the RFC notes.

## 3. CUBIC starts from cwnd after a slow start with no loss

At the start of an epoch with cwnd at or above W_max, CUBIC set K = 0 but kept W_max: 0 when no loss had happened. After a slow start that ends without a loss, W(t) stayed below cwnd and only the Reno-friendly window grew it. Now W_max = cwnd there (RFC 9438 section 4.10, as Linux's `bictcp_update()`). In the 5 s after congestion avoidance begins (1 MB queue):

| slow start ended | before | after |
|---|---|---|
| at the route's ssthresh (400 segments), HyStart++ off | +7 / +7 segments | +33 / +32 |
| by HyStart++ | +16 / +7 | +40 / +40 |

## 4. Test: a route's ssthresh reaches a new connection

`cunit-net-tcpinfo` sets `RTV_SSTHRESH` on the loopback host route (IPv4, IPv6) and reads it back from a new connection's TCP_INFO: a regression test for the route metrics the bench above relies on. (On the tap, the neighbour's host route inherits the link route's metric, and the connection takes it; link-local routes are keyed with zone 0.)

## Validation

linux-x86_64 hosted. `cunit-net-tcpinfo` (now takes IFNAME, for #2155's SYN backoff test): byte counting (12 segments over the loopback, in two ACKs: 2 segments of growth with L = 1, 4 with L = 2), no HyStart++ exit without an RTT rise, the route metric; `cunit-net-sysctl`: `abc_l`, `hystart`. All 51 socket suites pass in both runs; loss and RTO benches as before (no needless retransmission). Each commit builds on its own without warnings; cppcheck: no new findings. Benches in aros-matter: `tests/tcp/ss_probe.py`, `rtssthresh.c`, `cwnd_probe.py`.
