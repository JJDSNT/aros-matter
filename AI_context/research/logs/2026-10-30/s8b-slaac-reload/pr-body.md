## Scope

After an in-place reload (`NCMD_RELOAD` on the control port) an interface that stays configured has no IPv6 at all. Two defects stack up:

- **The link-local address never comes back.**
  - The link-local is made by `in6_if_up()` when an interface comes up: on the `SIOCSIFFLAGS` that sets `IFF_UP`, or in `sana_restore()` when the device comes online.
  - The reload deletes every address in `sana_reconfig_teardown()`, the link-local included, but the interface stays up and running, so neither of those runs again.
  - `addifent()` assumes the link-local is still there; its comment says "the stack already assigns fe80::".
  - So the interface is left without its link-local, and with it go Neighbor Discovery, the Router Solicitation and SLAAC. On master, ten seconds after a reload `eth0` still has no IPv6 address; only `lo0`'s `::1` is left.
- **The prefixes keep stale state.**
  - The reload deletes the SLAAC addresses, but each prefix entry keeps `ndpr_autoconf` set.
  - So even with a link-local, the next Router Advertisement for the prefix finds the address "already configured" (`nd6_prefix_slaac()`) and does not make it again. It comes back only once the prefix expires.
  - The entries also keep a pointer to the interface after `nd6_ifdetach()`. This is the same problem #1976 fixed for the router list.

Commits:

1. **Test.** `cunit-net-slaac6`, see below.
2. **Link-local.** When `addifent()` reconfigures an interface that is up and running, it calls `in6_if_up()`, as when the interface comes up (RFC 4861 §6.3.7): it makes the link-local, starts its DAD and sends the Router Solicitation after it. `in6_if_up()` does nothing for an interface that still has its link-local. An interface that is not running yet gets it from `SIOCSIFFLAGS` or `sana_restore()`, as before. Readme §6.1 describes the reload.
3. **Prefixes.** `nd6_purge_prefixes()` drops the interface's prefixes with their on-link routes, as FreeBSD's `nd6_purge()` does. `sana_if_deconfigure()` and `nd6_ifdetach()` call it next to `nd6_purge_routers()`. No address refers to a prefix entry, so freeing one leaves nothing dangling.

Each fix alone leaves the test failing: without commit 2 there is no link-local to form the address from, and without commit 3 the prefix says the address exists.

There is no API, ABI or structure change.

## Reproduction and validation

Hosted linux-x86_64, with `tap.device` attached to a host tap that sends no Router Advertisements. The series is on master `be237767fa`.

`cunit-net-slaac6 eth0` works like this:

1. It sends a Router Advertisement from a raw ICMPv6 socket, with hop limit 255, to the interface's own link-local address. The RA has router lifetime 0 and an autonomous prefix `2001:db8:4d54:20::/64`. It is received on the interface and never goes out on the link.
2. It checks that the SLAAC address appears.
3. It reloads the stack through `<bsdsocket/netcontrol.h>`.
4. It checks that the address is gone, sends the same Router Advertisement, and checks that the address comes back.

| Test | master | commit 2 only | this branch |
|---|---|---|---|
| an autonomous prefix gives an address (first run) | passed | passed | passed |
| after a reload the prefix gives the address again (first run) | **FAILED** | **FAILED** | passed |
| both tests (second run, after the reload of the first) | **FAILED** 2/2 | **FAILED** 2/2 | passed |

The cunit socket, tcp, udp, inet6, mld6, route6, cmsg, addr6, srcaddr6, mcast6, raw6, sendto6, scope6 and rio6 suites pass unchanged on master and on this branch, in both runs. They run before `cunit-net-slaac6`, which reloads the stack; with #1977 in, that reload no longer crashes.

**End to end:** my wider IPv6 harness (57 checks, not part of this PR) includes two cases that reload the stack: an interface removed and added back, and an address deleted before a reload. It passes all checks on both master and this branch.

**Additional validation:** each commit builds `workbench-network-stacks-arostcp`; `test-socket-yes-cunit` builds; `git diff --check` is clean. Only hosted x86-64 was built and run.

## Notes

- **Not covered here:**
  - An address that SLAAC made and a program then deletes with `SIOCDIFADDR_IN6` still leaves its prefix marked `ndpr_autoconf`, so it comes back only when the prefix expires.
  - `nd6_prefix_lookup()` does not look at the interface, so the same prefix heard on two interfaces is one entry.
