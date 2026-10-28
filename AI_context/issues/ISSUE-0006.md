---
id: ISSUE-0006
title: "Spike M1: camada de plataforma AROS mínima para o SDK"
status: backlog
priority: high
type: spike
owner: jaime
milestone: M1
area: system
created_at: 2026-10-28
updated_at: 2026-10-28
tags: [spike, platform, gn]
blockers: []
depends_on: [ISSUE-0002, ISSUE-0003]
upstream_refs: [connectedhomeip src/system/SystemLayerImplSelect.cpp, connectedhomeip src/platform/{Linux,NuttX,Zephyr,fake}, connectedhomeip src/inet/UDPEndPointImplSockets.cpp]
related_files: []
---

# Por quê

M1 = build reprodutível de um subconjunto mínimo do SDK no AROS, sem patches ocultos.

# O quê

- Escolher o molde de plataforma (`fake`/`Linux`/`NuttX`) e listar os hooks: `PlatformManagerImpl`, `ConfigurationManagerImpl`, `KeyValueStoreManagerImpl`, `ConnectivityManagerImpl` (stub), `Logging`, `Entropy`, mutex/locks.
- Event loop: `SystemLayerImplSelect` sobre `select()`. No AROS, sockets são da bsdsocket.library: `WaitSelect()`, `CloseSocket()`, `IoctlSocket()`, errno via `SocketBaseTags`. Precisa de uma camada de adaptação (ver `research/2026-10-28-hosted-tests.md` §Outras lacunas).
- Interfaces: sem `getifaddrs()` exportada; usar `SIOCGLIFADDR`/`SIOCGIFCONF` + `if_nametoindex` (miami.library).
- GN: verificar se aceita uma toolchain custom apontando para `x86_64-aros-g++` 10.5 (vindo da ISSUE-0002).
- Integrar com GN via toolchain custom, ou gerar a lista de fontes e compilar com mmake/make.
- Alvo do spike: `src/lib/core`, `src/system`, `src/inet` (UDP), `src/crypto`, mais um binário de teste que envie e receba UDP IPv6.

Fica de fora: commissioning, clusters, BLE, Thread, Wi-Fi provisioning.

# Passos de validação

- [ ] Inventário de dependências/licenças da revisão fixada (submódulos realmente necessários) → `research/`
- [ ] Tabela hook × disposição (port local / genérico upstream / stub) → `research/`
- [ ] Build do subconjunto → log reprodutível com script
- [ ] Binário de teste roda no AROS e troca UDP IPv6 com o host → log

# Critério de sucesso / falha

- Sucesso se: o subconjunto compila com script versionado e o binário roda.
- Falha se: houver dependência estrutural (ex.: threads POSIX completas) sem caminho viável; documentar como bloqueio.

# Log

- 2026-10-28: criada.
