# AROSTCP IPv4/IPv6 receive-path parity audit

**Status:** Pending audit — not a confirmed defect list  
**Priority:** P1 (follow-up to mDNS UDP dependency)  
**Owner:** Generic AROSTCP work, tracked by aros-matter; not an mDNSd workaround.

## Context

[AROS PR #2105](https://github.com/aros-development-team/AROS/pull/2105) addresses the IPv4 received-TTL ancillary-data need in the **UDP** path for mDNS. It must **not** be interpreted as closing all IPv4 receive-metadata or IPv4/IPv6 parity gaps. Verify the PR's current upstream status and exact diff before marking the UDP item complete.

The objective is a protocol-aware audit of remaining IPv4 receive-side capabilities, using IPv6 and existing BSD socket conventions as references, without assuming every IPv6 option should have an identical IPv4 counterpart.

## Audit matrix (to be populated with evidence)

| Area | Questions | Current status |
| --- | --- | --- |
| UDP IPv4 | Does #2105 provide the required received TTL, option handling, ancillary ABI, truncation and tests? | Implemented in PR; merge/status to verify |
| TCP IPv4 | What received IP metadata is meaningful/exposed for streams? Are there actual API gaps? Do **not** assume per-datagram IP_RECVTTL applies to TCP. | Not audited |
| Raw IPv4 | Can callers access received IP header/TTL as expected? Are any ancillary options missing or inconsistent? | Not audited |
| ICMP/diagnostics | Can ping/traceroute-like consumers obtain required received TTL and interface metadata? Distinguish raw socket header access from ancillary APIs. | Not audited |
| Other IPv4 ancillary metadata | Compare received TOS, packet/interface info, destination address, timestamps and control-message behavior with supported IPv6 facilities and documented ABI. | Not audited |
| Lifecycle and interfaces | Compare IPv4 and IPv6 address-change notification, flags, interface selection and binding where relevant. | Not audited |

## Method

1. Reconcile against current AROS upstream and merged/open PRs, especially #2105; do not duplicate implemented work.
2. Inspect socket options and receive paths for UDP, TCP, raw IP and ICMP, including `setsockopt`, `getsockopt`, `recvmsg`, `cmsghdr` and relevant headers.
3. Classify each difference: **confirmed missing generic feature**, **intentional protocol difference**, **already supported**, or **requires investigation**.
4. For each confirmed gap, record exact files/functions, expected contract, ABI layout/payload width/alignment, compatibility risk, consumers, and reproducible tests.
5. Propose focused, technically coherent upstream PR groups only for verified gaps; avoid arbitrary one-protocol/one-PR splitting.
6. Build/link relevant AROS targets and distinguish unit/host fixtures, cross-build, hosted runtime and real-network evidence.
7. Follow upstream AROSTCP revision-bump conventions for functional changes.

## Scope boundaries

- Do not extend the mDNSd/Bonami PR to repair generic socket behavior.
- Do not promise identical semantics for IPv4 and IPv6 where protocols or BSD APIs differ.
- Do not assume TCP supports packet-oriented ancillary TTL semantics.
- No implementation or upstream PR is authorized by this note alone.

## Completion criteria

A documented IPv4/IPv6 receive-capability matrix, with source references, test evidence, explicit remaining gaps and proposed PR grouping. Mark the audit complete only after upstream reconciliation.
