---
id: ISSUE-0001
title: "Matriz de capacidades M0 com evidência"
status: doing
priority: high
type: audit
owner: jaime
milestone: M0
area: network
created_at: 2026-10-28
updated_at: 2026-10-28
tags: [m0, audit]
blockers: []
depends_on: [ISSUE-0007, ISSUE-0008]
upstream_refs: [AROS@cbca98214f, connectedhomeip@8fd0af0792]
related_files: [docs/architecture-and-research.md, AI_context/research/2026-10-28-initial-desk-audit.md]
---

# Por quê

O M0 exige que cada linha da matriz (§4 de `docs/architecture-and-research.md`) tenha resultado testado, limitação ou bloqueio explícito. Sem isso, o port do SDK vira aposta.

# O quê

Preencher a matriz em duas camadas: (a) leitura de código com SHA; (b) teste executado no AROS. Fica de fora qualquer código Matter.

# Passos de validação

- [x] Leitura de código: IPv6, multicast, Bonami, mbedTLS, entropy → `research/2026-10-28-initial-desk-audit.md`
- [x] IPv6 UDP unicast (loopback), `WaitSelect`, `if_nametoindex`, `SIOCGLIFADDR` → `research/2026-10-28-hosted-tests.md`
- [~] Multicast IPv6 com host Linux via tap: envio só com contorno, recepção falha → bugs no AROSTCP, ISSUE-0008
- [~] Dois sockets na 5353 com `SO_REUSEPORT`: o bind funciona; a entrega a ambos falha por código (bug C, ISSUE-0008)
- [ ] Entropy: `entropy.resource` no alvo escolhido (ISSUE-0002); caminho de falha
- [ ] Timers monotônicos e `WaitSelect()` com timeout/cancelamento → teste de estresse
- [ ] Persistência: escrita atômica (rename) no filesystem do alvo → teste de queda/restart
- [ ] SPAKE2+/CASE → delegado a ISSUE-0003

# Critério de sucesso / falha

- Sucesso se: todas as linhas da matriz têm "testado OK", "limitação documentada" ou "bloqueio com issue".
- Falha se: alguma linha permanece só com leitura de código ao iniciar o M1.

# Evidências

- Leitura de código: `research/2026-10-28-initial-desk-audit.md`.
- Testes no hosted: `research/2026-10-28-hosted-tests.md`, `research/logs/2026-10-28/`.

# Decisões tomadas

# Log

- 2026-10-28: criada; primeira rodada de leitura de código concluída.
- 2026-10-28: testes IPv6 no hosted; abertas as lacunas da pilha na ISSUE-0008.
