# Network roadmap across the three initiatives (2026-11-01)

The three initiatives that depend on AROS networking:
- **completing AROSTCP** (Backlog 2, PR groups 3–7);
- **Matter** (M0–M6, on hold);
- **the Open Screen prerequisites** for the Prism ([backlog3.md](../backlog3.md)).

This is where each network capability lives, decided on the networking merits, and how the PR groups serve all three. Backlog 3 assigns QUIC to "a shared library, consumed by the Prism"; this document checks that against the code and settles it.

Revisions read: AROS upstream `bf196e7dc1` (5.20) + #2006 (5.21, in review); AROS contrib `development/libs/openssl` (OpenSSL **4.0.1**, `no-threads no-ssl3 no-asm no-shared no-tests`, the AROS patch adapts `test/quicapitest.c`).

## 1. Layers and owners

| Layer | Provides | Owner | Consumers |
|---|---|---|---|
| L1 — AROSTCP (`bsdsocket.library`) | sockets, IPv4/IPv6, zones, multicast/MLD, PMTU and ICMP signalling, UDP options, timers inside the stack | upstream AROS, via our PR groups | everything |
| L2 — system services | DNS-SD/mDNS (Bonami/mdnsd), resolver (with RDNSS), monotonic time (posixc `clock_gettime`) | Bonami: the maintainer / aros-midihub; resolver: AROSTCP; time: CRT | Matter (M2), Open Screen (B3-B), MIDIHub |
| L3 — shared libraries | crypto, TLS 1.3, **QUIC** | AROS contrib (OpenSSL) / aros-matter's own mbedTLS build | Matter (crypto PAL), Prism (TLS 1.3 + QUIC) |
| L4 — applications | `matterctl`; the Open Screen agent | aros-matter; aros-prism | — |

## 2. Decisions

1. **QUIC is a shared library (L3), not part of the Prism and not part of AROSTCP.**
   - **Not in AROSTCP.** QUIC is a user-space protocol by design: its congestion control, loss recovery and PLPMTUD (RFC 9000/9002, RFC 8899) live with the connection, and every deployed implementation runs outside the kernel. The stack's job is the UDP contract in §3.
   - **Not private to the Prism.** AROS contrib already ships OpenSSL 4.0.1, which has had a QUIC client since 3.2 and a server since 3.5; the AROS patch adapts its QUIC API test, so it is built and exercised. One QUIC implementation for the system, shared by the Prism and any later user (HTTP/3 and others), beats a second one bundled in an application.
   - **The first step is evidence (B3-A/B3-C).** OpenSSL's QUIC on AROS, against an external peer: handshake, ALPN, streams, loss, a reduced MTU. A different library (ngtcp2 and others) is considered only if that fails.
2. **Crypto: two libraries, each where it fits.**
   - **Matter keeps its own mbedTLS 3.6.7 build** (ISSUE-0003: SDK crypto 71/71, about 16 KB of extra options, its config kept in aros-matter).
   - **TLS 1.3 and QUIC use contrib's OpenSSL.** Matter's crypto doesn't use TLS. The SDK also has an OpenSSL PAL, so consolidating on OpenSSL later is possible but not needed now: it would mean validating the SDK against OpenSSL 4.0, and OpenSSL is much larger.
   - **Common rules:** entropy comes from the CRT (`arc4random_buf()`, as AROSTCP since #2005; B3-10 checks OpenSSL's seed source on AROS), and no crypto primitive is written by us. Open Screen's SPAKE2 is not Matter's SPAKE2+ (B3-11).
3. **DNS-SD: one system service, Bonami/mdnsd, for everyone.**
   - **Shared prerequisite:** IPv6 in mdnsd (ISSUE-0005, the maintainer's) is a common prerequisite of Matter M2 and Open Screen B3-B.
   - **Interim:** until it lands, Matter may use the SDK's `minimal_mdns` (ISSUE-0004) and Open Screen a test responder.
   - **Coordination:** neither ships its own mDNS. Coordination goes through `docs/upstream-coordination.md`.
4. **Time.** Monotonic time for timers is the CRT's (`clock_gettime(CLOCK_MONOTONIC)`, already used by the mbedTLS glue). B3-05 is a runtime test, not a stack change. The stack's own timer resolution (500 ms TCP slow tick) is group 7.

## 3. The network contract (L1)

| Capability | Matter | QUIC / Open Screen | AROSTCP today | Group |
|---|---|---|---|---|
| IPv6 link-local with zones, source selection | ✔ needed | ✔ needed | done (#1970–#2005); G18e/f/i open | 5 |
| Multicast/MLD, `IPV6_MULTICAST_IF`, two interfaces | ✔ (mDNS) | ✔ (mDNS) | done for one interface; not tested with two | 5 (B3-02) |
| `IPV6_RECVPKTINFO` / `IP_RECVDSTADDR` (local address of a datagram) | ✔ | ✔ (OpenSSL BIO uses either) | present | 4 (test) |
| Non-blocking UDP, `WaitSelect`, EWOULDBLOCK | ✔ | ✔ | present | 4 (test, B3-04) |
| Datagrams ≥ 1200 bytes, `MSG_TRUNC`, `SO_RCVBUF`, bursts | ✔ | ✔ | `MSG_TRUNC` set on truncation (`uipc_socket.c:976`); not tested | 4 (B3-01/07) |
| **UDP with DF; EMSGSIZE instead of fragmenting; path MTU to the app** | — | ✔ **required** (RFC 9000 §14) | **absent**: no `IPV6_DONTFRAG`, `IPV6_PATHMTU`, `IPV6_RECVPATHMTU`, `IPV6_USE_MIN_MTU` (RFC 3542 §11), no `IP_DONTFRAG`; UDP ignores `PRC_MSGSIZE` since #2005/#2006 | **3** (B3-06) |
| ECN on UDP: `IPV6_TCLASS`/`IP_TOS` on send, `IPV6_RECVTCLASS`/`IP_RECVTOS` on receive | — | optional (RFC 9000 §13.4) | `IPV6_TCLASS` present; receive side absent | 3 |
| TCP: path MTU (both families), black holes, ECN, recovery | optional (Matter over TCP) | — | PMTUD done (#2005/#2006); black holes, ECN modes, PRR default open | 3, 6 |
| DNS servers from RAs (RDNSS) | ✔ (IPv6-only networks) | ✔ | absent | 5 |
| Keepalive options, `TCP_USER_TIMEOUT` | optional | — | header-only | 4 |

aros-midihub was also checked (plan, §aros-midihub): it needs nothing beyond these rows.

Nothing in the table is Matter-only or Open-Screen-only code in the stack: every row is a generic socket capability with an RFC behind it.

## 4. Effect on the PR groups

Updated in [2026-10-31-arostcp-pr-groups-plan.md](2026-10-31-arostcp-pr-groups-plan.md):
- **Group 3 becomes "Path MTU and ECN, TCP and UDP":** TCP black-hole detection; the UDP DF and path-MTU options (B3-06), with a connected DF socket told of Packet Too Big; ECN modes (TCP accept-only by default) and UDP ECN ancillary data; sysctl knobs. Group 3 then closes the risk #2006 opened and the only hard QUIC prerequisite in the stack.
- **PRR on by default moves to group 6** (TCP recovery and hardening), next to RFC 5961, where loss-recovery behaviour is reviewed as a whole.
- **Group 4 adds the UDP correctness tests** (B3-01/04/07): large datagrams, `MSG_TRUNC`, buffers, non-blocking.
- **Group 5 adds two-interface tests** (B3-02/08: a second tap) and interface down/up with reconnection.

## 5. Outside the stack, in order

1. **Bonami/mdnsd IPv6** (ISSUE-0005): the maintainer's; the shared prerequisite for discovery in both Matter and Open Screen.
2. **OpenSSL QUIC on AROS** (B3-A/B3-C), once group 3 is merged:
   - an echo test over QUIC between AROS and a Linux peer, both directions, on the existing hosted/tap bench;
   - including `pmtud_probe.py --router` for a narrower path.
   - This lives in aros-matter's benches until the Prism takes it over (B3-E).
3. **Matter ISSUE-0003 step 4** and M1, when the Matter track resumes.
