## Scope

Deleting an IPv6 address leaves routes pointing at the freed address. Routes hold no reference on their `rt_ifa`. `in6_purgeaddr()` removes the address's prefix route (`in6_ifscrub()`) and then frees the `in6_ifaddr`, but two kinds of route are left pointing at it:

- the host routes cloned from that prefix route for neighbour resolution;
- any other route that resolved through the address.

Deleting one of those routes later calls `ifa->ifa_rtrequest()` through freed memory. Once something else has reused that memory, the call jumps through garbage.

An in-place reload deletes every route of the interface (`rt_purgeif()` from `sana_if_deconfigure()`). So a reload after an address had been added, used and deleted can take the stack down. Whether it does depends on what has reused the memory in between, which is why this looks intermittent.

I hit it running the socket cunit suites in one boot and then reloading the stack. Under gdb the fault is in `rtrequest()`'s `RTM_DELETE` path, reached through `rt_purgeif()` ← `sana_if_deconfigure()` ← `sana_reconfig_teardown()` ← `net_reload()`. The trigger needs three things in sequence: `cunit-net-srcaddr6` adds, uses and deletes `fd00:4d54:61::1`; a later suite reuses the freed memory; and then the reload runs. In one run the fault was a call to address `0xffffffffffffffff`.

Commits:

1. **Test.** `cunit-net-addr6` gains a test: add `fd00:4d54:52::1/64`, send a datagram to `fd00:4d54:52::2` so that a host route is cloned from the prefix route, delete the address, and check with `RTM_GET` that no route to `fd00:4d54:52::2` is left. Unlike the crash, the leftover route shows every time.
2. **Fix.** `in6_purgeaddr()` deletes every route that uses the address with `rt_purgeifa()` before freeing it, as `in_control()` already does for an IPv4 address (`netinet/in.c`).

There is no API, ABI or structure change.

## Reproduction and validation

Hosted linux-x86_64, with `tap.device` attached to a host tap. The series is on master `1fef6c415e`.

`cunit-net-addr6 eth0`, the same in both CUnit runs (basic and automated):

| Test | master | this branch |
|---|---|---|
| deleting an address removes its prefix route | passed | passed |
| deleting an address removes the routes cloned from it | **FAILED** (route to `fd00:4d54:52::2` left) | passed |
| a new address goes through DAD | passed | passed |
| deleting an address stops its DAD | passed | passed |
| adding an address solicits no routers | passed | passed |

**The crash.** I ran the socket, tcp, udp, inet6, mld6, route6, cmsg, addr6, srcaddr6, mcast6, raw6, sendto6, scope6 and rio6 suites in one boot, followed by a test that reloads the stack through `<bsdsocket/netcontrol.h>`.

| | master | this branch |
|---|---|---|
| traps during the reload | repeated (`Trap signal 11`) | none |
| the boot finishes | no | yes |

Narrowing the sequence down on master, the reload crashes only when `cunit-net-srcaddr6` and `cunit-net-rio6` have run with at least one other suite between them; either one alone, or the two alone, do not.

All the suites above pass unchanged on this branch, in both runs. My wider IPv6 harness (57 checks with a peer on the host, not part of this PR) passes all checks.

**Additional validation:** each commit builds `workbench-network-stacks-arostcp`; `test-socket-yes-cunit` builds; `git diff --check` is clean. Only hosted x86-64 was built and run.

## Notes

- **No reference counting.** `struct ifaddr` has an `ifa_refcnt` that nothing uses. With it, a route could hold its address alive the way the BSDs do. That is a larger change than mirroring what IPv4 already does here.
