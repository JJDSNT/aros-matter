The first half of group 6: TCP hardening. Five commits, one per change, each with its test or bench; the revision bump is in the last one: 5.29, kernel v0.68. The first commit is the `sblock()` point Kal raised on #2023.

## Scope

1. **A call that may not block does not wait for a held socket buffer** (Kal on #2023). On a socket shared between tasks, a receive with `MSG_WAITALL` that takes its data in sections sleeps holding the receive buffer. `sosend()` and `soreceive()` took the buffer with `sblock()`, which always waits: a `recv()` with `MSG_DONTWAIT`, or on a non-blocking socket, slept until the other call was done. It now gets `EWOULDBLOCK` at once, as FreeBSD's `SBLOCKWAIT(flags)`; a blocking call still waits.
2. **A reset before the receive window does not end the connection** (RFC 9293 §3.10.7.4). `tcp_input()` trimmed a segment to the window before it looked at RST, as 4.4BSD did, so a reset numbered anywhere before RCV.NXT was moved into the window and closed the connection. A reset's sequence number is now checked first, as in FreeBSD.
3. **Challenge ACKs (RFC 5961)**, as FreeBSD and Linux do:
   - only a reset at exactly RCV.NXT closes the connection; another in the window gets a challenge ACK (§3);
   - a SYN on a synchronized connection gets a challenge ACK instead of a reset (§4); in SYN_RECEIVED it still resets;
   - a segment whose ACK is older than SND.UNA by more than the peer's largest window is dropped with a challenge ACK (§5.2);
   - at most 5 challenge ACKs a second, counted per connection (§7).
4. **A timestamp offset per connection** (RFC 7323 §5.4). Every TSval was `tcp_now`, the clock since the stack started, the same for all connections. Each connection now adds an offset of its own, a keyed hash of its addresses and ports with a key that is not the ISN's. The SYN cache keeps it for the connection it makes, and the RTT taken from a timestamp echo removes it again.
5. **SipHash for the ISNs, SYN cookies and timestamp offsets.** They came from a fast mixing function that is not a keyed cryptographic one, as RFC 6528 asks for, and IPv6 addresses were folded to 32 bits first. `tcp_conn_hash()` replaces it: SipHash-2-4, as Linux uses for the same values, over both whole addresses, both ports, the cookie's counter and a byte for the use. The keys still come from `kern_random()`.

**Reviewed, nothing to change:**
- `SOL_SOCKET` flags set outside `splnet`: the API calls are serialized by `syscall_semaphore`, and the stack task only reads `so_options`.
- SYN cookies (RFC 4987), apart from the hash: the counter, its validity window (about 6 s; a comment said 3) and the MSS encoding are sound. A connection made from a cookie has no window scaling, SACK or timestamps, as the cookie does not carry them; FreeBSD stores them in the timestamp, which could come later.

## Validation

linux-x86_64 hosted, tap.device with a Linux neighbour:

- **New CUnit test:** `cunit-net-sblock`. It fails 2/3 on 5.28 (master) and passes 3/3 on this branch, in both the basic and the automated runs. The receive in the other task asks for more than the receive buffer holds; one that fits waits without holding the buffer.
- **On the wire** (aros-matter benches; a CUnit test cannot inject segments into a connection):
  - `tests/tcp/rst_probe.py` injects one segment into an AROS connection from the host, then checks whether the connection survives and what AROS answers:

    | Case | 5.28 | this branch |
    |---|---|---|
    | RST at RCV.NXT | reset | reset |
    | RST before the window | reset | ignored |
    | RST in the window, not exact | reset | challenge ACK |
    | SYN in the window | reset | challenge ACK |
    | data with an old ACK | data taken | dropped, challenge ACK |
    | RST far after the window | ignored | ignored |
    | 10 RSTs in the window | - | 5 challenge ACKs |

    The first and the sixth rows check the bench; commit 2 alone passes the second row only.
  - `tests/tcp/tsval_probe.py`:
    - the TSvals of 10 SYNs no longer start at the ticks since boot, 9 to 13 on 5.28, and are independent of each other;
    - on an accepted connection the SYN-ACK and the data carry the same clock;
    - the retransmission timeouts are unchanged, 3, 6 and 12 ticks.
  - SYN cookies, with a local build that answers every SYN with a cookie: all suites pass, IPv4 and IPv6, and a 200 kB transfer from the host completes; the SYN-ACK carries only the MSS.
- **SipHash** gives the reference test vectors (lengths 0, 8, 15 and 63).
- **All suites:** all 49 `cunit-net-*` socket suites pass, in both runs, with two tap.device units.
- **Regression:** `tests/tcp/run_tcp.py` (SYN options, loss recovery with SACK, reset on close with unread data, RTO) behaves as on master.
- **cppcheck** `--enable=warning,style`: no new findings in the changed files (5 fewer).
- **Bisect:** each commit builds on its own, stack and tests, without warnings.
