# PMTUD audit (Backlog 2, B2-B) — 2026-10-31

The first B2 activation, research only. Upstream master `aa24b08479` (AROSTCP 5.19, with #1995 MSS and Kal's ICMPv6 error delivery). Files read: `netinet/ip_output.c`, `ip_icmp.c`, `tcp_output.c`, `tcp_subr.c`, `tcp_input.c` (`tcp_mss`, `tcp_mssopt6`), `netinet6/icmp6.c` (`icmp6_update_pmtu`, `icmp6_notify_error`), `ip6_output.c`, `nd6.c`, `net/sana2arp.c`.

Wire tests use `tests/tcp/pmtud_probe.py`. The host (Linux, tap `aros0`) captures an AROS packet and answers it with an ICMPv6 Packet Too Big that quotes it, using only Python raw sockets (no scapy). Logs are in `logs/2026-10-31/pmtud-audit/`.

## Results

| # | Area | State | Evidence |
|---|---|---|---|
| P1 | IPv4 PMTUD (RFC 1191) | **absent** | TCP never sets DF (no `ip_off` in `tcp_output`/`tcp_subr`), so routers fragment. ICMP "fragmentation needed" maps to a protocol-unreachable code, and no MTU is stored. The 4.4BSD-Lite state: safe, not current practice |
| P2 | IPv6 Packet Too Big → route MTU | ✔ | `icmp6_update_pmtu()`: lower only, clamped to 1280 (RFC 8201 §4, RFC 8200 §5). `ip6_output()` caps each packet at the route's MTU |
| P3 | IPv6: TCP after a Packet Too Big | **partial** | A new connection uses it: SYN MSS 1220 after a PTB with MTU 1280 (via #1995). A **running** connection is not told (Kal's aa24b08479 leaves PTB out of socket notification on purpose), so it keeps MSS 1440 and `ip6_output` fragments every segment: **2450 fragments** for 2 MB after one PTB. RFC 8201 §5.2 wants the transport to send smaller packets; fragments are fragile on real paths (RFC 8900) |
| P4 | Scope of the PMTU | **on-link ok, off-link wrong** | On-link: per neighbour. A PTB about `fe80::e090…` left a connection to the host's other address `fe80::1` at MSS 1440, because ND clones a host route per neighbour. Off-link: `rtalloc1(dst, 0)` with no cloning finds the **default route**, so a PTB about `2001:db8:4d54::1` (MTU 1400) made a 1452-byte datagram to `2001:db8:4d54::2` leave fragmented at 1400. **One PTB lowers the MTU for every off-link destination.** KAME/FreeBSD clone a host route (`icmp6_mtudisc_clone`, `RTF_DYNAMIC`). For TCP the effect is small: off-link with no known PMTU, #1995 already uses MSS 1220 |
| P5 | PMTU aging | **absent** | The MTU is never raised again. RFC 8201 §4: try again no sooner than 5 min, 10 recommended. With P4, the default route stays lowered until the route changes |
| P6 | Checking a PTB | **absent** | Nothing checks the quoted packet against a connection (RFC 5927 §7.2: TCP sequence in window). With the 1280 floor, an off-path PTB can at worst push everything (P4) down to 1280 |
| P7 | ND hold queue (found by this test) | **one packet** | `nd6_resolve`: `ln_hold` keeps the latest packet only. A fragmented datagram sent while the neighbour is being resolved loses every fragment but the last; seen: only the 2nd fragment of the 3rd datagram went out after the NA. RFC 4861 §7.2.2 allows that ("at least one, MAY more"); FreeBSD queues 16, Linux about 100. ARP (`sana2arp.c` `at_hold`) also keeps one, which RFC 1122 allows |
| P8 | Black-hole detection / PLPMTUD (RFC 4821, 8899) | absent | B2-B, after P3–P5 |

## Proposed small deliveries

1. ✔ **In review as AROS #2002.** **P4 + P5:** a PTB updates a cloned host route for its destination (`RTF_DYNAMIC`, as KAME), not the default or prefix route; that route expires after 10 minutes, giving the MTU back. Test: CUnit with a raw socket sending a PTB about one destination, then checking `IPV6_PATHMTU` (RFC 3542 §11.2), or the fragmenting of a datagram, for another one.
2. **P3:** `tcp6_ctlinput()` takes `PRC_MSGSIZE`. `icmp6_notify_error()` calls it for a PTB, a check against the connection's sequence window (P6) included, and `tcp_mtudisc()` lowers `t_maxseg` and retransmits, as FreeBSD's `tcp_mtudisc`. That changes Kal's "no socket is told" note: it needs his view in the PR.
3. ✔ **In review as AROS #2003.** **P7:** a small ND hold queue per neighbour (e.g. 16 packets, oldest dropped first).
4. **P1:** IPv4 PMTUD with DF on TCP is a policy change for the whole IPv4 stack; ask Kal before doing it.

Matter runs over IPv6 and keeps its messages under 1280, so none of these blocks it. P3 and P4 matter to any IPv6 TCP over a path with a smaller MTU (tunnels, VPNs); P7 to the first burst towards a new neighbour.
