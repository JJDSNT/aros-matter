# Estado atual — aros-matter

Atualizado: 2026-10-30

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

Atualizado 2026-10-30. **IPv6 no AROSTCP (ISSUE-0008):**

| PR | Conteúdo | Estado |
|---|---|---|
| [#1924](https://github.com/aros-development-team/AROS/pull/1924) | S1: ciclo de vida das associações multicast | mesclado (`42cb8e8f34`) |
| [#1947](https://github.com/aros-development-team/AROS/pull/1947) | S5: ancillary data (LP64, cadeia, `in6_pktinfo`, `IPV6_RECVHOPLIMIT`) | mesclado (`0b1e1de27d`) |
| [#1948](https://github.com/aros-development-team/AROS/pull/1948) | G15a/b/c: rotas via roteador, próximo salto, default de RA | mesclado (`6053248953`) |
| [#1950](https://github.com/aros-development-team/AROS/pull/1950) | G15d/e, G16b: ciclo de vida de endereço | mesclado (`343de5cddf`) |
| [#1945](https://github.com/aros-development-team/AROS/pull/1945) | S2–S4: entrega multicast aos membros | mesclado (`62bd8216b1`) |
| [#1970](https://github.com/aros-development-team/AROS/pull/1970) | G16a: origem IPv6 por escopo (RFC 6724 regras 2/3/7), MLD da link-local | mesclado (`f71efe2595`) |
| [#1971](https://github.com/aros-development-team/AROS/pull/1971) | G14: sockets raw IPv6 (RFC 3542 §3): `inpcb`, opções, `ICMP6_FILTER`, todo ICMPv6 | mesclado (`273470fdd2`), com as correções do Codacy (cppcheck: `bzero`/`memcpy`, `optp`) |
| [#1973](https://github.com/aros-development-team/AROS/pull/1973) | G17: `sendto()` UDP6 escolhe a origem só para o datagrama (não prende `inp_laddr6`) | aberto 2026-10-30; master `273470fdd2` mesclado na branch, todas as suítes passam |
| [#1974](https://github.com/aros-development-team/AROS/pull/1974) | S6: zonas de endereços link-scope em bind/connect/getsockname/getpeername/recvfrom; loopback do próprio link-local pela interface real | aberto 2026-10-30; scope6 master 8/8 falham, branch 8/8 |

Próximos: resto da **S7** (`IPV6_MULTICAST_IF` escolher a origem multicast: as 6 falhas restantes da bancada) → **S8** (RFC 4191; WIP local `f16bbd4f8f`, rebasear sobre o master e corrigir a máscara da default) → **S6/S7** (com o Kal). Bancada no master+#1945: 9 falhas = S7 (envio multicast de `[::]`) ×8 + S6 (`sin6_scope_id` recebido) ×1.

Lição (2026-10-30): todo programa CUnit do AROS roda a suíte duas vezes (básica e automática). Validar **os dois** resumos; o Kal achou no #1950 uma falha que só aparecia na segunda.

Depois do IPv6: ISSUE-0003 (crypto) → fechar ISSUE-0001 → ISSUE-0006 (spike M1) → ISSUE-0004.

## Decisões em aberto para o mantenedor

- ~~Primeiro alvo~~ → decidido: AROS hosted linux-x86_64 (2026-10-28).
- ~~IPv6 D1–D4~~ → decididas (2026-10-28): modelo do Readme §6.6, coordenação com Kal, testes em `tests/`.
- Upstream AROS: commits/PRs **sem assinatura do Claude Code**.
- Fixar uma tag de release do connectedhomeip (ex.: `v1.4.x`) em vez de `master`?
