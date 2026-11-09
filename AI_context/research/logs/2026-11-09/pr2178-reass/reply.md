Thanks - I hit the same stall here once the receive buffers grew past ~100 segments, and had the same fix queued for a later series. It is now the second commit of this PR:

- `tcp_reass()` always takes the segment at `rcv_nxt`, as FreeBSD does; the cap on the queue becomes a receive buffer's worth of full-sized segments (at least 100), so a window the peer may legitimately send is not refused either.
- Test in `cunit-net-tcpinfo`: on a loopback connection opened without RFC 7323 options, 110 hand-made 100-byte segments go out of order through a raw socket and fill the queue; then the client sends the 11100 bytes itself, the missing segment first (all within its initial window, so nothing is acknowledged before the client sent it). The receiver reads all 11100 bytes; on master it reads none, ever.
- bsdsocket.library 5.40, on top of #2167. The 51 cunit-net suites pass.
