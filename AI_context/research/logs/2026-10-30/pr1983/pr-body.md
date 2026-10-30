## Scope

`ip6_output()` never delivers a datagram larger than the link MTU. Fragmentation goes wrong in three ways:

- **Only the first fragment is sent.** The loop works out each fragment's length and its M flag from `m->m_pkthdr.len`, which never shrinks; only the offset advances. On the second fragment, `m_copy()` is asked for bytes past the end and returns NULL, and the datagram is dropped with `ENOBUFS`.
- **The M flag is in the wrong byte order.** `IP6F_MORE_FRAG` is defined in network order (0x0100 on a little-endian machine), but it is OR'd into the offset before `htons()`. On x86-64 the first fragment goes out as "offset 256, last fragment". Big-endian machines are not affected.
- **Fragmenting a group datagram dereferences NULL.** The fragments are handed to `if_output()` with `rt->rt_flags` read unconditionally, and a group datagram has no route. The unfragmented path already checks `rt`.

So no large UDP datagram arrives. Neither does a full-sized TCP segment over IPv6, which today exceeds the MTU on every full send (the IPv6 MSS is a separate change). I found this with a TCP-over-the-wire bench against a Linux peer on the tap: the handshake completes, every data segment leaves as one malformed fragment, and the transfer never progresses.

Commits:

1. **Test.** `cunit-net-frag6`, see below.
2. **Fix.** Each fragment is worked out from what is left after its offset. `IP6F_MORE_FRAG` is set after the offset is converted. `rt` is checked before use, as on the unfragmented path. Readme §10 describes the fragments.

There is no API, ABI or structure change.

## Reproduction and validation

Hosted linux-x86_64, with `tap.device` attached to a host tap. The series is on master `337fa9c9ec`.

`cunit-net-frag6 eth0` sends UDP datagrams to `ff02::4d54:66` and reads its own output with BPF. Results are the same in both CUnit runs (basic and automated):

| Test | master | this branch |
|---|---|---|
| a 3000-byte datagram leaves as all its fragments, none above the MTU | **traps** (NULL `rt`) | passed |
| fragment offsets follow each other, M on all but the last | (not reached) | passed |
| the fragments reassemble to the datagram sent | (not reached) | passed |
| a datagram that fits the MTU is not fragmented | (not reached) | passed |

**Unicast, with a Linux peer:** AROS sends 2 MB over TCP/IPv6 to the host's link-local address. Today each segment is 1480 bytes plus the IPv6 header, which exceeds the 1500-byte MTU.

| | master | this branch |
|---|---|---|
| on the wire | one fragment per segment, `frag (id:256\|1448)` | two fragments per segment, `0\|1448` with M and `1448\|32` |
| host received | 0 bytes; AROS retransmits forever | 2,000,000 bytes in 0.28 s |

The cunit socket, tcp, udp, inet6, mld6, route6, cmsg, addr6, srcaddr6, mcast6, raw6, sendto6, scope6 and rio6 suites pass unchanged on this branch, in both runs. My wider IPv6 harness (67 checks with a peer on the host, not part of this PR) passes all checks.

**Additional validation:** each commit builds `workbench-network-stacks-arostcp`; `test-socket-yes-cunit` builds; `git diff --check` is clean. Only hosted x86-64 was built and run.

## Notes

- **Not covered here:**
  - **The TCP MSS over IPv6.** It is computed for IPv4: `tcp_mss()` looks the route up by `inp_faddr`, which is zero for an IPv6 connection, so it falls back to 1460 and ignores the peer's MSS. `tcp_mssopt()` subtracts 40 bytes of headers rather than 60. I will send that next; with it, TCP stops needing fragmentation.
  - **Extension headers in the unfragmentable part.** Only the fixed IPv6 header is copied into each fragment. Hop-by-Hop or Routing headers would have to be repeated in every fragment as well. Nothing the stack fragments today carries them.
  - **Fragment identification.** It is a plain counter; RFC 7739 recommends unpredictable values.
- **Overlap.** #1979 adds a test on the same mmakefile line, so whichever lands later needs a one-line rebase.
