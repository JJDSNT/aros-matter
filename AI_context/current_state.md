# Estado atual — aros-matter

Atualizado: 2026-10-28

## Foco atual (desde 2026-10-28)

**IPv6 no AROSTCP**, pré-requisito do mDNS IPv6 e do Matter. Desenho em revisão: [research/arostcp-ipv6-design.md](research/arostcp-ipv6-design.md) ([ISSUE-0008](issues/ISSUE-0008.md)). Trabalho na branch `arostcp-ipv6` (worktree `~/AROS-ipv6`, base `upstream/master` `4c2c268a53`). Diretriz: implementações corretas por área, com base em pesquisa, não correções pontuais.

Bancada: AROS hosted linux-x86_64 (`tools/hosted-run.sh`) + tap isolada `aros0` (`tools/tap-up.sh`).

## Resumo

Fase de pesquisa (M0). Toolchain validada (ISSUE-0002 concluída). Testes IPv6 no hosted mostraram lacunas na pilha (ISSUE-0008). A primeira auditoria por leitura de código ([research/2026-10-28-initial-desk-audit.md](research/2026-10-28-initial-desk-audit.md)) leva a quatro conclusões:

1. **A pilha IPv6 existe no AROSTCP upstream** (UDP6, MLD6, `IPV6_JOIN_GROUP`, `PKTINFO`, dual-stack). Falta testar com tráfego real.
2. **O mdnsd/Bonami é só IPv4.** IPv6 no mdnsd é trabalho futuro do mantenedor ([ISSUE-0005](issues/ISSUE-0005.md)). Isso não bloqueia o M2: o SDK traz `minimal_mdns`, que roda direto sobre sockets ([ISSUE-0004](issues/ISSUE-0004.md)).
3. **O SDK exige C++17+.** O GCC padrão do AROS é 6.5, e o x86_64 usa 10.5. Primeiro alvo provável: x86_64 ([ISSUE-0002](issues/ISSUE-0002.md)).
4. **Crypto:** o SPAKE2+ do SDK com backend mbedTLS usa ECP/MPI de baixo nível, não PSA PAKE. O SDK fixa o mbedTLS em 2.28; o AROS embarca 3.6.7. É preciso validar a compatibilidade ([ISSUE-0003](issues/ISSUE-0003.md)).

## Revisões de referência

- AROS upstream: `cbca98214f` (2026-10-28)
- connectedhomeip: `8fd0af0792` (2026-10-28), ainda não fixado como alvo do port

## Issues abertas

| ID | Título | Status | Prio | Marco |
|---|---|---|---|---|
| [0008](issues/ISSUE-0008.md) | AROSTCP IPv6: zonas, seleção de origem, multicast | ready | critical | M0 |
| [0009](issues/ISSUE-0009.md) | AROSTCP: rotas sem referência ao endereço (UAF intermitente) | backlog | high | M0 |
| [0001](issues/ISSUE-0001.md) | Matriz de capacidades M0 com evidência | doing | high | M0 |
| [0002](issues/ISSUE-0002.md) | Toolchain C++17 e primeiro alvo AROS | done | critical | M0/M1 |
| [0003](issues/ISSUE-0003.md) | Backend crypto: SDK × mbedTLS 3.6.7 do AROS | ready | high | M0/M1 |
| [0004](issues/ISSUE-0004.md) | Estratégia de descoberta: minimal_mdns × Bonami | ready | high | M2 |
| [0005](issues/ISSUE-0005.md) | IPv6 no mdnsd/Bonami (requisitos Matter) | backlog | medium | M2+ |
| [0006](issues/ISSUE-0006.md) | Spike M1: camada de plataforma mínima | backlog | high | M1 |
| [0007](issues/ISSUE-0007.md) | Bancada de testes: acessório e controlador de referência | doing | high | M0–M5 |

## Ordem sugerida

ISSUE-0008: S0 ✅, S1 ✅ **mesclada** no upstream ([AROS #1924](https://github.com/aros-development-team/AROS/pull/1924), `42cb8e8f34`), S2–S4 em revisão ([AROS #1945](https://github.com/aros-development-team/AROS/pull/1945)) → S5 (ancillary/LP64) e S7 (seleção de interface/origem) (IPv6 no AROSTCP: S0–S5 primeiro, S6–S7 após decisão de desenho). Em paralelo, se houver tempo: ISSUE-0003 (crypto). Depois fechar ISSUE-0001 → ISSUE-0006 (spike M1) → ISSUE-0004.

## Decisões em aberto para o mantenedor

- ~~Primeiro alvo~~ → decidido: AROS hosted linux-x86_64 (2026-10-28).
- ~~IPv6 D1–D4~~ → decididas (2026-10-28): modelo do Readme §6.6, coordenação com Kal, testes em `tests/`.
- Upstream AROS: commits/PRs **sem assinatura do Claude Code**.
- Fixar uma tag de release do connectedhomeip (ex.: `v1.4.x`) em vez de `master`?
