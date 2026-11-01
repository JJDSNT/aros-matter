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
| 2 | #2006 | IPv4 ARP queue, IPv4 path MTU discovery | merged (5.21) |
| 3 | #2011 | Path MTU and ECN, TCP and UDP | merged (5.22) |
| 4 | #2023 | Socket API and compatibility | in review (5.24) |
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

**As built (2026-11-01), eleven commits, 5.24 / kernel v0.63** (Kal's 8b16329595, RFC 6724 source selection = 5.23, came in between):
1. keepalive per connection (FreeBSD's options); 2. `TCP_USER_TIMEOUT` (Linux semantics, checked from `tcp_slowtimo()`); 3. **found by the keepalive test:** `tcp_slowtimo()` took `tcp_usrreq()`'s 0 (success) for "gone", so timers and idle/RTT clocks stood still on every tick a timer fired (keepalive at half speed);
4. localhost names (RFC 6761 6.3) in `gethostnamadr.c`, all lookups; 5. S5: networks table `n_net` in host order (`__inet_network()`); 6. **found by the netdb test:** `inet_network()` stack overflow on five parts (4.4BSD bug); 7. S7: `in_canforward()` lost the `IN_LOOPBACKNET` shift (127/8 forwardable), + link-local; `In_*` macros were missing from `defines/bsdsocket.h`;
8. `SO_TIMESTAMP`/`SO_TS_CLOCK`: realtime from stdc `timespec_get(TIME_UTC)` (= posixc `gettimeofday()`, zone per call, no cache needed - the open question resolved), monotonic from `GetUpTime()`; options at `splnet`; 9. S3: `MSG_DONTWAIT`; 10. S6: `ObtainInterfaceList()` + `QueryInterfaceTagList()` address tags; `GetRouteInfo()` version 3 is the probe's Roadshow-m68k assumption, not a defect; 11. `cunit-net-udpio` (all pass on master; regression only).
Benches: `tcpopt_probe.py` (keepalive/UTO/zero window), `udpbig_probe.py` (1200-9000 B on the wire). Not tested: a time-zone change (needs locale's internal `LocalePrefsUpdate()`); equivalence is by construction.

**Plan as written:**

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

**Refinements (2026-11-01, review of the plan):**
- `TCP_USER_TIMEOUT` is its own item, not a keepalive option (RFC 5482): the longest transmitted data may stay unacknowledged, or data blocked by a zero window, before the connection is aborted; it replaces the retransmission-count limit. Tests apart: a peer that vanishes mid-transfer (abort within the timeout, not after ~12 retransmissions), a persistent zero window, and with keepalive on too (Linux also bounds keepalive probes by it; check FreeBSD, choose and document).
- `SO_TIMESTAMP` gets an explicit ABI contract. AROS's `struct timeval` is two 32-bit fields on every architecture (`aros/types/timeval_s.h`), so the layout is the same on 32 and 64 bits; the epoch is the risk (the Amiga clock counts from 1978): `SCM_TIMESTAMP` uses the clock and epoch of posixc `gettimeofday()`. `SO_TS_CLOCK` (already in `sys/socket.h`, FreeBSD's) with `SO_TS_MONOTONIC` gives `SCM_MONOTONIC` (`struct timespec`) on the clock of posixc `clock_gettime(CLOCK_MONOTONIC)` - the one Network MIDI wants. The mark is taken when the datagram reaches the socket buffer; the test delays `recvmsg()` on purpose and checks the stamp is earlier than the call.
- UDP size tests keep the families and causes apart: the loopback MTU is 1536 (`LOMTU`), so 9000 bytes there tests fragmentation and reassembly, not a large-MTU path; `udp_sendspace` is 9216, so larger datagrams fail on the socket limit (legitimate, `SO_SNDBUF`); `IPV6_DONTFRAG`/`IP_DONTFRAG` above the link MTU must give `EMSGSIZE`. Cases: loopback v4/v6; the wire at 1500 with the host echoing (fragments counted); optionally jumbo end to end (AROSTCP has jumbo-frame support) with tap and AROS at 9000. Each failure is classed as network limit, configured limit or defect.

**`SO_TIMESTAMP` design, as settled (2026-11-01):**
- The stamp and the message type are decided at reception, before `sbappendaddr()` (in `udp_savecontrol()`), and kept with the datagram: changing `SO_TS_CLOCK` affects later datagrams only.
- `SO_TS_REALTIME_MICRO` (default) -> `SCM_TIMESTAMP`, `struct timeval`: `GetSysTime()` + `OFFSET_FROM_1970` + the time zone, to match posixc `gettimeofday()` (which asks the locale on every call; net.lib computes `__local_to_GMT` once at program start). `SO_TS_MONOTONIC` -> `SCM_MONOTONIC`, `struct timespec`: `GetUpTime()`, as posixc `CLOCK_MONOTONIC`. One clock read per datagram. `SO_TS_REALTIME`/`SO_TS_BINTIME`: `EOPNOTSUPP` (an AROS choice, documented; FreeBSD implements them); above `SO_TS_CLOCK_MAX`: `EINVAL`.
- Not `__stdc_gmtoffset()` per datagram: stdc calls it internal, it opens and closes the locale on every call, and returns 0 before locale.library is loaded. Open: how to follow the time zone - a locale/IPrefs notification or DOS notification on `ENV:` first, a cache refreshed from the slow timer (never on the receive path) only if neither works.
- Locking: `setsockopt()` holds only `syscall_semaphore`, which the daemon never takes; generic `SOL_SOCKET` options change `so_options` without `splnet`. So `SO_TIMESTAMP`/`SO_TS_CLOCK` are changed at `splnet` and read once per datagram. (Aside, not in group 4: `SO_REUSEADDR`/`SO_REUSEPORT`, read by UDP input, are also set without `splnet`.)
- Tests: set/get; no message when off; a clock change between two queued datagrams (each keeps its own type); stamps of datagrams received at different times differ and are earlier than a delayed `recvmsg()`; `sizeof`/`offsetof`/field sizes of `timeval` and `timespec` on 32 and 64 bits; the time zone changed without the clock - `SCM_TIMESTAMP` still matches `gettimeofday()`. Matching is against the reception instant, never the `recvmsg()` call: on the loopback each stamp must fall between a `gettimeofday()` taken just before `sendto()` and one taken as soon as the socket is readable (before any deliberate delay); for the zone, one datagram just before the change and one just after, each with its own bracket.

## Group 5 — IPv6 on real networks

**Split (2026-11-01), two PRs, 5b after 5a merges:** 5a = configuration and routing (items 1-5); 5b = zones, interfaces and address state (items 7-11). Same procedure as group 4: reproduce first, fix only shown defects, document what already conforms.
- **RDNSS to the resolver:** learned servers go into `DynDB.dyn_NameServers` tagged with the interface (`nsn_Owner`), as the `DNS=`/`DNS6=` interface tokens already do, with the RA lifetime; `NetDB` (manual) is never touched and keeps precedence; RA and DHCPv6 lists coexist (RFC 8106 5.3.1). Tests end at the resolver: a query goes to the learned server; it expires with its lifetime; manual servers stay first; the interface going away removes it. DNSSL into the search list the same way.
- **IPv6 `SO_BINDTODEVICE` semantics, each tested:** an unzoned link-local peer takes the bound interface as its zone; an explicit zone other than the bound interface is an error, not a silent choice; an unknown interface gives `ENXIO` (as IPv4); the interface disappearing under a connection.
- **DAD tests are state transitions:** on the address-change signal, `SIOCGIFAFLAG_IN6` must already show the address no longer tentative (or duplicated) - the signal comes after the state change.

1. **R4 RDNSS/DNSSL** (RFC 8106): DNS servers and search list from Router Advertisements, into the resolver's configuration, with their lifetimes. Needed on IPv6-only networks.
   - Test: CUnit sending itself an RA with RDNSS (as `cunit-net-rio6`), then the resolver's server list.
2. **G18a** router selection by reachability (RFC 4191 §3.2/3.5, RFC 4861 §6.3.6).
3. **G18b** redirect validation (RFC 4861 §8).
4. **G18c** `nd6_prefix_lookup()` per interface.
5. **G18d** SLAAC address deleted by hand comes back with the next RA.
6. ~~**G18e** RFC 6724 rules~~ - done by Kal (8b16329595: rules 1, 6, 8 and the default policy table).
7. **G18f** `IPV6_PKTINFO` takes precedence over the bound address (RFC 3542 §6.1).
8. **G18g/h** `connect()` to a group and the first-interface fallback (from #1975).
9. **G18i** `SO_BINDTODEVICE` for IPv6; link-scope `connect()` without a zone.
10. **IPv6 address state for applications** (RFC 4862 §5.4: a tentative address must not be used; mdnsd picks one link-local per interface and can't tell, Bonami README §Limits):
    - `SIOCGIFAFLAG_IN6` (KAME, `netinet6/in6_var.h`): an address's `IN6_IFF_*` flags (tentative, duplicated, deprecated, autoconf).
    - The `SBTC_SIG_ADDRESS_CHANGE_MASK` signal (and `RTM_NEWADDR`) also when DAD ends, passed or duplicated (`nd6_nbr.c` clears `IN6_IFF_TENTATIVE` silently today), so a woken consumer sees the address once usable.
    - Test: CUnit, an address added on loopback/tap: tentative, then the signal, then not tentative; a duplicate (a NA to ourselves) reported as `IN6_IFF_DUPLICATED`.
11. **Two interfaces** (B3-02/08): multicast join, send and receive on each with a second tap; source and zone per interface; an interface going down and up, and sockets reconnecting.
    - Also a test that `SBTC_SIG_ADDRESS_CHANGE_MASK` fires for IPv4 and IPv6 adds and deletes, SLAAC included (aros-midihub MD13 wants to stop polling; the signal already exists, `api_sendaddrchange()`).

12. **Jumbo end to end** (run 2026-11-01 on 5.24, `jumbo_probe.py`, `AROS_TAP_MTU`): conforms - UDP fragments only above 8972 (IPv4) / 8952 (IPv6) bytes, every echo whole; SYN MSS 8960 / 8940; with a 1500-byte router in the path the PMTU falls to 1500 (IPv6: all packets <= 1500 after the PTB, the next SYN offers 1440; IPv4: only the 3 segments in flight above). **Finding, for 5b:** `tcp_mss()` rounds the MSS down to a multiple of the mbuf cluster (2048, 4.4BSD-Lite, "to utilize large mbufs"): 8948 -> 8192 on a 9000 path, 3948 -> 2048 on a 4000 one; Linux never did, FreeBSD dropped it; `tcp_setmtu()` (PMTU) does not round, so the two disagree. Fix with an A/B throughput measurement at 9000. Logs: `logs/2026-11-01/jumbo/`.

Each G18 item is first reproduced; the ones that don't reproduce are closed with the evidence. If the group grows too large it is split into 5a (RDNSS + routing) and 5b (source selection + zones).

## Group 6 — TCP recovery and hardening

Added (2026-11-01, Kal on #2023): `MSG_DONTWAIT` and `SS_NBIO` can still block in `sblock()` while another task holds the socket buffer; FreeBSD uses `SBLOCKWAIT(flags)`. Predates group 4.

Added (2026-11-01): `SO_REUSEADDR`/`SO_REUSEPORT` and the other generic `SOL_SOCKET` flags the daemon reads are set without `splnet` (found while doing `SO_TIMESTAMP`, group 4): reproduce/assess, then set them at `splnet`.

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
