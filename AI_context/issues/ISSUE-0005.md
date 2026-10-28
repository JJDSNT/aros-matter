---
id: ISSUE-0005
title: "IPv6 no mdnsd/Bonami — requisitos vindos do Matter"
status: backlog
priority: medium
type: external
owner: jaime
milestone: M2
area: dnssd
created_at: 2026-10-28
updated_at: 2026-10-28
tags: [external, upstream, mdns, ipv6]
blockers: []
depends_on: [ISSUE-0008]
upstream_refs: [AROS workbench/network/mdns/README.md §Limits]
related_files: []
---

# Por quê

O mantenedor do mdnsd/Bonami (jaime) vai implementar IPv6 como trabalho futuro, fora deste repo. Esta issue só **registra o que o Matter precisa**, para que essa implementação o cubra, e acompanha o andamento.

# O quê

Requisitos para a opção B de ISSUE-0004:

- Responder e consultar em `ff02::fb`; publicar e resolver `AAAA` (incluindo link-local, com interface/scope id no resultado).
- Browse por subtipo DNS-SD (`_L840._sub._matterc._udp`, `_I<id>._sub._matter._tcp`).
- Resultado de resolve com várias addresses (v4 e v6) e a interface de origem.
- Registro de serviço com subtipos (necessário só para o modo accessory, fora do escopo atual).
- TXT binário ou com `=` arbitrário (chaves Matter: `D`, `CM`, `VP`, `SII`, `SAI`, `T`, `PH`, `PI`…).

Fica de fora: qualquer implementação neste repositório.

Pré-requisito descoberto: o mdnsd IPv6 vai precisar dos fixes de multicast IPv6 do AROSTCP (ISSUE-0008: envio de `[::]:5353`, recepção de grupos entrados, entrega a vários sockets).

# Passos de validação

- [ ] Mantenedor confirma o escopo/agenda do IPv6 no mdnsd
- [ ] Quando houver: `dnssd` resolve um acessório Matter real com AAAA

# Critério de sucesso / falha

- Sucesso se: a Bonami resolve `_matterc._udp` com subtipo e AAAA de um dispositivo real.

# Log

- 2026-10-28: criada; o mantenedor confirmou que o IPv6 no mdnsd será trabalho futuro dele.
