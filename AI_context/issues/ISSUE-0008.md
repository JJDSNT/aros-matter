---
id: ISSUE-0008
title: "AROSTCP IPv6: zonas de escopo, seleção de origem e multicast conforme as RFCs"
status: ready
priority: critical
type: upstream
owner: jaime
milestone: M0
area: network
created_at: 2026-10-28
updated_at: 2026-10-28
tags: [upstream, arostcp, ipv6, multicast, scope, rfc4007, rfc6724, rfc3493, rfc3542, rfc4191]
blockers:
  - "S6/S7 (G1/G2) aguardam conversa com Kal (Nick Andrews) sobre a análise"
depends_on: []
upstream_refs: [AROS@4c2c268a53 workbench/network/stacks/AROSTCP/bsdsocket/netinet6, freebsd-src@389ae8e4fa sys/netinet6]
related_files: [AI_context/research/arostcp-ipv6-design.md, AI_context/research/2026-10-28-hosted-tests.md, tests/m0/ipv6probe.c, tests/m0/peer_mdns6.py]
---

# Por quê

Os testes no hosted mostraram que o multicast IPv6 não funciona nos dois sentidos. A análise (`research/arostcp-ipv6-design.md`) mostrou que os sintomas vêm de lacunas de arquitetura: falta o modelo de zonas da RFC 4007 e uma seleção única de interface e origem (RFC 6724). Também faltam partes do modelo multicast (recepção por grupo, entrega a vários sockets, loopback, ciclo de vida das associações). É pré-requisito do mDNS IPv6 (ISSUE-0005) e do Matter (ISSUE-0004).

Diretriz do mantenedor (2026-10-28): implementações corretas e completas por área, baseadas em pesquisa; não correções pontuais.

# O quê

Lacunas G1–G9 e plano em etapas S0–S9: ver `research/arostcp-ipv6-design.md` §3 e §5.

Fica de fora: MLDv2 com filtro de fontes (RFC 3678 SSM), roteamento multicast, IPsec, mobilidade.

# Passos de validação

- [x] Reproduzir os sintomas: `ipv6probe eth0` + `peer_mdns6.py` (`research/logs/2026-10-28/`)
- [x] Análise de arquitetura com referências (RFCs, FreeBSD `389ae8e4fa`) → `research/arostcp-ipv6-design.md`
- [x] Mantenedor revisa o desenho e decide D1–D4
- [x] S0: suíte de testes IPv6 (`tests/ipv6/`, 18 casos; base em `research/logs/2026-10-28/s0-baseline/`)
- [x] S1: ciclo de vida das associações → **AROS #1924** (https://github.com/aros-development-team/AROS/pull/1924), branch `review/arostcp-ipv6-membership` (`667b0e7218`, base `d68c0a784c`); evidência em `research/logs/2026-10-28/s1-ab/` e `pr-review/`
- [ ] S2–S5: recepção, entrega UDP, loopback, ancillary data
- [ ] S6–S7: zonas e seleção de origem (após D1/D4)
- [ ] S8: RIO (RFC 4191)
- [ ] PRs upstream separados por etapa, cada um com o teste CUnit no padrão do upstream (`tests/upstream/`, ex.: `cunit-net-mld6.c` para a S1)

# Critério de sucesso / falha

- Sucesso se: cada etapa fecha com o teste listado no §5 do desenho e sem regressão em IPv4 multicast, ND/SLAAC, DHCPv4 e TCP6; ao final, o AROS envia de `[::]:5353` para `ff02::fb%if`, vários sockets recebem com `PKTINFO`, e endereços link-local com `%if` funcionam em bind/connect/sendto/recvfrom com duas interfaces.
- Falha se: o upstream rejeitar a direção de G1/G2; nesse caso, rever o desenho com eles antes de seguir.

# Decisões tomadas

- 2026-10-28: trabalho upstream na branch `arostcp-ipv6`, worktree `~/AROS-ipv6`, a partir de `upstream/master` `4c2c268a53`. Nenhuma branch existente é alterada.
- 2026-10-28: o contorno de bind no link-local serviu só para os testes; não é solução.
- 2026-10-28: o IPv6 do AROS passa a ser o primeiro foco do projeto (decisão do mantenedor).
- 2026-10-28: D1 = modelo de zona explícita já documentado em `bsdsocket/Readme.md` §6.6; D4 = coordenar com Kal; testes ficam em `tests/` deste repo.
- 2026-10-28: **commits e PRs upstream sem assinatura do Claude Code.**
- 2026-10-28: cada PR leva junto o teste que demonstra o problema, no formato CUnit do upstream (pedido do mantenedor). A suíte de bancada `tests/ipv6/` continua sendo a validação ampla.

# Log

- 2026-10-28: criada a partir dos testes no hosted.
- 2026-10-28: reformulada como trabalho de arquitetura; desenho em revisão.
- 2026-10-28: decisões registradas; pronta para S0/S1.
- 2026-10-28: S0 concluída; S1 implementada e validada (A/B: upstream morre em `mld.ifdetach`, S1 passa 53 verificações, 14 falhas restantes = S2–S7). Achado à parte: ISSUE-0009 (tempo de vida rota/endereço).
- 2026-10-28: testes do upstream (`developer/debug/test/net/socket`, CUnit, loopback) passam inalterados com a S1. Criado `tests/upstream/.../cunit-net-mld6.c`, que observa o próprio MLD via BPF: upstream falha 4/5 (controle passa), S1 passa 5/5.
- 2026-10-28: PR AROS #1924 aberto (4 commits: teste, socket, endereço, interface), sem assinatura.
- 2026-10-28: aberta a issue pública https://github.com/JJDSNT/aros-matter/issues/1 (em inglês) com achados, causas e perguntas para o Kal.
