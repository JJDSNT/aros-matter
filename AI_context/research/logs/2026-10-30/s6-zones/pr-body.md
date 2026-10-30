## Scope

A link-scope IPv6 address names a link only together with its zone, the interface index in `sin6_scope_id` (RFC 4007). Readme §6.6 already follows that model for output: the link is the one the caller names, and the zone is never embedded. The socket calls do not:

- **`bind()` takes any address.** It takes addresses that are not ours, and a link-local one whatever its `sin6_scope_id`.
- **`connect()` ignores the peer's `sin6_scope_id`.** The routing table picks the link, so on a host with two interfaces `connect(fe80::1%eth1)` can go out the wrong one.
- **No zone is ever reported.** `getsockname()`, `getpeername()`, `accept()` and `recvfrom()` return `sin6_scope_id` 0. A program cannot tell which link a link-local peer is on, nor reply to the address it was given.
- **Packets to our own link-local look like they came from `lo0`.** They loop back through `lo0` and are marked received there, so `IPV6_PKTINFO` reports lo0 and the source's zone is lost.

Commits:

1. **Test.** `cunit-net-scope6`, see below.
2. **Loopback.** A packet to one of our own link-local addresses still goes through `lo0`'s queue, but `looutput()` gets the interface that owns the address, as KAME's `ip6_output()` does with `origifp`. The packet is received on, and counted against, that interface. Other addresses still arrive on `lo0`.
3. **Zones in the socket calls.** A socket's zone is kept in `inp_boundif`, the interface `SO_BINDTODEVICE` also sets, as Linux keeps it in `sk_bound_dev_if`.
   - `in6_pcbbind()` accepts only our usable addresses (or a group, or `::`), and a link-scope one only in its zone. It sets the socket's zone.
   - `in6_pcbconnect()` takes a link-scope peer's zone from `sin6_scope_id`, else the socket's. It returns `ENXIO` for an index no interface has and `EINVAL` for a zone other than the socket's, and picks the source on that link. Without a zone, the routing table picks the link as before: RFC 4007 §6 allows a default zone.
   - `in6_setsockaddr()`/`in6_setpeeraddr()` report the zone of link-scope addresses. For an accepted connection that is the link its link-local address is on, so the syncache needs no change.
   - `udp6_input()` and `rip6_input()` set `sin6_scope_id` on a link-scope source: the link it arrived on.
   - Readme §6.6 describes all of it.

`struct inpcb` does not change. There is no API or ABI change.

## Reproduction and validation

Hosted linux-x86_64, with `tap.device` attached to a host tap. The series is on master `273470fdd2`.

`cunit-net-scope6 eth0`, the same in both CUnit runs (basic and automated):

| Test | master | after commit 2 | this branch |
|---|---|---|---|
| `bind()` refuses an address that is not ours (`EADDRNOTAVAIL`) | **FAILED** | **FAILED** | passed |
| a link-local address binds in its zone (`getsockname()` reports it) | **FAILED** | **FAILED** | passed |
| a link-local address does not bind in `lo0`'s zone | **FAILED** | **FAILED** | passed |
| `connect()` takes the peer's zone (`getpeername()`/`getsockname()`) | **FAILED** | **FAILED** | passed |
| `connect()` refuses an unknown zone (`ENXIO`) | **FAILED** | **FAILED** | passed |
| `recvfrom()` reports the source's zone | **FAILED** | **FAILED** | passed |
| `IPV6_PKTINFO` gives the link-local's own link | **FAILED** (lo0) | passed | passed |
| TCP over a link-local address reports the zone (`accept()`, both ends) | **FAILED** | **FAILED** | passed |

The cunit socket, tcp, udp, inet6, mld6, route6, cmsg, addr6, srcaddr6, mcast6 and raw6 suites pass unchanged on master and on this branch, in both runs.

**End to end, with a peer on the host:** my wider IPv6 harness (57 checks) is not part of this PR. With the host sending to AROS from its link-local, `recvfrom()` gives `fe80::…%2` on this branch and `%0` on master. `sendto(ff02::fb%eth0)` from `[::]` also reaches the host now, through `in6_pcbconnect()`; #1973 fixes the same case on the `sendto()` side. The six checks still failing are the same on both: they send multicast with `IPV6_MULTICAST_IF` and no `sin6_scope_id`, and that option does not yet pick the source.

**Additional validation:** each commit builds `workbench-network-stacks-arostcp`; `test-socket-yes-cunit` builds; `git diff --check` is clean. Only hosted x86-64 was built and run.

## Notes

Decisions for you:

- **The zone lives in `inp_boundif`.** This avoids adding fields to the public `struct inpcb`, at the cost of sharing the field with `SO_BINDTODEVICE`. `SO_BINDTODEVICE` stays IPv4-only. The alternative is a zone field at the end of the `INET6` part of `struct inpcb`.
- **No `sin6_scope_id` keeps today's behaviour** for link-scope `connect()`: the routing table picks the link. Linux refuses that with `EINVAL`. I kept compatibility.
- **`bind()` now refuses addresses that are not ours**, and tentative ones, with `EADDRNOTAVAIL`, as the BSDs and Linux do. A program that bound an address before configuring it would now fail.
- **A looped packet counts against the owning interface.** Packets to our own link-local now count in that interface's statistics rather than `lo0`'s, as on KAME.

Overlap: #1973 adds a test on the same mmakefile line. Nothing else conflicts; #1973 changes `udp6_output()`, this changes `udp6_input()`.
