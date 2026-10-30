## Scope

`nd6_ra_input()` ignores two parts of RFC 4191:

- **The Default Router Preference in an RA.** The default route goes through whichever router is first on the list.
- **Route Information Options (type 24).** A host learns no route to a prefix that a router advertises beyond its own link.

The second is how a Thread border router announces the mesh's off-mesh-routable prefix to the hosts on its link. Without it, a Matter controller reaches the mesh only if the border router is also its default router.

Separately, the default router list outlives the interface it was heard on. `sana_if_deconfigure()` flushes the interface's routes, but the entries stay marked installed. When the router advertises again after a reload, `defrouter_select()` finds its entry installed and never puts the default route back. After `nd6_ifdetach()` the entries keep a pointer to the departed interface.

Commits:

1. **Test.** `cunit-net-rio6`, see below.
2. **RFC 4191.** Router Advertisements are processed as by a type C host:
   - **Default routers.** Each keeps its preference; the reserved value counts as medium. The default route goes through the most preferred router that has not expired, the one heard first among equals (§3.2).
   - **Route Information Options.** Each installs a route to its prefix through the advertising router, on the interface it was heard on. There is one entry per (prefix, router), each with its own lifetime and preference, at most `ND6_MAX_RTINFO`. The most preferred router for a prefix gets the route. Between prefix lengths, the routing table's longest match decides.
   - **Ignored options.** An option with the reserved preference, a length that does not fit its prefix length, or a link-local or multicast prefix is ignored (§2.3).
   - **`::/0`.** A `::/0` option overrides its RA's router lifetime and preference (§3.1).
   - **Lifetimes** are 32-bit, and `0xffffffff` never expires.
   - **One route helper.** All routes go through `nd6_router_route()`. It always passes the netmask, which is still `::/0` for the default route as today.
   - Readme §6.1 describes it.
3. **Interface down.** `nd6_purge_routers()` drops the interface's default routers and learned routes with their routing table entries, as FreeBSD's `nd6_purge()` does, and another interface's routers take over. `sana_if_deconfigure()` calls it before `rt_purgeif()`, and `nd6_ifdetach()` before the interface goes.

There is no API or ABI change; `struct nd_defrouter` and the new `struct nd_route_info` are private to the stack.

## Reproduction and validation

Hosted linux-x86_64, with `tap.device` attached to a host tap that sends no Router Advertisements. The series is on master `d50355747a`.

**How the test works.** The test sends its Router Advertisements from a raw ICMPv6 socket, with hop limit 255, to the interface's own link-local address. They loop back and are received on that interface as if a router on the link had sent them. None goes out on the link, where other hosts would take this one for a router. A second link-local address stands for a second router. Routes are read back with `RTM_GET`.

During a run, a capture on the host tap showed:

- **Sent by AROS:** the Router Solicitations and the DAD Neighbor Solicitations;
- **Router Advertisements:** none.

`cunit-net-rio6 eth0`, the same in both CUnit runs (basic and automated):

| Test | master | this branch |
|---|---|---|
| a Route Information Option installs its route (router lifetime 0) | **FAILED** | passed |
| lifetime 0 removes the route | **FAILED** | passed |
| the more preferred router wins, and the other takes over when it withdraws | **FAILED** | passed |
| the longest prefix is used | **FAILED** | passed |
| an invalid option is ignored | passed | passed |
| the more preferred default router wins | passed (see note) | passed |
| a `::/0` option overrides the router lifetime | **FAILED** | passed |

Note: master passes the default router preference case by chance. It puts a new router at the head of its list and takes the first, which in this test is the high-preference one.

The cunit socket, tcp, udp, inet6, mld6, route6, cmsg, addr6, srcaddr6, mcast6, raw6, sendto6 and scope6 suites pass unchanged on master and on this branch, in both runs.

**Additional validation:** each commit builds `workbench-network-stacks-arostcp`; `test-socket-yes-cunit` builds; `git diff --check` is clean. Only hosted x86-64 was built and run.

## Notes

- **Why the test relies on #1974.** The test's Router Advertisements must be received on the interface, not on `lo0`. Sending them to our own link-local address works only since #1974, which receives such packets on the interface that owns the address.
- **Not covered here:**
  - **Reachability-based router selection** (§3.2/3.5): an unreachable preferred router is not skipped yet.
  - **Redirects** are not touched.
