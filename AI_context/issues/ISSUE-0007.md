---
id: ISSUE-0007
title: "Bancada de testes: acessório e controlador de referência"
status: doing
priority: high
type: infra
owner: jaime
milestone: M0
area: testbed
created_at: 2026-10-28
updated_at: 2026-10-28
tags: [testbed, chip-tool, interop]
blockers: []
depends_on: []
upstream_refs: [connectedhomeip examples/all-clusters-app, connectedhomeip examples/lighting-app, connectedhomeip examples/chip-tool]
related_files: []
---

# Por quê

Todo marco (M0 a M5) exige teste contra uma implementação interoperável conhecida. Sem bancada, não há evidência.

# O quê

- Acessório de referência: `lighting-app` ou `all-clusters-app` (Linux) do SDK, na mesma revisão fixada.
- Controlador de referência: `chip-tool`, para comparar com o `matterctl` (capturas lado a lado).
- Rede: um segmento L2 com IPv6 link-local e multicast entre o host Linux e o AROS (bridge/tap para QEMU ou AROS hosted).
- Opcional: um dispositivo Matter comercial em Wi-Fi/Ethernet para teste de interoperabilidade.

Atenção: o WSL2 em NAT não repassa multicast IPv6 de forma confiável; prefira o modo de rede `mirrored` ou uma VM/host Linux dedicado.

# Passos de validação

- [ ] Compilar `chip-tool` e `lighting-app` na revisão fixada → binários
- [ ] `chip-tool pairing onnetwork` + `onoff toggle` entre os dois no Linux → log (baseline)
- [x] Segmento hosted: tap isolada `aros0` (`tools/tap-up.sh`) + `tools/hosted-run.sh` (`AROS_TAP_IP`); o AROS ganha link-local e troca IPv6 com o host
- [ ] AROS no mesmo segmento vê o anúncio `_matterc._udp` (tcpdump no host + `dnssd` no AROS) → captura

# Critério de sucesso / falha

- Sucesso se: baseline Linux↔Linux funcionando e o AROS recebendo multicast IPv6 do segmento.

# Log

- 2026-10-28: criada.
- 2026-10-28: bancada hosted+tap funcionando (`tools/`).
