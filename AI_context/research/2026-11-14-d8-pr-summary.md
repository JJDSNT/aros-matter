# D8 — PR summary (draft; not published)

Draft of the upstream PR body for `review/mdnsd-canonical-links` (26 commits on
#2218's head `283464c0b6`). **Not pushed, not opened: waiting for the user's
approval.** No Claude attribution upstream.

---

## mdnsd: native DNS-SD on dnssd.library; bonami.library retired

mdnsd becomes a dual-stack mDNS/DNS-SD responder and querier with one record
cache, served to programs through an AROS-owned library, `dnssd.library`.
As #2123's review asked, the dual-stack API no longer extends amigazen's
Bonami ABI under its name: the in-tree clients (the mdns tools and
netmidid) move to `dnssd.library`, and `bonami.library` with its port and
headers leaves the tree.

### Architecture

- **Links.** mdnsd takes complete link snapshots from AROSTCP (addresses of
  both families per interface, flags, scope) and treats them as the
  authority; one IPv4 and one IPv6 UDP 5353 socket per usable link;
  `IP_PKTINFO`/`IPV6_PKTINFO` name the link a datagram came by and each
  answer leaves by that link, from its address.
- **Registrations** are kept as DNS has them (`dnssd_reg.h`): wire names,
  subtype labels, the names their records carry built once. A client may
  register for another host, IPv4 and IPv6. A time to live per registration
  (`DNSSD_TimeToLive`, 1–4500 s).
- **One cache** (`mdns_cache.c`): every answer heard, names as wire labels,
  within a budget (24 KB on the 68k, 128 KB elsewhere). Operations watch it;
  questions follow RFC 6762's schedule with known answers, those due on a
  link go in one query, watched records are refreshed at 80–95 % of their
  life, unwatched records are evicted first. The host's own announced
  records are reflected into it (marked local; they end only by goodbye, or
  when the host loses the name).
- **dnssd.library**: sessions with a message port of the caller's; each
  request is an operation; events are read one at a time into the caller's
  buffer; no daemon pointer reaches a program; every request travels in a
  sized envelope checked before mdnsd reads it. Browse, resolve (until
  cancelled with `DNSSD_Timeout` 0), address lookup, record query,
  register/update, cancel. A session goes with its task (`TNA_REMOVED`).
- **Resolve reporting**: what changed (port, priority, weight, host, TXT, an
  address) is reported once per mdnsd turn, never without TXT; after the
  first report, an empty address set is reported too.
- **Host name**: changes in one place (`mdnsHostSetName()`), which drops the
  records the host said under the old name.
- **Tools** (`dnssd`, `Nearby`, `Share`, `Handshake`) on `dnssd.library`,
  with AutoDocs; IPv4 and IPv6 addresses, binary TXT; a browse follows 16
  instances (resolve until cancelled) and resolves 4 more at a time
  (1 + 16 + 4 = 21 of the 24 operations a 68k session has).
- **netmidid**: discovery on `dnssd.library`, event-driven (the session's
  signal is in its wait mask), every address of a peer, its own name taken
  from REGISTERED, mdnsd's restart detected; 2 + 2 + 16 = 20 operations.

### Bonami attribution

mdnsd and the tools are derived from amigazen Bonami (BSD-2-Clause). Every
file that keeps Bonami code keeps amigazen's copyright notice (`mdns_dns.c`,
`mdns_dns.h`, `mdns_host.c`, `mdns_net.c`, `mdns_packet.c`, `mdns_reg.c`,
`mdnsd.c`, `mdnsd.h`, `tools/`); `LICENSE` names both copyright holders; the
README has a Credits section saying what derives from Bonami and what is
AROS's own (`dnssd.library`, the cache, the link inventory, the session
protocol). netmidid is AROS's own work. `bonami.library` itself, amigazen's
interface, is no longer part of AROS; programs that use it take it from the
Bonami project.

### Tests (aros-matter)

Hosted AROS (x86_64) and AROS m68k on an emulated A3000 (A2065), against
Avahi on the Linux host:

| Test | Hosted | m68k |
|---|---|---|
| dnssdtest (library API, 68 cases) | 68/68 | 68/68 |
| tools.sh (every tool mode; TTL, IPv6 proxy, binary TXT, UPDATE, own name) | pass | pass |
| netmidid.sh (conflict, rename, IPv4+IPv6 peer, goodbye, new port, TTL) | pass | pass |
| follow.sh (20 instances followed/resolved; address add/remove/replace) | pass | pass |
| dnssd_gone (session ends with its task) | pass | — |
| interop with Avahi, two links | pass | pass |

Host fixtures under ASan/UBSan: `dnssd_server_rfc.c` 29/29 (cache,
operations, own-host invalidation paths), responder 44/44.
Codacy pre-check (cppcheck 2.22 + flawfinder): clean apart from
`unknownMacro` on the AROS library macros.

### Footprint (m68k)

| | before | after |
|---|---|---|
| mdnsd text | 60,484 B | 48,480 B |
| mdnsd file | 87,540 B | 71,432 B |
| bonami.library | present | removed |
| dnssd.library | — | 20,072 B |

Hosted mdnsd (x86_64): 166,824 → 134,888 B.

### Dependencies

- #2218 (IP_PKTINFO on IPv4 datagram sockets, IPv4 conflict detection,
  per-link IPv6 neighbour cache): this branch sits on its head and uses
  `IP_PKTINFO`. To be rebased onto master once #2218 merges.

### Known follow-ups (outside this PR)

- B42: a runtime hostname change made without a reconfiguration or an
  interface change is not noticed by mdnsd (since the first AROS mdnsd,
  `db1826863d`). To be solved with AROSTCP/resolver.atcp, preferably with a
  dedicated hostname-change notification.
- A canonical provider for the host's own records, as a separate
  investigation (memory, duplicated paths, code size).
- netmidid transports open IPv4 sockets; a peer with IPv6 addresses only is
  reported but not reached.

---

## Internal notes (not for the PR body)

- Commit 75b8c03aed (own host in cache)'s message says the server fixture's own-host and renamed
  cases fail before it and pass on it. With the fixture as it is now, the
  commit before does not build it (a later case calls `mdnsHostSetName()`,
  which that commit introduces), and `expire-a` fails until 1dcdbdc3cb
  (empty address set reported). The fixture follows the tip.
- Validation of the cleaned history (2026-11-14): hosted dnssdtest 68/68,
  tools/netmidid/follow 0 failed, dnssd_gone 8/8 (both runs), interop
  TWO=1 (`tests/mdns/out/*-cl-025632`, `*-cl2-053042`); fixtures 29/29 and
  44/44 on the tip; precodacy 283464c0b6..HEAD only `unknownMacro`.
- README: two sentences added after the review (own records in the cache,
  folded into 75b8c03aed; tools follow what they browse, folded into the
  Bonami-removal commit).
