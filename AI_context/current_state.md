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
| [#1979](https://github.com/aros-development-team/AROS/pull/1979) | S8b: o reload devolve o link-local e os endereços SLAAC (`in6_if_up()` no `addifent()`, `nd6_purge_prefixes()`) | mesclado (`1a565164eb`) |
| [#1983](https://github.com/aros-development-team/AROS/pull/1983) | G19c+d: fragmentação IPv6 (todos os fragmentos, bit M na ordem certa, `rt` NULL em multicast) | **merged** (b35c81ec1a); revalidado com build limpo pós-merge |
| [#1991](https://github.com/aros-development-team/AROS/pull/1991) | follow-up do #1980 (Codex): `header` com escopo reduzido em `mdnsd.c` (Codacy variableScope) | **merged** 2026-10-31 |
| [#1992](https://github.com/aros-development-team/AROS/pull/1992) | follow-up do #1986 (Codex): AROSTCP 5.15 / kernel v0.54 em `bsdsocket/version.h`, pedido do Kal | **merged** 2026-10-31 (7a6f655644) |
| [#1995](https://github.com/aros-development-team/AROS/pull/1995) | G19b: MSS do TCP em IPv6 (60 bytes de cabeçalho, default 1220, respeita o MSS do peer, SYN-ACK do syncache) + 5.16 / v0.55 | **merged** 2026-10-31; evidência em `research/logs/2026-10-31/pr-tcp-mss6/` |
| [#1996](https://github.com/aros-development-team/AROS/pull/1996) | G19e: T/TCP desligado por padrão (`tcp_do_rfc1644 = 0`; RFC 6247), teste `cunit-net-tcpsyn6` (BPF no SYN), Readme §5.4, 5.16 | **merged** 2026-10-31; conflita com o #1995 em `version.h`/mmakefile: quem entrar depois sobe para 5.17. Evidência em `research/logs/2026-10-31/pr-ttcp-off/` |
| [#1997](https://github.com/aros-development-team/AROS/pull/1997) | G19h: `close()` com dados não lidos manda RST (RFC 9293 §3.6.1 SHLD-2), 4 casos novos no `cunit-net-tcp`, Readme §10, 5.16 | **merged** 2026-10-31; evidência em `research/logs/2026-10-31/pr-close-rst/` |
| [#1998](https://github.com/aros-development-team/AROS/pull/1998) | R1/G19g: portas efêmeras aleatórias em 49152–65535 (RFC 6056 alg. 1, RFC 6335), `in_pcbpickport()`, `EADDRNOTAVAIL` ao esgotar, teste `cunit-net-ports`, Readme §10 | **merged** 2026-10-31; evidência em `research/logs/2026-10-31/pr-ephemeral-ports/` |
| [#2000](https://github.com/aros-development-team/AROS/pull/2000) | G19j: `tcp_now`/`tcp_iss` param sem conexões TCP (`tcp_slowtimo()` retornava antes) → TSval 0 no SYN, ISN parado e o rate limit de ICMP IPv4 sem recarga (só 10 erros); teste no `cunit-net-udp`, Readme §5.3 | **fechado, agrupado em #2005**; evidência em `research/logs/2026-10-31/pr-tcp-clock/` |
| aa24b08479 (Kal) | G19l + crash: `icmp6_input()` passava DST_UNREACH/TIME_EXCEEDED/PARAM_PROB/PTB a `pfctlinput(..., NULL)` → `in_pcbnotify()` derreferenciava NULL: **qualquer erro ICMPv6 da rede derrubava a pilha**. Kal corrigiu com `icmp6_notify_error()` + `udp6_ctlinput`/`tcp6_ctlinput`/`in6_pcbnotify()` (KAME) e o teste `cunit-net-icmp6err`, 5.19 | **merged** 2026-10-31. Achamos o mesmo crash em paralelo (trap em `in_pcbnotify+0x1f` com um Port Unreachable real do Linux; logs em `research/logs/2026-10-31/icmp6-error-crash/`); nosso branch foi descartado |
| [#2001](https://github.com/aros-development-team/AROS/pull/2001) | G19k: UDP6 manda ICMPv6 Port Unreachable (RFC 4443 §3.1); `icmp6_error()` responde da origem certa (§2.2 a) e não responde a origem `::`/multicast (§2.4 e); teste `cunit-net-unreach6`, Readme §6.3, 5.20 | **fechado, agrupado em #2005**; evidência em `research/logs/2026-10-31/pr-udp6-port-unreach/` |
| [#2002](https://github.com/aros-development-team/AROS/pull/2002) | PMTUD P4+P5: PMTU do PTB numa rota host do próprio destino (clone `RTF_DYNAMIC` via roteador, como KAME), expira em 10 min (RFC 8201 §4); teste `cunit-net-pmtu6`, Readme §6.3, 5.20 | **fechado, agrupado em #2005**; evidência em `research/logs/2026-10-31/pr-pmtu-host-route/` |
| [#2003](https://github.com/aros-development-team/AROS/pull/2003) | PMTUD P7: fila de ND de até 16 pacotes por vizinho (antes 1: só o último fragmento saía) e Destination Unreachable (address) para cada pacote quando a resolução falha (RFC 4861 §7.2.2 MUST); teste `cunit-net-ndqueue6`, Readme §6.1, 5.20 | **fechado, agrupado em #2005**; evidência em `research/logs/2026-10-31/pr-nd6-hold-queue/` |
| [#2004](https://github.com/aros-development-team/AROS/pull/2004) | `kern_random()` sobre o `arc4random_buf()` da CRT (pool de 256 bytes; revisado após o Kal pedir a CRT em vez do `entropy.resource` direto) para a chave de ISN/SYN cookies, chave de portas, IDs IPv4, ID de fragmento IPv6 (era contador, RFC 7739) e IIDs temporários (RFC 8981); teste no `cunit-net-frag6`, Readme §10, 5.20 | **fechado, agrupado em #2005**; evidência em `research/logs/2026-10-31/pr-entropy/` |
| [#2005](https://github.com/aros-development-team/AROS/pull/2005) | **Série agrupada**, 7 commits (um por mudança, com o teste; bump 5.20 no último), a pedido do Kal: relógios TCP, Port Unreachable UDP6, PMTU por destino, fila de ND, valores aleatórios via CRT, **partial ACK do NewReno (G19m)**, **TCP reage ao PTB (P3)**. 23 suítes; bench de roteador estreito: 2×2 MB, 0 fragmentos (master trava em 2008 bytes) | **merged** 2026-10-31 (bf196e7dc1, 5.20); evidência em `research/logs/2026-10-31/pr-series/` |

**Build isolado (2026-10-30):** o Codex compilou em `~/aros-build-ipv6-hosted` a partir de `/tmp/aros-udp6-hops`; o `udp6_usrreq.o` dele entrou nos binários "frag" (#1983) e "mss". A partir de agora o build próprio é `~/aros-build-ipv6-hosted-claude` (mesma configuração, toolchain do midihub, cache de fontes copiado). Não usar o diretório antigo para validar.

**Revisão do AROSTCP:** todo PR funcional no AROSTCP sobe REVISION/DATE/VERS/VERSTAG/kernel em `bsdsocket/version.h` (Kal no #1986). #1995 = 5.16; #1996/#1997 = 5.17; #1998 = 5.18; aa24b08479 (Kal) = 5.19. #2005 (série) leva 5.20 / v0.59. **Segundo grupo:** [#2006](https://github.com/aros-development-team/AROS/pull/2006), aberto 2026-10-31 depois do merge do #2005: fila do ARP + 1 pedido/s (RFC 1122 §2.3.2.1) e PMTUD IPv4 (RFC 1191: DF no TCP, `icmp_mtudisc()`, PMTU por destino em `route.c` compartilhado com IPv6, `ip_output` usa o MTU da rota, `tcp_mtudisc()` comum); 2 commits, 5.21 / v0.60; 25 suítes. R2 (RFC 5961) ficou fora deste grupo. Bench a corrigir: depois que o tap foi recriado, o `run_tcp.py --only send` conta só 15 "segmentos" e nenhuma perda (master e branch iguais), provavelmente agregação no tap antes da captura e do tc. **Regras (Kal, 2026-10-31):** mudanças no AROSTCP vão num PR agrupado por trabalho coerente; cada mudança é **um** commit (teste + fix juntos); um bump só, no último commit; trabalho novo do tema entra no PR aberto.

**Lição de teste (2026-10-31):** num teste CUnit que conecta a um vizinho, o vizinho pode recusar (RST) antes de `connect()` voltar; o PCB some e `getsockname()` dá EINVAL. Fazer `bind()` + `getsockname()` antes do `connect()`. A falha só aparecia sem `printf` (timing) e na segunda execução.

**Bench (2026-10-31):** o caso `mss advmss=0` vazio era do bench: um tap recém-criado não tem link-local até ter carrier, e o script mandava `None` como host (errno 49). `tools/tap-up.sh` agora dá `fe80::1` (nodad) a um tap sem link-local, e `run_tcp.py` aborta sem link-local. `mld.ifdetach` (janela de MLD no host) falhou 1 vez em 4 com master e com o fix: timing, não regressão.

Próximos: aguardar #2000/#2001. **Trilha Matter retomada (2026-10-31):** ISSUE-0003 passos 1–3 feitos no host (SDK crypto 71/71 com +4 opções na config do mbedTLS do AROS); nada falta ao mbedTLS do AROS (só config, que fica no aros-matter). ISSUE-0003 pausada no passo 4; **prioridade volta a IPv6/TCP**.

**Auditoria de PMTUD (B2-B, 2026-10-31):** [research/2026-10-31-pmtud-audit.md](research/2026-10-31-pmtud-audit.md). Achados P1–P8: IPv4 sem PMTUD; IPv6 ok para conexões novas, mas uma conexão TCP em curso não é avisada do PTB (fragmenta tudo); o PMTU off-link cai na rota default (vale para todos os destinos) e nunca expira; PTB não é conferido; fila de ND de um pacote (perde fragmentos). P4+P5 em review como #2002, P7 como #2003, semente/IDs como #2004. Próximas: P3 (TCP reage ao PTB, falar com o Kal), P7 (fila de ND), depois a semente do `entropy.resource` para ISN/portas. G19i explicado (sem defeito no RTO). Depois: S1 (`localhost`), R4, R7, G18a–i. #1980 foi mesclado (Codex); o follow-up do Codacy foi o #1991.

**Backlog 2 (2026-10-31):** matriz de reconciliação em [research/2026-10-31-backlog2-reconciliation.md](research/2026-10-31-backlog2-reconciliation.md). B2 ainda não é ativado como frente própria: G19e/G19h/R1 cobrem B2-A e G19i cobre B2-C. G19f explicado (`tcp_do_ecn = 0`, desligado por padrão). Achado: as opções `TCP_KEEP*` estão só no header, sem `tcp_ctloutput()`. Primeiro candidato B2 depois disso: auditoria de PMTUD (B2-B, só pesquisa).

Lição (2026-10-30): todo programa CUnit do AROS roda a suíte duas vezes (básica e automática). Validar **os dois** resumos; o Kal achou no #1950 uma falha que só aparecia na segunda.

**Sequência sugerida para a trilha Matter (não é bloqueada pelo Backlog 2):** após estabilização suficiente do IPv6, ISSUE-0003 (crypto) → fechar ISSUE-0001 → ISSUE-0006 (spike M1) → ISSUE-0004. O agente pode intercalar ou antecipar essas atividades e as frentes B2 conforme dependências, evidências e riscos; não existe exigência de concluir a modernização TCP antes do Matter.

## Planejamento futuro — ativação incremental pelo agente

- [Backlog 2 — modernização incremental do AROSTCP](backlog2.md): segurança, PMTUD, recuperação, temporizadores e TCP avançado. **O agente pode ativar e repriorizar autonomamente itens B2**, com evidência e reconciliação com upstream e trabalho em andamento, sem prejudicar entregas ativas ou alterar M0–M6. Decisões excepcionais de alto risco permanecem sujeitas à aprovação do mantenedor.

## Decisões em aberto para o mantenedor

- ~~Primeiro alvo~~ → decidido: AROS hosted linux-x86_64 (2026-10-28).
- ~~IPv6 D1–D4~~ → decididas (2026-10-28): modelo do Readme §6.6, coordenação com Kal, testes em `tests/`.
- Upstream AROS: commits/PRs **sem assinatura do Claude Code**.
- ~~Fixar uma tag de release do connectedhomeip~~ → decidido (2026-10-31): **última stable, v1.6.1.0** (`3bcdd56ba5`).


## Coordenação com aros-midihub

Para mudanças compartilhadas em AROSTCP, IPv6/multicast, mdnsd/Bonami e DNS-SD, consultar [contrato de coordenação](../docs/upstream-coordination.md) e [índice de trabalho em andamento](../docs/upstream-work-in-progress.md). Antes de abrir PR upstream, verificar master/PRs atuais e inventariar branches, commits e worktrees locais ainda não publicados. A coordenação não impõe precedência global entre os backlogs ou marcos Matter; dependências devem ser concretas e específicas à tarefa.
