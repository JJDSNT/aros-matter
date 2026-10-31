# Backlog 2 — reconciliation with the current backlog and upstream (2026-10-31)

The first step [backlog2.md](../backlog2.md) asks for before any activation. Upstream AROS master `7a6f655644` (AROSTCP 5.15). Open AROSTCP PR: #1995 (G19b, 5.16). Files read: `netinet/tcp_subr.c`, `tcp_input.c`, `tcp_usrreq.c`, `tcp_timer.c`, `workbench/network/common/include/netinet/tcp.h`.

States:
- **done**: merged upstream.
- **current**: already on the current backlog (`current_state.md`), so not duplicated in B2.
- **pending**: nobody is working on it.
- **research**: needs a reproducible measurement before code.

| Item | B2 front | State | Evidence / note |
| --- | --- | --- | --- |
| G19b — MSS IPv6 | B2-B | done (#1995) | fixes the MSS only; PMTUD audit not done |
| R1/G19g — RFC 6056 ports | B2-A | in review (#1998) | sequential ports from 1024 measured on the wire (tcp-wire 2026-10-30); done here satisfies B2-A R1 |
| G19e — T/TCP `ccnew` in the SYN | B2-A (compatibility) | done (#1996) | `tcp_do_rfc1644 = 1` (`tcp_subr.c:314`); RFC 6247 moved T/TCP to Historic |
| G19h — close with unread data sends FIN | B2-A | done (#1997) | = stackprobe S4; RFC 1122 §4.2.2.13 / RFC 2525 §2.17 |
| G19i — RTO 1.4 s then 9 s gap | B2-C | explained, no defect (backoff 1.5/3/6 s; the gap was ND dropping a held packet in the bench) | measure timer granularity before touching anything (RFC 6298) |
| G19f — no ECN in the SYN | B2-C | explained | `tcp_do_ecn = 0` (`tcp_subr.c:317`): off by default, not a defect. Enabling it globally needs maintainer approval (B2 §6) |
| R2 — RFC 5961 | B2-A | pending, research | RST in `tcp_input.c:1411` acts on any in-window RST: no exact-sequence check, no challenge ACK. Needs a blind-RST/SYN test first |
| R3 — keepalive options | B2-A | pending | `TCP_KEEPIDLE/INTVL/CNT/KEEPINIT` are **defined** in `netinet/tcp.h:235-238` but `tcp_ctloutput()` (`tcp_usrreq.c:584-644`) handles only NODELAY/MAXSEG/NOOPT/NOPUSH. B2 calls them "existing"; they are header-only. `TCP_USER_TIMEOUT` absent. Public API: check the Roadshow contract first |
| S3 `MSG_DONTWAIT`, S5 `getnetbyaddr`, S6/S7 Roadshow calls | B2-A | research | ABI/contract questions; stackprobe is a probe, not an oracle |
| PMTUD (ICMP frag-needed / ICMPv6 Packet Too Big) | B2-B | research | after #1995: next audit candidate, since it decides the MSS once a path MTU is known |
| SACK / PRR | B2-B | research | `tcp_do_sack = 1`, `tcp_do_prr = 0`; check behaviour under loss before any default change |
| CUBIC / NewReno, HyStart++ | B2-C | research | both exist; HyStart++ only after G19i is understood |
| RACK-TLP, F-RTO, TFO, fuzzing | B2-D | deferred | depend on timers and SACK scoreboard |

## Decision

B2 is not activated as a separate front yet. The next small deliveries come from the current backlog and cover B2-A and B2-C items at the same time:

1. **G19e:** T/TCP off by default. Acceptance: the SYN carries no `cc`/`ccnew` option; a CUnit test checks the option through TCP_NOOPT/getsockopt, or on the wire if the API cannot see it; all suites pass.
2. **G19h:** RST on close with unread data. Acceptance: the peer sees RST, not FIN; a CUnit loopback test checks that the peer gets ECONNRESET.
3. **R1:** RFC 6056 ephemeral ports. Acceptance: consecutive connections do not use consecutive ports; IPv4 and IPv6.

After these, the first B2 activation candidate is the **PMTUD audit (B2-B)**, research only (no code): the IPv4/IPv6 Packet Too Big paths, the route MTU cache, and what `tcp_mss()` does with them after #1995. Matter work (ISSUE-0003 crypto) can be interleaved at any point; nothing here blocks it.
