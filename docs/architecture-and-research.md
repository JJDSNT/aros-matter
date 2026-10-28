# Architecture, upstream audit and implementation research

Status: research plan; implementation and platform compatibility are **not yet validated**.

## 1. Scope and first vertical slice

Build an AROS Matter **controller**, not an accessory. The first demonstration should operate over an existing IPv6-capable Ethernet/Wi-Fi network: discover a commissioned-capable device, commission it where supported, establish an operational session, read a standard attribute, and issue an OnOff command. An existing Thread border router may expose Thread devices on the IP network, but native Thread radio and BLE commissioning are separate future work.

Do not claim that IPv6, multicast, secure credential storage, or the full Matter SDK currently work on AROS without tests.

## 2. Separation of concerns

- **AROS upstream**: portable socket/IPv6 fixes, multicast behavior, entropy, crypto, DNS-SD improvements, timing and storage primitives. These should not depend on Matter or Prism.
- **aros-matter**: SDK port/adapters, commissioning and fabric lifecycle, controller application, Matter-specific service discovery.
- **aros-prism**: displays, Open Screen and other presentation protocols. No direct dependency on Matter.
- **Shared security**: Matter requires SPAKE2+ for PASE and certificate-based CASE. SPAKE2 and SPAKE2+ are distinct. QUIC is not a Matter prerequisite.

Avoid creating a generic `spake2.library` or `quic.library` prematurely; first determine the API and concrete consumers.

## 3. Verified AROS upstream starting points

The AROS tree includes `workbench/libs/mbedtls/mmakefile.src` fetching **mbedTLS 3.6.7** and building crypto, X.509 and TLS libraries. Its `mbedtls_aros_config.h` enables TLS 1.2/1.3 client functionality, PSA crypto and elliptic curves, but is not proof of SPAKE2+ support. The network adapter `mbedtls_net_aros.c` integrates with `bsdsocket.library`; the entropy adapter `mbedtls_entropy_aros.c` obtains randomness from `entropy.resource`.

The bundled PSA PAKE source in mbedTLS 3.6.7 documents EC J-PAKE. **Do not confuse generic PSA PAKE or EC J-PAKE with Matter SPAKE2+.** Check the SDK's actual cryptographic backend and version compatibility before selecting an implementation.

References:
- https://github.com/aros-development-team/AROS/blob/master/workbench/libs/mbedtls/mmakefile.src
- https://github.com/aros-development-team/AROS/blob/master/workbench/libs/mbedtls/mbedtls_aros_config.h
- https://github.com/aros-development-team/AROS/blob/master/workbench/libs/mbedtls/mbedtls_net_aros.c
- https://github.com/aros-development-team/AROS/blob/master/workbench/libs/mbedtls/mbedtls_entropy_aros.c
- https://github.com/Mbed-TLS/mbedtls/blob/mbedtls-3.6.7/library/psa_crypto_pake.c

## 4. Audit matrix (all items require evidence)

| Capability | Questions to answer | Proof |
| --- | --- | --- |
| IPv6 | AF_INET6, bind/connect, scope IDs, interface enumeration, dual stack? | Client/server IPv6 tests |
| UDP/multicast | IPv6 multicast join/leave, receive, interface selection, packet sizes? | mDNS multicast send/receive |
| DNS-SD/Bonami | PTR browse, SRV/TXT/AAAA resolve, subtype queries, service changes? | Discover real Matter advertisements |
| Entropy | Strong entropy available on each target; failures propagate? | Crypto initialization and negative tests |
| SPAKE2+ | Which connectedhomeip implementation/backend builds on AROS? | SDK vectors and cross-platform PASE |
| CASE | Certificate validation, fabric identity, operational discovery? | Operational secure session |
| Persistence | Atomic credential storage, permissions, failure recovery? | Restart and fabric retention |
| Timers/events | Monotonic timers, nonblocking sockets, cancellation, task ownership? | Stress and timeout tests |
| Build portability | Supported toolchains/architectures, endianness, memory footprint? | Reproducible builds |

A successful DNS-SD browse alone does not demonstrate Matter support. Matter requires secure commissioning, operational discovery, sessions and application clusters.

## 5. SDK feasibility spike

Inspect the official https://github.com/project-chip/connectedhomeip SDK, especially its platform abstraction, C++ toolchain requirements, GN/build integration, memory allocation, persistent storage, logging, networking, cryptography and event loop. Do not assume the entire SDK is portable simply because its cryptography supports mbedTLS.

Deliver:
1. Exact upstream SDK revision and license/dependency inventory.
2. Minimal build target and compiler/toolchain assessment for AROS.
3. Required platform hooks with a port-vs-upstream disposition.
4. Crypto backend selection based on working SPAKE2+ and CASE, not just TLS.
5. Test strategy against a known interoperable Matter implementation.

## 6. Milestones and acceptance criteria

**M0 — Capability audit:** every matrix row has a tested result, limitation, or explicit blocker.

**M1 — Build spike:** a reproducible AROS build of a minimal SDK subset; no vendor patches hidden in the build.

**M2 — Discovery:** `matterctl discover` reports authentic commissionable or operational advertisements with service data and IPv6 address; no invented devices.

**M3 — PASE commissioning:** SPAKE2+ succeeds with a test accessory; invalid passcodes fail; secrets are not logged.

**M4 — CASE + read:** restart-safe credentials, authenticated operational session and attribute read.

**M5 — Control:** `matterctl onoff` interacts with a test device; failures and timeouts are handled.

**M6 — Upstream:** separate focused AROS pull requests for generic improvements, without Matter-only coupling.

## 7. Security and quality gates

- Never implement SPAKE2+ arithmetic or certificate verification from scratch.
- Verify random number quality and cryptographic failure paths.
- Do not store setup codes, private keys or fabric secrets in logs.
- Treat certificate stores and persistent credentials as security-sensitive.
- Validate interoperability, negative pairing cases and restart behavior.
- Keep Thread and BLE commissioning explicitly out of the first milestone unless platform audits justify expanding scope.

## 8. Agent handoff

Start with M0. Inspect actual AROS upstream source and the pinned connectedhomeip revision; write a concise evidence-backed gap report. Do not begin a broad SDK port or design new AROS libraries until the gaps, crypto backend and smallest compilable target are identified. Keep research and implementation commits separately reviewable.
