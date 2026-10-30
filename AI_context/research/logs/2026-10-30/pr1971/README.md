# AROS #1971: G14, raw IPv6 sockets (RFC 3542 section 3)

Branch `review/arostcp-ipv6-raw-options` on master `343de5cddf`; commits `29d35bfb5b` (`ICMP6_FILTER`), `f0784c56f7` (test), `29da733b27` (raw sockets on an `inpcb`, `netinet6/raw_ip6.c`), `b5a470cf64` (every ICMPv6 message to the raw sockets).

Hosted linux-x86_64 with the tap `aros0`. Every log has both CUnit runs (basic and automated). The basic report lists only one failed assertion per test.

| Dir | Stack | raw6 |
|---|---|---|
| `master-1950/` | master | 8/8 fail; the other suites (socket, tcp, udp, inet6, mld6, route6, cmsg, addr6) pass |
| `g14-a/` | through commit 3 | 2/8 fail (Echo Request never reaches the socket: ECHO_REQUEST_AND_REPLY, RECVHOPLIMIT) |
| `g14/` | the branch | 8/8 pass; the other suites unchanged |

`*.tcpdump`: Echo Requests to `ff02::1` captured on the host tap (both CUnit runs).
- master: seq 5 and 6 with hop limit 64 from `::`; seq 7 (`sendmsg()` with ancillary data) never sent.
- branch: seq 5 hop limit 255, seq 6 hop limit 1, seq 7 hop limit 255, all from the link-local, checksums correct.

A probe on master showed the protocol-253 socket receiving 44 bytes: the 40-byte IPv6 header (`60 00 00 00 00 04 fd 40 …`) and `RAW6`.

`../merges/`: #1945 and #1970 after merging master `343de5cddf` (only the mmakefile test line conflicted); every suite passes in both runs.
