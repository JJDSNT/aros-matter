Group 7, timers: round-trip times and the retransmission timeout in milliseconds, TCP_INFO, and slow start to local destinations. Three commits, each with its test; bsdsocket.library 5.38, kernel v0.77.

## 1. TCP_INFO

`<netinet/tcp.h>` declared it and FreeBSD's `struct tcp_info`, but `tcp_ctloutput()` refused it. It is filled as FreeBSD's `tcp_fill_info()` does: state, negotiated options, segment size, windows and sequence numbers, `snd_cwnd`/`snd_ssthresh`, and the RTT estimate, variance and RTO in microseconds. The structure is larger than an mbuf, so the answer goes in a cluster. It is what the next two commits are tested with.

## 2. RTT and RTO in milliseconds

The RTT was counted in 500 ms ticks (4.4BSD), so any RTT below 500 ms was 1 or 2 ticks, the RTO settled at 3 to 5 ticks and fired on the slow tick. Now, as RFC 6298 and FreeBSD:

- `tcp_ms()` (milliseconds of `GetUpTime()`) is the timestamp clock, 1 ms a tick, and times the RTT samples: from the echoed timestamp, or from the timed segment's send time (Karn), the SYN's included.
- SRTT and RTTVAR in ms, scaled by 32 and 16. RTO = SRTT + max(G, 4·RTTVAR), between `net.inet.tcp.rexmit_min` and 64 s, doubled on each timeout.
- **`net.inet.tcp.rexmit_min`**, new: 200 ms by default, as FreeBSD and Linux. RFC 6298 section 2.4 says the RTO SHOULD be rounded up to 1 s; this is a deliberate departure, and the sysctl puts it back.
- The initial RTO is separate from the floor: `net.inet.tcp.rttdflt`, now 1 s (section 2.1; it was 6 s), seeded in RTTVAR as 4.4BSD and FreeBSD do so that the backoff runs from it (1, 2, 4, 8 s, section 5.5), and 3 s when a connection is established with no sample after its SYN or SYN-ACK was retransmitted (section 5.7). The SYN cache resends a SYN-ACK after 1, 2, 4 and 8 s (it was 3, 6, 12).
- The retransmission timer is a deadline checked on every fast tick, so it fires within a tick after the RTO and never before. The fast tick is about 60 ms, not 50 (`UNIT_VBLANK`), so a countdown would have been 20% late.

The persist timer, the TIME_WAIT truncation and the route metrics convert from ms. Everything else (keepalive, 2MSL, SYN cache, PAWS) stays on the slow tick.

## 3. The initial window for every destination

`tcp_mss()` set the initial window only `if(!local)`, which 4.4BSD used to skip slow start on a local network. To any destination on the same subnet `snd_cwnd` stayed at its maximum, 1 GB: the first flight was whatever the send buffer held, and after a loss cwnd fell only to 70% of 1 GB. RFC 5681 section 3.1 has every connection slow-start, and FreeBSD and Linux use the initial window whatever the destination. IW10 (RFC 6928) is now set for all.

## Validation

linux-x86_64 hosted, tap.

| | 5.37 | 5.38 |
|---|---|---|
| RTO after a lost tail, RTT 0.4 ms | 1.28 s | 0.20-0.24 s |
| ... RTT 50 ms | 1.16 s | 0.20 s |
| ... RTT 200 ms | 2.36 s | 0.26 s |
| ... RTT 500 ms | 1.76 s | 0.56 s |
| ... RTT 200 ms ± 100 ms jitter | 2.13 s | 0.59 s, no spurious retransmission |
| a lost SYN (initial RTO) | 5.8 s | 1.0 s |
| four lost SYNs: intervals | 6 s, 24 s, ... | 1.0, 2.04, 4.02, 8.04 s |
| cwnd right after connect(), loopback | 1073725440 | 14480 (10 × MSS) |

On the wire, by benches in aros-matter: `rto_probe` (20 exchanges, then a tail dropped once; 8 connections per case), `cwnd_probe` (TCP_INFO every 50 ms). With the initial window, CUBIC's epochs follow RFC 9438's W(t) within 1-2 segments. On the loss bench (1 MB, ACKs delayed 20 ms), a lost retransmission recovers in 0.55 s instead of 1.68 s, with no needless retransmission in any case. A transfer with random loss is slower to start now that it slow-starts (0.33 s → 1.31 s): that is RFC 5681's behaviour and what HyStart++ will tune next.

- `cunit-net-tcpinfo` (new, 9 tests): on 5.37 TCP_INFO is refused; over the loopback the RTO is the 200 ms floor, the RTT ~1 ms, and the initial window IW10, IPv4 and IPv6; a SYN to a link-local neighbour that does not exist has an RTO of 2 s after one timeout and 4 s after two. `cunit-net-sysctl`: `rexmit_min` and `rttdflt`.
- **All suites:** all 51 `cunit-net-*` socket suites pass, in both the basic and the automated runs.
- **cppcheck** `--enable=warning,style`: no new findings in the changed files. Each commit builds on its own without warnings.
