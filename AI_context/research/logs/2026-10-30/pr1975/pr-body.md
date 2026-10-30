## Scope

`IPV6_MULTICAST_IF` names the interface outgoing multicast leaves by (RFC 3493 §5.2), and `ip6_output()` does send the datagram there. The source address does not follow it. `udp6_output()` looks for an interface only in `IPV6_PKTINFO` and `sin6_scope_id`, then falls back to the routing table, which has no route for `ff02::/16`.

So a socket on `[::]` that sets `IPV6_MULTICAST_IF` and sends to `ff02::fb` gets `EADDRNOTAVAIL`. That is how an mDNS responder sends.

Commits:

1. **Test.** `cunit-net-sendto6` gains a case: a socket bound to `[::]` sets `IPV6_MULTICAST_IF` and sends to `ff02::4d54:63`. A member of that group on the interface must receive the looped-back copy from the interface's link-local address.
2. **Fix.** When the datagram names no interface and goes to a group, `udp6_output()` takes the `IPV6_MULTICAST_IF` interface for the source as well, as KAME's `in6_selectsrc()` does with the multicast options. Raw IPv6 sockets already do this (#1971). Readme §6 says so.

There is no API, ABI or structure change.

## Reproduction and validation

Hosted linux-x86_64, with `tap.device` attached to a host tap. The series is on master `b145f05fb3`.

`cunit-net-sendto6 eth0`, the same in both CUnit runs (basic and automated):

| Test | master | this branch |
|---|---|---|
| `sendto()` leaves the socket unbound | passed | passed |
| after `sendto()` the socket receives on its other addresses | passed | passed |
| an `IPV6_PKTINFO` source is used | passed | passed |
| `IPV6_MULTICAST_IF` names a group datagram's source | **FAILED** | passed |

The cunit socket, tcp, udp, inet6, mld6, route6, cmsg, addr6, srcaddr6, mcast6 and raw6 suites pass unchanged on master and on this branch, in both runs.

**End to end, with a peer on the host:** in my wider IPv6 harness (57 checks, not part of this PR), master fails 7 checks and this branch 1.

- **Now passing:** the six checks that send to `ff02::fb` from `[::]` with `IPV6_MULTICAST_IF`.
  - On master, `sendto()` fails with `EADDRNOTAVAIL`.
  - On this branch, the host receives the datagram from AROS's link-local. A local member receives the looped-back copy, and with `IPV6_MULTICAST_LOOP 0` it does not.
- **Still failing:** `sin6_scope_id` on a received link-local source, which #1974 fixes.

**Additional validation:** each commit builds `workbench-network-stacks-arostcp`; `test-socket-yes-cunit` builds; `git diff --check` is clean. Only hosted x86-64 was built and run.

## Notes

- **Not changed:**
  - `connect()` to a group still picks its source from the zone (#1974) or the routing table, not from `IPV6_MULTICAST_IF`.
  - `ip6_output()` still falls back to the first interface that is up when a group datagram names no interface at all.
- **Overlap:** none with #1974 beyond the Readme paragraph context.
