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
| [0009](issues/ISSUE-0009.md) | AROSTCP: rotas sem referência ao endereço (UAF intermitente) | done (#1977) | high | M0 |
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
| [#1973](https://github.com/aros-development-team/AROS/pull/1973) | G17: `sendto()` UDP6 escolhe a origem só para o datagrama (não prende `inp_laddr6`) | mesclado (`c8e79a9cc3`) |
| [#1974](https://github.com/aros-development-team/AROS/pull/1974) | S6: zonas de endereços link-scope em bind/connect/getsockname/getpeername/recvfrom; loopback do próprio link-local pela interface real | mesclado (`d50355747a`) |
| [#1975](https://github.com/aros-development-team/AROS/pull/1975) | Resto da S7: `IPV6_MULTICAST_IF` escolhe a origem do datagrama multicast UDP6 | mesclado |
| [#1976](https://github.com/aros-development-team/AROS/pull/1976) | S8: RFC 4191 (preferência do roteador default, RIO, `::/0`) + limpeza dos roteadores da interface | mesclado (`1fef6c415e`) |
| [#1977](https://github.com/aros-development-team/AROS/pull/1977) | ISSUE-0009: `in6_purgeaddr()` apaga as rotas que usam o endereço (`rt_purgeifa`, como o IPv4); o reload travava com `rt_ifa` liberado | mesclado |
| [#1979](https://github.com/aros-development-team/AROS/pull/1979) | S8b: o reload devolve o link-local e os endereços SLAAC (`in6_if_up()` no `addifent()`, `nd6_purge_prefixes()`) | aberto 2026-10-30; slaac6 master falha, branch passa |
| [#1983](https://github.com/aros-development-team/AROS/pull/1983) | G19c+d: fragmentação IPv6 (todos os fragmentos, bit M na ordem certa, `rt` NULL em multicast) | **merged** (b35c81ec1a); revalidado com build limpo pós-merge |
| [#1991](https://github.com/aros-development-team/AROS/pull/1991) | follow-up do #1980 (Codex): `header` com escopo reduzido em `mdnsd.c` (Codacy variableScope) | aberto 2026-10-31 |
| [#1992](https://github.com/aros-development-team/AROS/pull/1992) | follow-up do #1986 (Codex): AROSTCP 5.15 / kernel v0.54 em `bsdsocket/version.h`, pedido do Kal | aberto 2026-10-31 |

**Build isolado (2026-10-30):** o Codex compilou em `~/aros-build-ipv6-hosted` a partir de `/tmp/aros-udp6-hops`; o `udp6_usrreq.o` dele entrou nos binários "frag" (#1983) e "mss". A partir de agora o build próprio é `~/aros-build-ipv6-hosted-claude` (mesma configuração, toolchain do midihub, cache de fontes copiado). Não usar o diretório antigo para validar.

**Revisão do AROSTCP:** todo PR funcional no AROSTCP sobe REVISION/DATE/VERS/VERSTAG/kernel em `bsdsocket/version.h` (Kal no #1986). O PR do MSS leva 5.16 / v0.55 por cima do #1992.

Próximos: rerodar o caso `mss advmss=0` do bench TCP (veio vazio) → abrir o PR do **G19b** (MSS do TCP em IPv6; commits prontos em `review/arostcp-ipv6-tcp-mss`) → #1980 (mdnsd IPv6, do Codex) só se o Codex parar de mexer nele → G19e (T/TCP no SYN) → G19h, R1 → G19i. Depois: S1 (`localhost`), R4, R7, G18a–i.

Lição (2026-10-30): todo programa CUnit do AROS roda a suíte duas vezes (básica e automática). Validar **os dois** resumos; o Kal achou no #1950 uma falha que só aparecia na segunda.

**Sequência sugerida para a trilha Matter (não é bloqueada pelo Backlog 2):** após estabilização suficiente do IPv6, ISSUE-0003 (crypto) → fechar ISSUE-0001 → ISSUE-0006 (spike M1) → ISSUE-0004. O agente pode intercalar ou antecipar essas atividades e as frentes B2 conforme dependências, evidências e riscos; não existe exigência de concluir a modernização TCP antes do Matter.

## Planejamento futuro — ativação incremental pelo agente

- [Backlog 2 — modernização incremental do AROSTCP](backlog2.md): segurança, PMTUD, recuperação, temporizadores e TCP avançado. **O agente pode ativar e repriorizar autonomamente itens B2**, com evidência e reconciliação com upstream e trabalho em andamento, sem prejudicar entregas ativas ou alterar M0–M6. Decisões excepcionais de alto risco permanecem sujeitas à aprovação do mantenedor.

## Decisões em aberto para o mantenedor

- ~~Primeiro alvo~~ → decidido: AROS hosted linux-x86_64 (2026-10-28).
- ~~IPv6 D1–D4~~ → decididas (2026-10-28): modelo do Readme §6.6, coordenação com Kal, testes em `tests/`.
- Upstream AROS: commits/PRs **sem assinatura do Claude Code**.
- Fixar uma tag de release do connectedhomeip (ex.: `v1.4.x`) em vez de `master`?


## Coordenação com aros-midihub

Para mudanças compartilhadas em AROSTCP, IPv6/multicast, mdnsd/Bonami e DNS-SD, consultar [contrato de coordenação](../docs/upstream-coordination.md) e [índice de trabalho em andamento](../docs/upstream-work-in-progress.md). Antes de abrir PR upstream, verificar master/PRs atuais e inventariar branches, commits e worktrees locais ainda não publicados. A coordenação não impõe precedência global entre os backlogs ou marcos Matter; dependências devem ser concretas e específicas à tarefa.
