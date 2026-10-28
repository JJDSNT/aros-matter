# AROS Matter

Matter protocol support for [AROS](https://github.com/aros-development-team/AROS).

## Goal

Enable AROS to discover, commission, and control Matter devices through a portable implementation that reuses upstream AROS networking and cryptographic infrastructure.

**Initial target:** a minimal Matter controller for devices reachable over an existing IPv6-capable IP network (Ethernet/Wi-Fi). Thread border-router functionality, BLE commissioning, accessory/server mode, and certification are outside the first milestone.

## Architectural principles

- Keep Matter protocol code separate from [AROS Prism](https://github.com/JJDSNT/aros-prism). Both projects may benefit from generic AROS infrastructure, but neither should depend on the other.
- Prefer the official [connectedhomeip](https://github.com/project-chip/connectedhomeip) SDK and upstream-compatible adaptations over a new protocol implementation.
- Reuse AROS `bsdsocket.library`, `entropy.resource`, the existing mbedTLS port, and Bonami/DNS-SD wherever their capabilities satisfy Matter requirements.
- Contribute generic improvements to AROS upstream; keep Matter-specific integration in this repository until appropriate for upstream.
- Distinguish **SPAKE2+** (Matter commissioning) from **SPAKE2** (potentially used by other protocols). Do not assume they are interchangeable.
- Matter's operational transports are not QUIC. QUIC investigation belongs to shared networking research, not the Matter implementation dependency chain.
- Avoid writing custom cryptographic primitives. Verify implementation, licensing, interoperability, and platform security assumptions.

## Proposed milestones

1. **Platform capability audit:** IPv6, multicast, UDP, DNS-SD, entropy, timers, mbedTLS/PSA, persistent storage and event loop.
2. **SDK feasibility spike:** compile a minimal connectedhomeip subset with an AROS platform adaptation; document build and dependency gaps.
3. **Discovery:** browse and resolve Matter DNS-SD records, including IPv6 addresses and TXT metadata.
4. **Commissioning:** implement PASE/SPAKE2+ with audited SDK crypto and persist fabric credentials securely.
5. **Operational session:** CASE establishment and an authenticated attribute read.
6. **Useful controller:** `matterctl` discovery, pairing, inspection and a simple on/off command.
7. **Upstream extraction:** propose only generic AROS changes as focused patches.

See [docs/architecture-and-research.md](docs/architecture-and-research.md) for the technical research plan and validation criteria.

## Status

**Research / bootstrap.** No claim of functional Matter support is made yet.

Operational tracker (issues, findings, current state): [AI_context/](AI_context/current_state.md).

## References

- [Matter SDK (connectedhomeip)](https://github.com/project-chip/connectedhomeip)
- [AROS upstream](https://github.com/aros-development-team/AROS)
- [AROS Prism](https://github.com/JJDSNT/aros-prism)
