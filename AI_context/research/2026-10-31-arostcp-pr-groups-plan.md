# AROSTCP — plan of the next PR groups (2026-10-31)

Current priority: completing the stack (Matter on hold, `current_state.md`). The maintainer left the choices to the agent, ECN and PRR defaults included.

Rules (Kal, 2026-10-31):
- One grouped PR open at a time; the next is prepared locally (`review/arostcp-series<N>`) and opened only after the open one is merged.
- One commit per change, its test with it.
- One revision bump, in the last commit (`…; 5.xx`).
- No Claude attribution.
- Each change gets an upstream-style CUnit test that fails on master. Where the loopback can't show the behaviour, it gets a wire check with the benches (`tests/tcp/run_tcp.py`, `pmtud_probe.py`, both now self-checking).

| Group | PR | Theme | State |
|---|---|---|---|
| 1 | #2005 | IPv6/TCP conformance series | merged (5.20) |
| 2 | #2006 | IPv4 ARP queue, IPv4 path MTU discovery | in review (5.21) |
| 3 | — | TCP robustness and defaults | next |
| 4 | — | Socket API and compatibility | |
| 5 | — | IPv6 on real networks | |
| 6 | — | TCP hardening | |
| 7 | — | Timers and congestion | research first |

The order follows risk and dependencies. Group 3 covers what #2006 introduced (DF on IPv4 can black-hole). Groups 4 and 5 are what applications and IPv6-only networks miss. Group 6 is defensive hardening. Group 7 needs measurement before any code.

## Group 3 — TCP robustness and defaults

1. **PMTU black-hole detection** (RFC 2923, a simplified RFC 4821/8899, as FreeBSD's `pmtud_blackhole_detection`). With DF on (#2006), a path that filters ICMP leaves a connection retransmitting full segments forever. After two retransmission timeouts of a full-sized segment, retry with a smaller MSS (1220 for IPv6, 1200/536 for IPv4); when that gets acknowledged, keep it; give it back like a learned path MTU.
   - Test: `pmtud_probe.py --router` with the injector off (a filtered path). Master stalls; the branch completes.
   - Test: CUnit only if a lossy path can be made locally; otherwise the bench.
2. **PRR on by default** (RFC 6937; Linux since 3.2, FreeBSD 14).
   - Test: loss bench with PRR off and on (recovery time, retransmissions, no stall, sanity ok).
   - Test: router probe; the partial-ACK path fixed in #2005 under PRR.
3. **ECN modes; accept-only by default** (RFC 3168; Linux `tcp_ecn=2`, FreeBSD `ecn.enable=2`). `tcp_do_ecn`: 0 off, 1 initiate and accept, 2 accept only. Default 2: answer ECN when the peer proposes it, don't propose it in our SYNs (old middleboxes).
   - Test: wire. Linux initiating (`net.ipv4.tcp_ecn=1`) gets ECN negotiated; AROS initiating doesn't propose it by default.
   - Test: CE marks (host tc with ECN marking) reduce cwnd once per window.
   - Test: CUnit for the default on loopback (AROS↔AROS: no ECE/CWR in the SYN; BPF can't see the loopback, so this is checked on eth0 against the neighbour, as `tcpsyn6`).
4. **sysctl knobs** for `ecn`, `prr`, `pmtud`, `pmtud_blackhole` in `tcp_sysctl` (new `TCPCTL_*` names in `netinet/tcp_var.h`, appended; backwards-compatible).
   - Test: CUnit `MiamiSysCtl()` read/write round trip.

## Group 4 — Socket API and compatibility

1. **R3 keepalive options:** `TCP_KEEPIDLE`/`TCP_KEEPINTVL`/`TCP_KEEPCNT`/`TCP_KEEPINIT` (defined in `tcp.h`, not handled by `tcp_ctloutput()`) per socket, and `TCP_USER_TIMEOUT` (RFC 5482). Check the Roadshow/AmiTCP API first (values, units).
   - Test: CUnit set/get, and a dead peer detected within the set time.
2. **S1 `localhost`** (RFC 6761 §6.3): `getaddrinfo("localhost", …)` returns `::1` and `127.0.0.1` (AF_UNSPEC), without the resolver.
   - Test: CUnit.
3. **Stackprobe S3, S5, S6, S7:** `MSG_DONTWAIT`, `getnetbyaddr(127)`, Roadshow `ObtainInterfaceList`/`QueryInterfaceTagList`/`GetRouteInfo`, `In_CanForward()`. Each is checked against its documented contract first; only the confirmed defects are fixed. Stackprobe is a probe, not an oracle.
   - Test: CUnit per defect.

## Group 5 — IPv6 on real networks

1. **R4 RDNSS/DNSSL** (RFC 8106): DNS servers and search list from Router Advertisements, into the resolver's configuration, with their lifetimes. Needed on IPv6-only networks.
   - Test: CUnit sending itself an RA with RDNSS (as `cunit-net-rio6`), then the resolver's server list.
2. **G18a** router selection by reachability (RFC 4191 §3.2/3.5, RFC 4861 §6.3.6).
3. **G18b** redirect validation (RFC 4861 §8).
4. **G18c** `nd6_prefix_lookup()` per interface.
5. **G18d** SLAAC address deleted by hand comes back with the next RA.
6. **G18e** RFC 6724 rules 1, 5, 6, 8 (and the policy table, if small).
7. **G18f** `IPV6_PKTINFO` takes precedence over the bound address (RFC 3542 §6.1).
8. **G18g/h** `connect()` to a group and the first-interface fallback (from #1975).
9. **G18i** `SO_BINDTODEVICE` for IPv6; link-scope `connect()` without a zone.

Each G18 item is first reproduced; the ones that don't reproduce are closed with the evidence. If the group grows too large it is split into 5a (RDNSS + routing) and 5b (source selection + zones).

## Group 6 — TCP hardening

1. **R2, RFC 5961:** in-window RST, SYN and ACK validation, challenge ACKs rate-limited per connection.
2. **Timestamps with a random per-connection offset** (RFC 7323 §5.4; FreeBSD/Linux), so TSval does not reveal uptime.
3. **SYN cookies:** review against RFC 4987 with the new key source (#2005).

## Group 7 — Timers and congestion (research first)

1. **RTO granularity** (RFC 6298): the 500 ms slow tick limits RTO resolution; measure first, then consider an ms-resolution RTO from the 200 ms fast timer or `GetSysTime()`.
2. **HyStart++** (RFC 9406) for CUBIC slow start; **RACK-TLP** (RFC 8985). Only with A/B measurements showing a benefit, and after the SACK scoreboard is reviewed under loss.
3. **TCP Fast Open** (RFC 7413): optional, last.

## Not planned

- **Removing the T/TCP code** (off since #1996): a cleanup, not a fix. Only if Kal asks.
