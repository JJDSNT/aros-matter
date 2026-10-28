# AROSTCP IPv6 test suite (S0)

Conformance cases for the AROSTCP IPv6 work ([ISSUE-0008](../../AI_context/issues/ISSUE-0008.md), [desenho](../../AI_context/research/arostcp-ipv6-design.md)). The suite runs a hosted AROS (linux-x86_64) attached to an isolated tap, `aros0`, with the Linux host as the peer on the link.

## Running

```sh
tests/ipv6/run.py                                   # default image: ~/aros-midihub/.../AROS
tests/ipv6/run.py --image ~/aros-build-ipv6-hosted/bin/linux-x86_64/AROS
tests/ipv6/run.py link.recv-joined mld.close-leaves # only some cases
```

The suite needs sudo, to create the tap (`tools/tap-up.sh`) and to run `tcpdump`. Results go to `tests/ipv6/out/<timestamp>/`, which git ignores:
- `report.txt`: PASS/FAIL for each check
- `boot/out/aros.log`: raw output of `ipv6test`
- `mld.tcpdump`: the capture
- `host.json`: what the host received, and the MLD events parsed per group

The cross-compiler comes from `AROS_CROSS` (default: the `x86_64-aros-gcc` in the aros-midihub build).

## What runs where

- `ipv6test.c` runs on AROS. For each check it prints `ok`/`not ok`, plus `host <case> <expectation>` lines for the things only the host can see.
- `run.py` runs on the host. While AROS runs, it:
  - multicasts `H:<seq>` to `ff02::fb:5353` twice a second;
  - records what AROS sends to that group;
  - captures `ip6 and not udp` with tcpdump, so MLD messages arrive with their Hop-by-Hop header.

  Afterwards it checks the `host` expectations against what it recorded.

## Cases

| Case | Checks | Reference |
|---|---|---|
| `local.unicast` | UDP over `::1` with `WaitSelect` | RFC 3493 §3 |
| `local.join-semantics` | join, join again → `EADDRINUSE`, leave, leave again → `EADDRNOTAVAIL` | RFC 3493 §5.2 |
| `local.reuseport-bind` | two sockets on `[::]:5353` | BSD `SO_REUSEPORT` |
| `link.linklocal` | the interface has an autoconfigured `fe80::` | RFC 4862 §5.3 |
| `link.send-mcast-if` | `sendto(ff02::fb)` from `[::]:5353` after `IPV6_MULTICAST_IF`; host receives from port 5353 | Readme §6.6, RFC 3493 §5.2 |
| `link.send-scopeid` | same, with only `sin6_scope_id` on the destination | Readme §6.6, RFC 4007 §11 |
| `link.recv-joined` | a socket that joined `ff02::fb` receives the host's datagrams | RFC 3493 §5.2 |
| `link.recv-fanout` | two sockets on the port both receive | parity with IPv4 `udp_input()` |
| `link.recv-port-parity` | a socket on the port that joined nothing receives, because the host is a member | parity with IPv4 `udp_input()` |
| `link.pktinfo` | `IPV6_RECVPKTINFO` gives ifindex and `ff02::fb` | RFC 3542 §6 |
| `link.recv-scopeid` | a link-local source arrives with `sin6_scope_id` | RFC 4007 §11, RFC 3493 §3.3 |
| `link.mcast-loop` | with `IPV6_MULTICAST_LOOP` 1 a local member receives our datagram; with 0 it doesn't | RFC 3493 §5.2 |
| `mld.leave-explicit` | join/leave of `ff12::4d54:b`: wire shows report, then leave (control case) | RFC 2710 §4, RFC 3810 §6.1 |
| `mld.close-leaves` | join `ff12::4d54:a`, close, join again, close: report, leave, report, leave | mirror of IPv4 `95a501ff47` |
| `mld.addr-owned` | adding `fd00:4d54::12:3456` joins `ff02::1:ff12:3456`; deleting leaves it | RFC 4861 §7.2.1, RFC 4862 §5.4.2 |

## Known limits

- One link and one interface. The multi-interface zone cases (Readme §6.6) need a second tap and come with S6.
- The interface-removal case (in-place reload through `AROSTCP.ctrl`) is not automated yet.
- `link.mcast-loop` and the `send` cases also depend on S7 (source and interface selection).
