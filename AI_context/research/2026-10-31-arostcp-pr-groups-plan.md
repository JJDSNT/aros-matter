# AROSTCP — plan of the next PR groups (2026-10-31)

Current priority: completing the stack (Matter on hold, `current_state.md`). The maintainer left the choices to the agent, ECN and PRR defaults included. Revised 2026-11-01 so that the groups also cover the network prerequisites of Matter and of Open Screen ([backlog3.md](../backlog3.md)); see [2026-11-01-network-roadmap-integration.md](2026-11-01-network-roadmap-integration.md).

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
| 3 | (to open) | Path MTU and ECN, TCP and UDP | ready (5.22), branch `review/arostcp-series3` |
| 4 | — | Socket API and compatibility | |
| 5 | — | IPv6 on real networks | |
| 6 | — | TCP recovery and hardening | |
| 7 | — | Timers and congestion | research first |

The order follows risk and dependencies. Group 3 covers what #2006 introduced (DF on IPv4 can black-hole). Groups 4 and 5 are what applications and IPv6-only networks miss. Group 6 is defensive hardening. Group 7 needs measurement before any code.

## Group 3 — Path MTU and ECN, TCP and UDP

**As built (2026-11-01), four commits, 5.22 / kernel v0.61:**
1. TCP black-hole detection (FreeBSD's steps; on by default, as XNU) + sysctls `pmtud`, `pmtud_blackhole`; `defines/miami.h` `MiamiSysCtl()` fixed (it returned void and its macro did not compile). Test: `cunit-net-sysctl`; wire `pmtud_probe.py --blackhole` (master stalls, v4 and v6).
2. RFC 3542 §11 (`IPV6_USE_MIN_MTU` default -1 as KAME, `IPV6_DONTFRAG` sends above the path MTU and refuses only above the link MTU, `IPV6_RECVPATHMTU`, `IPV6_PATHMTU`) and `IP_DONTFRAG`; ICMPv6 errors about link-scope destinations carry the zone. `cunit-net-frag6` asks for `IPV6_USE_MIN_MTU 0`. Test: `cunit-net-udppmtu` (6/6 fail on master).
3. ECN modes, default 2; ECT over IPv6 (`tcp_v6output()` takes the traffic class); found by the wire test and fixed: CE on in-sequence data never echoed and ECE on pure ACKs never seen (handled after header prediction; moved before it, as FreeBSD), CWR on every ECE (now on the first new data after a reduction). Test: `cunit-net-sysctl` ecn; wire `ecn_probe.py` (new, with `tcpserve.c`).
4. UDP ECN field: `IPV6_RECVTCLASS`, `IPV6_TCLASS` actually sent (it was accepted and ignored: traffic class always 0), `IP_RECVTOS`, `IP_TOS` ancillary data; IPv4 multicast/broadcast datagrams had no ancillary data at all (`udp_savecontrol()`). Test: `cunit-net-cmsg` (3 new, fail on master).

Item 4 of the plan (sysctl knobs) went into commits 1 and 3, with the features.

**Plan as written:**

This closes the risk #2006 opened (DF on IPv4 TCP) and the only hard QUIC prerequisite in the stack (B3-06).

1. **TCP PMTU black-hole detection** (RFC 2923, a simplified RFC 4821/8899, as FreeBSD's `pmtud_blackhole_detection`). After two retransmission timeouts of a full-sized segment, retry with a smaller MSS (1220 for IPv6, 1200/536 for IPv4); keep it once acknowledged; give it back like a learned path MTU.
   - Test: `pmtud_probe.py --router` with no ICMP (a filtered path). Master stalls; the branch completes.
2. **UDP with DF and the path MTU for applications** (RFC 3542 §11; B3-06; RFC 9000 §14).
   - `IPV6_DONTFRAG` and `IP_DONTFRAG` (BSD names; OpenSSL's datagram BIO looks for them): DF on, and EMSGSIZE instead of fragmenting.
   - `IPV6_USE_MIN_MTU`.
   - `IPV6_PATHMTU` (getsockopt) and `IPV6_RECVPATHMTU` (ancillary data when a Packet Too Big arrives).
   - `udp6_ctlinput`/`udp_ctlinput` stop ignoring `PRC_MSGSIZE` for sockets that set DF: they report the new MTU, and EMSGSIZE on a connected socket.
   - Test: CUnit, via a Packet Too Big / "fragmentation needed" to ourselves, as `pmtu4`/`pmtu6`.
3. **ECN.**
   - TCP: modes 0 off, 1 initiate and accept, 2 accept only; **default 2** (Linux `tcp_ecn=2`, FreeBSD `ecn.enable=2`).
   - UDP ancillary data: `IP_RECVTOS`/`IPV6_RECVTCLASS` on receive, `IP_TOS`/`IPV6_TCLASS` on send (RFC 9000 §13.4).
   - Test: wire. Linux initiating ECN gets it negotiated; AROS doesn't propose it by default; CE marks (host tc) reduce cwnd once per window.
   - Test: CUnit for the UDP TOS/TCLASS round trip on loopback.
4. **sysctl knobs** `ecn`, `pmtud`, `pmtud_blackhole` (new `TCPCTL_*` names in `netinet/tcp_var.h`, appended).
   - Test: CUnit `MiamiSysCtl()` round trip.

## Group 4 — Socket API and compatibility

1. **R3 keepalive options:** `TCP_KEEPIDLE`/`TCP_KEEPINTVL`/`TCP_KEEPCNT`/`TCP_KEEPINIT` (defined in `tcp.h`, not handled by `tcp_ctloutput()`) per socket, and `TCP_USER_TIMEOUT` (RFC 5482). Check the Roadshow/AmiTCP API first (values, units).
   - Test: CUnit set/get, and a dead peer detected within the set time.
2. **S1 `localhost`** (RFC 6761 §6.3): `getaddrinfo("localhost", …)` returns `::1` and `127.0.0.1` (AF_UNSPEC), without the resolver.
   - Test: CUnit.
3. **UDP correctness** (B3-01/04/07). Tests first, fixes only for what fails:
   - datagrams of 1200–9000 bytes over IPv4/IPv6 without truncation;
   - `MSG_TRUNC` in `msg_flags` when the buffer is short;
   - `SO_RCVBUF`/`SO_SNDBUF` and bursts;
   - EWOULDBLOCK on non-blocking sockets;
   - `IP_RECVDSTADDR`/`IPV6_RECVPKTINFO` on every datagram.
4. **`SO_TIMESTAMP`** (4.4BSD; FreeBSD/Linux `SCM_TIMESTAMP`): the receive time of each datagram as ancillary data (`struct timeval`), taken when the packet reaches the socket. The header defines it, but `sosetopt()` rejects it with `ENOPROTOOPT`. Added next to `IP_RECVDSTADDR` (`udp_usrreq.c`) and `IPV6_RECVPKTINFO` (UDP6). Consumers: Network MIDI and AppleMIDI clock sync, where the stack's receive time is free of the delay before the application task runs; RTT and jitter measurement in general.
   - Test: CUnit, datagram on loopback: `SCM_TIMESTAMP` present, between the times before the send and after the receive; absent without the option.
5. **Stackprobe S3, S5, S6, S7:** `MSG_DONTWAIT`, `getnetbyaddr(127)`, Roadshow `ObtainInterfaceList`/`QueryInterfaceTagList`/`GetRouteInfo`, `In_CanForward()`. Each is checked against its documented contract first; only the confirmed defects are fixed. Stackprobe is a probe, not an oracle.
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
10. **IPv6 address state for applications** (RFC 4862 §5.4: a tentative address must not be used; mdnsd picks one link-local per interface and can't tell, Bonami README §Limits):
    - `SIOCGIFAFLAG_IN6` (KAME, `netinet6/in6_var.h`): an address's `IN6_IFF_*` flags (tentative, duplicated, deprecated, autoconf).
    - The `SBTC_SIG_ADDRESS_CHANGE_MASK` signal (and `RTM_NEWADDR`) also when DAD ends, passed or duplicated (`nd6_nbr.c` clears `IN6_IFF_TENTATIVE` silently today), so a woken consumer sees the address once usable.
    - Test: CUnit, an address added on loopback/tap: tentative, then the signal, then not tentative; a duplicate (a NA to ourselves) reported as `IN6_IFF_DUPLICATED`.
11. **Two interfaces** (B3-02/08): multicast join, send and receive on each with a second tap; source and zone per interface; an interface going down and up, and sockets reconnecting.
    - Also a test that `SBTC_SIG_ADDRESS_CHANGE_MASK` fires for IPv4 and IPv6 adds and deletes, SLAAC included (aros-midihub MD13 wants to stop polling; the signal already exists, `api_sendaddrchange()`).

Each G18 item is first reproduced; the ones that don't reproduce are closed with the evidence. If the group grows too large it is split into 5a (RDNSS + routing) and 5b (source selection + zones).

## Group 6 — TCP recovery and hardening

1. **PRR on by default** (RFC 6937; Linux since 3.2, FreeBSD 14).
   - Test: loss bench with PRR off and on (recovery time, retransmissions, no stall, sanity ok).
   - Test: the router probe, under PRR.
2. **R2, RFC 5961:** in-window RST, SYN and ACK validation, challenge ACKs rate-limited per connection.
3. **Timestamps with a random per-connection offset** (RFC 7323 §5.4; FreeBSD/Linux), so TSval does not reveal uptime.
4. **SYN cookies:** review against RFC 4987 with the new key source (#2005).

## Group 7 — Timers and congestion (research first)

1. **RTO granularity** (RFC 6298): the 500 ms slow tick limits RTO resolution; measure first, then consider an ms-resolution RTO from the 200 ms fast timer or `GetSysTime()`.
2. **HyStart++** (RFC 9406) for CUBIC slow start; **RACK-TLP** (RFC 8985). Only with A/B measurements showing a benefit, and after the SACK scoreboard is reviewed under loss.
3. **TCP Fast Open** (RFC 7413): optional, last.

## aros-midihub (checked 2026-11-01)

Written up for midihub in its `docs/arostcp-stack-findings-2026-11-01.md` (commit 81feeef).

Nothing new for the stack. Its needs are already covered or live elsewhere:
- **MD13** (address changes found by polling every 3 s): the stack already signals them (`SBTC_SIG_ADDRESS_CHANGE_MASK`, `api/amiga_api.c`, from `rt_newaddrmsg()`). mdnsd should subscribe; that is an mdnsd change. Group 5 item 10 tests the signal.
- **IPv6 `SO_BINDTODEVICE`** (mdnsd binds per interface on IPv4; on IPv6 `sosetopt()` returns `ENOPROTOOPT`, and mdnsd uses one wildcard socket with `IPV6_PKTINFO`): group 5, G18i.
- **MD08** (multicast filters): the stack asks SANA-II for IPv4 and IPv6 groups (`netinet/in.c`, `netinet6/in6.c`); whether each driver honours `S2_ADDMULTICASTADDRESS` is driver work.
- **AM14/NM15/MD14** (IPv6 in AppleMIDI, Network MIDI 2.0, mdnsd): application work; mdnsd's dual-stack core is merged (#1980) and the stack side is in.
- **MD18** (m68k AROSTCP build needs the `fd.library` headers): a build fix, not stack behaviour; it goes as its own small PR from aros-midihub.
- **`SO_TIMESTAMP`** (defined, rejected with `ENOPROTOOPT`): group 4 item 4. Network MIDI carries its timestamps in the payload, but its clock sync gains from the stack's receive time (midihub L12 is BLE, unrelated).
- **D1** (a library base belongs to its task): AmiTCP's `ObtainSocket`/`ReleaseSocket` already cover handing sockets over.

## Not planned

- **Removing the T/TCP code** (off since #1996): a cleanup, not a fix. Only if Kal asks.
