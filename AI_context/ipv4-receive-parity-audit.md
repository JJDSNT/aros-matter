# AROSTCP IPv4/IPv6 receive-path parity audit

**Status:** Pending audit — not a confirmed defect list  
**Priority:** P2 (targeted capability audit; no confirmed blocker beyond the separate mDNS integration)  
**Owner:** Generic AROSTCP work, tracked by aros-matter; not an mDNSd workaround.

## Context

[AROS PR #2105](https://github.com/aros-development-team/AROS/pull/2105) addresses the IPv4 received-TTL ancillary-data need in the **UDP** path for mDNS. It must **not** be interpreted as closing all IPv4 receive-metadata or IPv4/IPv6 parity gaps. Verify the PR's current upstream status and exact diff before marking the UDP item complete.

The objective is a protocol-aware audit of remaining IPv4 receive-side capabilities, using IPv6 and existing BSD socket conventions as references, without assuming every IPv6 option should have an identical IPv4 counterpart.

## Established facts and audit matrix

The #2105 PR description explicitly specifies FreeBSD-compatible `IP_RECVTTL = 65`, a one-byte `IPPROTO_IP` / `IP_RECVTTL` control-message payload, `CMSG_LEN`/`CMSG_SPACE` handling, `MSG_CTRUNC`, and hosted UDP tests including fragmented and multicast datagrams. These are **PR-author claims**, not independently reproduced by this document. Upstream merge status and diff remain to be checked.

Crucially, the PR explicitly scopes the feature to **UDP**, as existing `IP_RECVTOS` does. TCP is a byte stream and does **not** have a per-message received TTL contract. Raw IPv4 sockets reportedly have no ancillary-data delivery yet; this is a **capability to assess**, not proof of a defect.

| Area | Questions | Current status |

| Area | Questions | Current status |
| --- | --- | --- |
| UDP IPv4 | Verify #2105 option, received TTL, one-byte FreeBSD ABI, `MSG_CTRUNC`, fragments, multicast and upstream merge | Implemented/tested per PR description; independent verification pending |
| TCP IPv4 | Audit only meaningful stream-level socket capabilities; do not require per-datagram TTL ancillary metadata | **Intentional protocol difference**, not a missing `IP_RECVTTL` feature |
| Raw IPv4 | Verify IP-header/TTL access and whether optional ancillary metadata is justified by real consumers | No ancillary support per #2105 description; impact not audited |
| ICMP/diagnostics | Can ping/traceroute-like consumers obtain required received TTL and interface metadata? Distinguish raw socket header access from ancillary APIs. | Not audited |
| Other IPv4 ancillary metadata | Compare received TOS, packet/interface info, destination address, timestamps and control-message behavior with supported IPv6 facilities and documented ABI. | Not audited |
| Lifecycle and interfaces | Compare IPv4 and IPv6 address-change notification, flags, interface selection and binding where relevant. | Not audited |

## Method

1. Reconcile against current AROS upstream and merged/open PRs, especially #2105; do not duplicate implemented work.
2. Inspect socket options and receive paths for UDP, TCP, raw IP and ICMP **only where semantics apply**, including `setsockopt`, `getsockopt`, `recvmsg`, `cmsghdr` and relevant headers.
3. Treat TCP's absence of per-datagram received TTL as expected, **not a parity gap**. Do not propose TCP `IP_RECVTTL` without a separately demonstrated meaningful API contract. Classify each remaining difference: **confirmed missing generic feature**, **intentional protocol difference**, **already supported**, or **requires investigation**.
4. For each confirmed gap, record exact files/functions, expected contract, ABI layout/payload width/alignment, compatibility risk, consumers, and reproducible tests.
5. Propose focused, technically coherent upstream PR groups only for verified gaps; avoid arbitrary one-protocol/one-PR splitting.
6. Build/link relevant AROS targets and distinguish unit/host fixtures, cross-build, hosted runtime and real-network evidence.
7. Follow upstream AROSTCP revision-bump conventions for functional changes.

## Scope boundaries

- Do not extend the mDNSd/Bonami PR to repair generic socket behavior.
- Do not promise identical semantics for IPv4 and IPv6 where protocols or BSD APIs differ.
- Do not treat TCP's lack of per-datagram ancillary TTL as a bug; it is an intentional stream/datagram distinction.
- Raw IPv4 ancillary support is a research question, not automatically required when IP headers already provide the needed information.
- The mDNSd TTL=255 validation is separate application work and must not be conflated with generic AROSTCP parity.
- No implementation or upstream PR is authorized by this note alone.

## Completion criteria

A documented IPv4/IPv6 receive-capability matrix, with source references, test evidence, explicit remaining gaps and proposed PR grouping. Mark the audit complete only after upstream reconciliation.
