# CUBIC curve and the initial window (group 7) - 2026-11-07

Bench: `tests/tcp/cwnd_probe.py` (tcpbench `cwnd`): AROS sends for 40 s over IPv6
link-local with a 400 KB send buffer and prints TCP_INFO's snd_cwnd every 50 ms; the
host delays ACKs 100 ms and drops one in 3000 of AROS's segments (gact determ).

## Finding: no slow start to a local destination

`tcp_mss()` set the initial window only `if(!local)` (4.4BSD: no slow start on a local
network). To any destination on the same subnet snd_cwnd stayed at its maximum,
`TCP_MAXWIN << TCP_MAX_WINSHIFT` (1 GB): `cunit-net-tcpinfo` over the loopback reads
1073725440 right after connect(); on the tap the first sample is 751908 segments, and
after each loss cwnd only fell to 70% of that (cwnd-r2-no-iw.csv). RFC 5681 section 3.1
has every connection slow-start; FreeBSD and Linux use the initial window for all.
Fixed: IW10 (RFC 6928) for every destination; cunit-net-tcpinfo reads 14480/14600.

## CUBIC on the 500 ms clock: no measurable gain from milliseconds

With the initial window fixed, the epochs follow RFC 9438's W(t) = C(t-K)^3 + W_max
within 1-2 segments (W_max 83.5, K 3.97 s):

    0.30s cw=63 W=64 | 0.78s 70/71 | 1.26s 74/76 | 1.80s 79/79 | 2.52s 81/82 | 3.54s 83/83

cwnd moves toward the target a little on every ACK ((target - cwnd)/cwnd), which smooths
the 500 ms steps of t. Not changed: no A/B gain to show. Two limits seen on the way: the
send buffer defaults to 128 KB and SO_SNDBUF can be raised to ~455 KB (sb_max 512 KB);
a buffer of 128 KB holds the window at ~90 segments (a 100 ms path: 1.3 MB/s).
