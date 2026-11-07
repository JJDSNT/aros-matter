# Estado atual — aros-matter

Atualizado: 2026-11-07

## Foco atual (desde 2026-10-28)

**IPv6 no AROSTCP**, pré-requisito do mDNS IPv6 e do Matter. Desenho em revisão: [research/arostcp-ipv6-design.md](research/arostcp-ipv6-design.md) ([ISSUE-0008](issues/ISSUE-0008.md)). Trabalho na branch `arostcp-ipv6` (worktree `~/AROS-ipv6`, base `upstream/master` `4c2c268a53`). Diretriz: implementações corretas por área, com base em pesquisa, não correções pontuais.

Bancada: AROS hosted linux-x86_64 (`tools/hosted-run.sh`) + tap isolada `aros0` (`tools/tap-up.sh`).

## Prioridade atual (mantenedor, 2026-10-31)

**Completar a pilha AROSTCP vem antes do Matter.** A trilha Matter (ISSUE-0003 passo 4, M1–M5) fica em espera; o trabalho segue em grupos de PR do AROSTCP (um aberto por vez), tirados do Backlog 2 e das pendências IPv6/TCP. **Plano dos grupos:** [research/2026-10-31-arostcp-pr-groups-plan.md](research/2026-10-31-arostcp-pr-groups-plan.md), revisto em 2026-11-01 para servir às três iniciativas ([research/2026-11-01-network-roadmap-integration.md](research/2026-11-01-network-roadmap-integration.md): Matter, pilha, Open Screen/[backlog3](backlog3.md)) — grupo 3 path MTU e ECN para TCP e UDP (black-hole, `IPV6_DONTFRAG`/`IP_DONTFRAG`/`IPV6_PATHMTU`/`IPV6_RECVPATHMTU`, ECN só-aceitar + ancilares UDP, sysctls), 4 API e UDP (keepalive, `localhost`, testes de UDP, stackprobe), 5 IPv6 em redes reais (RDNSS, G18a–i, duas interfaces), 6 recuperação e endurecimento do TCP (PRR ligado, RFC 5961, TSval, SYN cookies), 7 timers. QUIC: biblioteca compartilhada, o OpenSSL 4.0.1 do contrib (não no Prism, não no AROSTCP); validar no AROS depois do grupo 3.

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

**Revisão do AROSTCP:** todo PR funcional no AROSTCP sobe REVISION/DATE/VERS/VERSTAG/kernel em `bsdsocket/version.h` (Kal no #1986). #1995 = 5.16; #1996/#1997 = 5.17; #1998 = 5.18; aa24b08479 (Kal) = 5.19. #2005 (série) leva 5.20 / v0.59. **Segundo grupo:** [#2006](https://github.com/aros-development-team/AROS/pull/2006), aberto 2026-10-31 depois do merge do #2005: fila do ARP + 1 pedido/s (RFC 1122 §2.3.2.1) e PMTUD IPv4 (RFC 1191: DF no TCP, `icmp_mtudisc()`, PMTU por destino em `route.c` compartilhado com IPv6, `ip_output` usa o MTU da rota, `tcp_mtudisc()` comum); 2 commits, 5.21 / v0.60; 25 suítes. R2 (RFC 5961) ficou fora deste grupo. **Bench corrigido (2026-10-31):** a falha não era do tap. O `pmtud_probe.py` nunca matava os injetores: o `pgrep -f "... d={}"` é um regex inválido e falhava sempre; os injetores ficavam vivos respondendo com Packet Too Big aos pacotes de 1500 da rodada seguinte, e o AROS fragmentava tudo a 1280 (o filtro `ip6 and tcp` do `run_tcp.py` escondia os PTB). Agora o probe mata o injetor pelo PID, os dois benches matam injetores perdidos no início (padrão `p\.inject_(ptb|needfrag4)\(`), o injetor tem prazo absoluto, e o `run_tcp.py` captura ICMPv6 e informa `sanity` (PTB recebidos, fragmentos enviados). Logs em `logs/2026-10-31/bench-stray-injector/`. **Regras (Kal, 2026-10-31):** mudanças no AROSTCP vão num PR agrupado por trabalho coerente; cada mudança é **um** commit (teste + fix juntos); um bump só, no último commit; trabalho novo do tema entra no PR aberto.

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

**Terceiro grupo (2026-11-01):** #2006 mesclado (0b819a59f1, 5.21). [#2011](https://github.com/aros-development-team/AROS/pull/2011) aberto: black hole do PMTU no TCP; RFC 3542 §11 + `IP_DONTFRAG`; ECN aceito por padrão (v4/v6), com correções achadas pelo bench (CE não ecoado, ECE em ACK puro ignorado, CWR a cada ECE); campo ECN para UDP (`IPV6_TCLASS` era ignorado), ancillary data em multicast IPv4; 4 commits, 5.22 / v0.61; 27 suítes. Evidência em `research/logs/2026-11-01/pr-group3/`. Próximo grupo (4) só depois do merge.

**Quarto grupo (2026-11-01):** #2011 mesclado (f6513c6801, 5.22); o Kal fez o 8b16329595 (RFC 6724, 5.23). [#2023](https://github.com/aros-development-team/AROS/pull/2023) aberto: keepalive por conexão, `TCP_USER_TIMEOUT`, timer lento (ticks perdidos), localhost (RFC 6761), `SO_TIMESTAMP`/`SO_TS_CLOCK`, `MSG_DONTWAIT`, base networks em ordem de host, estouro do `inet_network()`, `in_canforward()` (rede 127), `ObtainInterfaceList()`/tags do `QueryInterfaceTagList()`, teste de regressão UDP; 11 commits, 5.24 / v0.63; 36 suítes; Codacy ok. Evidência em `research/logs/2026-11-01/pr-group4/`. Grupo 5 só depois do merge.

**Revisão do Kal no #2023 (2026-11-01):** quatro pontos, todos corrigidos e juntados aos commits de origem (force-push): o relógio do `TCP_USER_TIMEOUT` não parava quando o SYN era confirmado (conexão cliente ociosa caía; teste novo: par ocioso, opção antes e depois do `connect()`); `TP_UTO_TICKS()` estourava em 32 bits; `TP_MAXIDLE()` acima de 32767 (limitado a 32766, não 32767, por causa do `t_idle` saturado); `IFQ_DestinationAddress`/`IFQ_BroadcastAddress` pelas flags. Achado ao refazer o bench: keepalive com user timeout caía uma sonda tarde (`t_idle` incrementado depois dos timers). `MSG_DONTWAIT` no `sblock()` fica para depois (grupo 6). Respondido no PR; Codacy ok.

**Grupo 5a (2026-11-01):** #2023 mesclado (8d0c904eae, 5.24). [#2031](https://github.com/aros-development-team/AROS/pull/2031) aberto, 7 commits, 5.25 / v0.64: G18d (SLAAC pelos tempos de vida do prefixo), busca do resolver em todos os domínios (`RES_DNSRCH`, achado no DNSSL), RDNSS/DNSSL (RFC 8106) na DynDB por interface, G18b (Redirect só do primeiro salto), flags do NA em ordem de rede (achado pelo bench do G18a: em little-endian todo NA perdia S/O/R), G18a (roteador por alcançabilidade, round robin, sonda RFC 4191 §3.5), G18c (prefixo por interface, rota na interface certa). 42 suítes nas duas execuções; benches `tests/ipv6/defrouter.py` (novo), `rfc4191.py` (expectativa da fase 4 corrigida: o /48 de A cobre 12::), S0, UDP grande, jumbo. Bancada com segunda tap (`tools/tap-up.sh 1`, `AROS_TAP2_IP`). Evidência em `research/logs/2026-11-01/pr-group5a/`. Achados para o 5b no plano. 5b só depois do merge.

**Revisão do Kal no #2031 (2026-11-02):** mesclado (8355df7838, 5.25) com três comentários. Os dois primeiros em [#2050](https://github.com/aros-development-team/AROS/pull/2050) (5.26 / v0.65): o Redirect só substitui rota de host `RTF_DYNAMIC` (a estática fica, como no FreeBSD); `ndb_ra_server()`/`ndb_ra_domain()` com `AttemptSemaphore()` (no 5.25 um cliente segurando o lock via `ClearDynDomain()` travava a pilha em splnet e o próprio teste nunca voltava). O terceiro (tempos de vida pelo `GetSysTime()`) fica para o grupo 7: nd6 inteiro no relógio monotônico. 42 suítes ok. Evidência em `research/logs/2026-11-02/pr-5a-followup/`. 5b depois do merge do #2050.

**Grupo 5b (2026-11-02):** #2050 mesclado (6f9867b96c, 5.26). Kal comentou no #2050: `ifnet_clear_dns()` ainda bloqueava a pilha. [#2053](https://github.com/aros-development-team/AROS/pull/2053) aberto, 11 commits, 5.27 / v0.66:
- G18f (`IPV6_PKTINFO` ganha do endereço vinculado e precisa ser nosso);
- G18g (`connect()` a grupo sem zona pelo `IPV6_MULTICAST_IF`; G18h documentado como zona default);
- G18i (`SO_BINDTODEVICE` em IPv6, zona no `sendto()`, entrada unicast filtrada);
- interface removida sob sockets (use-after-free: `INP_BOUNDGONE`, `ENXIO`, TCP fechado);
- `SIOCGIFAFLAG_IN6` + sinal no fim do DAD;
- teste do sinal de endereço;
- NA com R limpo tira o roteador (§7.2.5);
- NS a cada RetransTimer e probe unicast;
- MSS sem arredondamento a 2048 (4000: +45%);
- `NAMESERVER` IPv6;
- fila de operações da DynDB (o comentário do Kal, mais `ifnet_set_dns()`/`dyndb_flush()` no reload).

48 suítes ok nas duas execuções; benches novos `bindgone.py`, `dnsgone.py`, `nameserver6.py`; `defrouter.py` com forwarding na tap. Evidência em `research/logs/2026-11-02/pr-group5b/`. Próximo: grupo 6 (TCP), depois do merge.

**Revisão do Kal no #2053 (2026-11-02):** a entrada TCP não olhava a interface vinculada (listener com `SO_BINDTODEVICE` aceitava por qualquer interface; um com a interface removida continuava aceitando). Corrigido nos dois commits de origem (`in6_pcblookup()` com a interface; `tcp_boundif_pcb()` para IPv4; `INP_BOUNDGONE` na entrada TCP), casos novos no `cunit-net-bindtodev6` e no `bindgone.py`; force-push, corpo atualizado e resposta no PR.
- **Achado, fora do PR:** remover uma interface por reload às vezes derruba a pilha (sinal 11 logo depois de "interface detached", ~1 em 5-8 execuções do `bindgone.py`). Mesma instrução e mesmo padrão de memória liberada no 5.26 e no 5b: anterior ao grupo.

**#2053 mesclado (c388bc08e9, 5.27). Crash de remoção (2026-11-02):** causa na AROSTCP. O pedido `S2_ONEVENT` que o driver recusa (tap.device: `IOERR_NOCMD`) ou que não é reenviado após `S2EVENT_OFFLINE` ficava fora de toda lista, ainda `NT_REPLYMSG`; o `WaitIO()` do `sana_unrun()` fazia um segundo `Remove()` por links velhos, corrompendo a lista do `SanaPort` (crash no `GetMsg()` do `sana_poll()`) ou o heap (TLSF: "free-list corruption at REMOVE_HEADER", mesma mensagem do ISSUE-0037 do Bellatrix, outra causa: no x86_64 o alinhamento de 16 já garante o MIN_PAYLOAD). Correção: `sana_connect()` libera o pedido. [#2067](https://github.com/aros-development-team/AROS/pull/2067), 5.28 / v0.67; bench `tests/ipv6/remloop.py`: 0/16 boots caem com a correção, 7/9 sem; 48 suítes ok.
- Achado em paralelo, **não demonstrado**: corrida no tap.device (iotask preenche uma leitura sem lock enquanto `abort_io()` pode respondê-la). Patch guardado em `research/logs/2026-11-02/removal-crash/tap-race-fix.patch`; só vira PR se for demonstrada (p.ex. alargando a janela).
- Ferramentas de depuração: `tests/debug/segmap.c` (onde está o código de cada módulo, via `debug.library`) e um dump de pilha local no trap handler do hosted (não commitado; patch é trivial).

**#2067 mesclado (eebbac3697, 5.28). Grupo 6a (2026-11-03), branch `review/arostcp-series6a`:**
- `0a92fffe97` `sblock()` sem esperar com `MSG_DONTWAIT`/`SS_NBIO` (Kal no #2023). Só se demonstra quando o `MSG_WAITALL` pede mais que o buffer (`sb_hiwat`, arredondado ao MSS no connect): só então dorme segurando o lock. `cunit-net-sblock`: 5.28 falha 2/3, com a correção 3/3 nas duas execuções.
- Flags `SOL_SOCKET` fora do splnet: **conforme**, nada a fazer. A API é serializada pelo `syscall_semaphore`, e a tarefa da pilha só lê `so_options` (palavra inteira; `sonewconn()` copia).
- `2944f4a195` um RST antes da janela não fecha mais a conexão: o 4.4BSD aparava o segmento à janela antes de olhar o RST (RFC 9293 §3.10.7.4).
- `98224d7735` RFC 5961 (R2, descrever em alto nível): challenge ACK para RST na janela fora do RCV.NXT exato, SYN em estado sincronizado e ACK mais velho que SND.UNA − max_sndwnd; limite de 5/s por conexão (`t_challenge_*` no fim do `tcpcb`).
- Bench novo `tests/tcp/rst_probe.py` (injeta pela tap via AF_PACKET; modo `hold` no `tcpbench`): 5.28 falha 4/7 (o RST velho derruba; dados injetados com ACK velho são aceitos), A falha 4/7 (só corrige o velho), A+B passa 7/7; os controles (`exact`, `beyond`) são verdadeiros nos três. 10 RSTs → 5 challenge ACKs.
- Regressão: 48 suítes ok com A+B; `run_tcp.py` igual ao 5.28 (variação de RTO de 1,5-4 s nos dois). Evidência em `research/logs/2026-11-03/pr-group6a/`.
- `c4c87d49a3` TSval = `tcp_now` + deslocamento por conexão (hash com chave própria `tcp_ts_key`, de `kern_random()`/`arc4random_buf()`; `sc_tsoff` no SYN cache). Bench `tests/tcp/tsval_probe.py`: no 5.28 os 10 SYNs ficam a 9..13 ticks do boot; com a correção independentes; passivo com o mesmo relógio do SYN-ACK; RTO 3/6/12 ticks igual. O stall conta no relógio do AROS (TSval): o hosted às vezes para ~2,4 s, o que o relógio do host contava. 49 suítes ok (com `sblock`).
- `1de2b52061` SipHash-2-4 (`tcp_conn_hash()`) para ISN, cookies, buckets do SYN cache e TSval: endereços inteiros (sem dobrar o IPv6), byte de uso. Vetores de referência ok (0/8/15/63). Cookies testados com build local só-cookies (`tcp_syncookiesonly = 1`, não commitado): 49 suítes ok, 200 kB pela tap, SYN-ACK só com MSS. Revisão dos cookies: conforme; o comentário da janela dizia 3 s (são ~6 s). Limitação documentada: conexão por cookie perde wscale/SACK/TS (o FreeBSD guarda no TS; possível depois).
- Bump 5.29 / v0.68 no último commit. Bisect: os 5 commits compilam sozinhos sem avisos; cppcheck sem achados novos (5 a menos). flawfinder não rodou localmente (download bloqueado pelo modo automático): conferir no Codacy.
- **PR [#2078](https://github.com/aros-development-team/AROS/pull/2078) mesclado** (`58cdb8bac5`, 5.29 / v0.68, sem comentários) (grupo 6a). Corpo em `research/logs/2026-11-03/pr-group6a/pr-body.md`. Próximo: 6b (bench de perdas, auditoria do scoreboard SACK, PRR) depois do merge.

**Grupo 6b (2026-11-03), branch `review/arostcp-series6b` (de `58cdb8bac5`):**
- Bench novo `tests/tcp/loss_probe.py` (1 MB por cenário, IPv6 LL, ACKs atrasados 20 ms; todo o shaping montado antes do boot, cada cenário na sua porta): `random` 1/50, `partial` (contadores 100/101/103: vários buracos por janela), `lostrexmit` (filtro u32 pelo número de sequência derruba original e 1ª retransmissão), `reorder` (netem `reorder 100% gap 10` por ifb). Métricas: tempo, retransmissões, desnecessárias (dados já ACK/SACK num ACK visto ≥5 ms antes), 3+ cópias, timeouts, ACKs com 2+ blocos. Autochecagens: partial com SACK múltiplo, lostrexmit com 3 cópias do alvo, reorder com SACK do host. Consertos do bench no caminho: shaping no accept chegava tarde (transferência de 0,2 s), handle u32 fixo colidia, reorder aleatório às vezes não reordenava, métrica sem margem contava corridas de leitura do hosted.
- **Defeito 1 (demonstrado):** `tcp_input()` só contava ACK duplicado com a mesma janela (RFC 5681); o Linux aumenta a janela a cada ACK, então nenhum dupack contava e toda perda esperava o RTO. Com SACK, ACK que SACKa dados novos conta (RFC 6675 §2). 5.29 → correção: random 12,5 s/6 timeouts → 0,32 s/0; partial 10 s/6 → 3,8-6,2 s/1. Binário `ab/AROSTCP.d0`.
- Achados de leitura, a demonstrar: com PRR desligado (padrão) a recuperação é NewReno puro, o SACK não escolhe o que retransmitir (no reorder, cada ACK parcial reenvia o próximo segmento ainda em trânsito); com PRR ligado o `tcp_sack_nextseg()` não tem HighRxt (reenviaria o mesmo buraco a cada dupack) e `delivered` é 1 MSS fixo; `pipe` sem IsLost; placar de 4 blocos descarta o mais baixo; `MAX_SACK_BLKS` definido 6 em `tcp.h` e 4 em `tcp_var.h`. Depois do RTO reenvia dados SACKados (partial: 2-5 desnecessárias).
- `lostrexmit` ~1,5 s com 1 timeout nos dois (sem RACK, esperado). `reorder` com deslocamento ~15 segmentos: referência para o grupo 7 (RACK/D-SACK), não critério do 6b.
- Rebase sobre `c4ff508861` (inclui `d6425105cc` do Kal: ACK avulso em LISTEN recebe RST; 5.30 / v0.69). Bump do 6b será 5.31 / v0.70.
- Commits: `b354478278` dupack com SACK (refinado: com blocos SACK, só conta se SACKa dados novos; D-SACK não conta — numa captura, 3 D-SACKs abriram recuperação nova que reenviou o recém-reenviado), `3902a90843` recuperação SACK RFC 6675 (IsLost/SetPipe/NextSeg, HighRxt, placar 32 descartando o mais alto, ACK parcial sem volta do NewReno, PRR só com SACK e DeliveredData medido), `6981396187` PRR ligado + sysctl `net.inet.tcp.prr` (teste no `cunit-net-sysctl`). 49 suítes ok (r4).
- PRR antes da correção (d1): 1928 segmentos para 715, 853 desnecessárias. Depois: random/partial 0,32 s, 0 desnecessárias, 0 cópias 3+; reorder espúrias ~120-270 (grupo 7). Paradas do hosted (~1,7 s sem pacote e TSval parado) agora marcadas como STALL no bench.
- Checagem RFC 6582 §3.2 (recover) testada nos dois caminhos e desfeita: não demonstrada com SACK e prejudicaria fast retransmit legítimo no ponto de recuperação. Fica para o caminho sem SACK, se demonstrada (`--nosack`).
- Bench `tests/tcp/dupack_probe.py` (determinístico): queda no ingress mantém ~130 KB em voo, injeta 3 ACKs a partir do último ACK real (seq/ack/janela/TS) e observa 300 ms. dsack (só D-SACK) não pode retransmitir; newsack (SACK de dados enviados e não confirmados) e samewin (sem SACK, mesma janela) têm de retransmitir (controles). Até 3 tentativas por caso (janela do host fechada invalida a tentativa). p0 (5.29) e r2 (commit original) falham o dsack; r4 passa; controles ok sempre. Consertos do bench: transferência acabava antes da queda; captura AF_PACKET atrasada em relação ao fio (agora drena tudo após a queda, buffer 16 MB).
- Sugestões (ChatGPT, via usuário) aceitas: `--nosack` com restauração garantida e trava; SACK do receptor RFC 2018 (primeiro bloco = segmento que disparou o ACK; hoje do mais baixo, até 3); `rst_probe` para o commit do Kal só no aros-matter; A/B final do PRR pelo sysctl; evidências antes/depois classificadas (demonstrado e corrigido / já conforme / não reproduzido).
- **PR [#2085](https://github.com/aros-development-team/AROS/pull/2085) aberto** (grupo 6b, 5.31 / v0.70): `b354478278` dupack com SACK (D-SACK não conta), `4b02ee0d44` recuperação SACK RFC 6675, `a6ebd27b01` sysctl `net.inet.tcp.prr` (**PRR fica desligado**: A/B no mesmo binário via `tests/tcp/tcpctl.c` deu empate em todos os cenários; decisão do usuário: desligado + sysctl, ligar só com medição que mostre ganho, p.ex. perda em rajada no grupo 7), `fbe07ddde5` SACK do receptor RFC 2018 (primeiro bloco = segmento que disparou; nenhum bloco abaixo do ACK — antes 52/52 fora de ordem e 44 falsos D-SACK). Bench `tests/tcp/rcvsack_probe.py`. 49 suítes ok (k2); bisect ok; cppcheck sem achados novos (2 a menos; consertos de const/escopo/init aplicados nos commits de origem).
- Pendente (só aros-matter): `tests/tcp/listen_probe.py` escrito para o commit do Kal `d6425105cc` (stray ACK → RST seq=SEG.ACK; RST → nada; ACK errado no handshake → RST; handshake certo → dados confirmados, controle), ainda não rodado.
- #2085: Codacy acusou 3 (cppcheck mais estrito que o local: negativeIndex falso positivo na macro TCP_SACK_ADD → função `tcp_sack_addblk()`; variableScope de `end` e `sent`). Corrigido nos commits de origem (fixup), force-push (`0bcf190766`); benches iguais; Codacy passa, 0 novos. Lição: o cppcheck local não substitui o do Codacy.

**#2085 mesclado (2026-11-04).** Comentário do Kal (não bloqueante): `tcp_sack_rcvblocks()` quadrático (um `tcp_sack_run()` por segmento, cada um do início da fila; ~10k passos com 100 segmentos) e `tcpcb` +224 bytes com o placar de 32. Follow-up [#2099](https://github.com/aros-development-team/AROS/pull/2099) (5.32 / v0.71): `755c491faa` uma passada por faixa até `MAX_SACK_BLKS`; `9bfd3d098f` custo anotado em `TCP_SACK_BOARD`. 49 suítes ok; `rcvsack_probe` sem bloco abaixo do ACK. Dois ACKs com primeiro bloco que não é o mais alto: em ambos o segmento recebido por último está no primeiro bloco (Linux mandou um segmento mais baixo por último) — conforme a RFC 2018; a métrica `first_block_not_highest` supõe chegada em ordem crescente e deve ser lida assim.

**IP_RECVTTL (2026-11-04), branch `review/arostcp-recvttl`, commit `8f4d7f34b1` (5.33 / v0.72), PR [#2105](https://github.com/aros-development-team/AROS/pull/2105) aberto:** pedido da auditoria do mDNSd/Bonami (TTL 255, RFC 6762 §11). Lacuna confirmada no upstream `6fabae71cb`: IPv6 tem `IPV6_RECVHOPLIMIT`, IPv4 não tinha `IP_RECVTTL`. **ABI (decisão do usuário): convenção FreeBSD** — `IP_RECVTTL` = 65, `cmsg_level IPPROTO_IP`, `cmsg_type IP_RECVTTL`, payload `u_char` (1 byte), coerente com `IP_RECVTOS` (68, 1 byte); o número Linux 12 já é `IP_ADD_MEMBERSHIP` no AROS. `CMSG_LEN(1)` = 17 / `CMSG_SPACE(1)` = 32 no x86_64 (`AROS_WORSTALIGN` 16), 13/16 no m68k; `recvmsg()` (amiga_sendrecv.c) corta com `MSG_CTRUNC`. TTL do cabeçalho como chegou (`save_ip` antes do `ipovly` zerar `ih_x1`; remontagem guarda o cabeçalho intacto em `ipqe_ip`). Só UDP (TCP não tem TTL por mensagem; raw IPv4 não entrega nenhum dado ancilar hoje). Arquivos: `in.h`, `in_pcb.h` (`INP_RECVTTL` 0x80 em `INP_CONTROLOPTS`), `ip_output.c` (`ip_ctloutput` set/get), `udp_usrreq.c` (`udp_savecontrol`), Readme, `cunit-net-cmsg` (+4 testes, multicast confere TTL). Antes: 5/12 falham; depois 12/12 (125 asserts), nas duas execuções.
- **Dependência para o mDNSd:** ler `IP_RECVTTL` com `cmsg_type == IP_RECVTTL` e `*(u_char *)CMSG_DATA(c)` (não `IP_TTL`/int); exigir bsdsocket.library ≥ 5.33. IPv6: `IPV6_RECVHOPLIMIT` → `IPV6_HOPLIMIT`, int (RFC 3542).
- Candidato (não planejado): dados ancilares em sockets raw IPv4 (`IP_RECVDSTADDR`/`TOS`/`TTL` no `rip_input()`, como o `ip_savecontrol()` do FreeBSD), útil a ping/traceroute; só se pedido.
- Build: `config.status --recheck` foi preciso após `2ecaeb33fc` (configure mudou no master); taps somem quando o WSL reinicia (`tools/tap-up.sh`).

**#2105 mesclado (2026-11-05, `f4a4deec2d`).** Depois dele entrou o #2116 (cabeçalhos UDP/IPv6 contíguos) e commits do Kal (bases compartilhadas, 5.36 / v0.75).

**Grupo 7a (2026-11-07), branch `review/arostcp-nd6-monotonic` (de `492163d979`, 5.36), PR [#2153](https://github.com/aros-development-team/AROS/pull/2153) aberto:** relógio monotônico, o primeiro item do grupo 7 (Kal no #2031). Três commits, 5.37 / v0.76:
- `423365096d` Neighbour Discovery em `GetUpTime()`: estados de vizinho, roteadores, prefixos, RIO, endereços SLAAC/temporários, DAD/RS, servidores e domínios do RA (`ndb_ra_now()`). Nada disso sai para o usuário como hora do dia; o `in_var.h` já dizia "seconds since boot".
- `b18e5764fa` `rmx_expire` em uptime; `rt_expire_out()`/`rt_expire_in()` convertem para hora Unix UTC no routing socket (RTM_GET, NET_RT_DUMP, RTV_EXPIRE) e no `GetRouteInfo()`, como o rtsock do FreeBSD. Antes saía o `GetSysTime()` (época 1978, hora local); `ip -d route` mostrava esse número como "segundos restantes", agora mostra o que falta. `cunit-net-pmtu4/6` comparam com `time()`.
- `8feb79de63` cache do resolver em `GetUpTime()`; `dnstest.h` ganha TTL por registro (dois nomes novos com 600 s e 3 s; os outros seguem TTL 0).
- Suíte nova `cunit-net-clockstep` (TR_SETSYSTIME ±1 dia, restaura a cada caso; o primeiro caso confere que o passo move só o `GetSysTime()`). 5.36: 5/6 falham; cada commit vira os seus casos. Evidência em `research/logs/2026-11-07/pr-group7a/`.
- `netstat -r` (lê a memória da pilha, kvm) compara com `CLOCK_MONOTONIC`, como o FreeBSD com `CLOCK_UPTIME`; antes a expiração ficava sempre no passado e a linha saía sem interface e sem Expire. Não mudados: o que é hora do dia (timestamps ICMP, BPF, `if_lastchange`, logs) e o ritmo do ARP (diferença sem sinal).
- **netstat e libkvm:** `kvm_openfiles()` exige que o `SBTC_RELEASESTRPTR` da pilha seja igual ao `STACK_RELEASE` da libkvm (versão do kernel **e data**). Ao testar uma pilha nova, recompilar `arostcp-linklibs-kvm` e `workbench-network-common-c-netstat` junto; senão `kvm_open: Wrong bsdsocket.library version` (no stderr), rc=1.
- 50 suítes ok nas duas execuções (5.36: só os casos novos/alterados falham); cada commit compila sozinho sem avisos; cppcheck sem achados novos.
- **Bancada:** a imagem `~/aros-build-ipv6-hosted-claude` tinha a CRT de 30/10; programas compilados depois do `956444232f` (errno por thread) saíam com rc=20 sem saída (`ip`, `netstat`). Recompilar `compiler-stdc`, `compiler-posixc`, `compiler-stdcio` ao trazer o master.

**#2153 mesclado (2026-11-07, `65873a4272`, 5.37).**

**Grupo 7b (2026-11-07), branch `review/arostcp-rtt-ms` (de `65873a4272`), 5.38 / v0.77, PR [#2155](https://github.com/aros-development-team/AROS/pull/2155) aberto:** item 1 do grupo 7, [nota de desenho](research/2026-11-07-tcp-rtt-rto-design.md). Três commits:
- `TCP_INFO` (o header declarava, o `tcp_ctloutput()` recusava): estrutura do FreeBSD, num cluster. Teste novo `cunit-net-tcpinfo`.
- RTT e RTO em ms: `tcp_ms()` (`GetUpTime()`) é o relógio do TSval e das amostras; SRTT/RTTVAR do FreeBSD (escala 32/16); RTO = SRTT + max(G, 4·RTTVAR); piso `net.inet.tcp.rexmit_min` 200 ms (**decisão do usuário**: desvio do SHOULD de 1 s da RFC 6298 §2.4); RTO inicial `rttdflt` 1 s (era 6 s), 3 s após SYN retransmitido (§5.7); SYN-ACK 1/2/4/8 s; REXMT como prazo (`t_rexmt_at`) checado no tick rápido (~60 ms, `UNIT_VBLANK`: uma contagem ficava 20% atrasada).
- IW10 para todo destino: o `if(!local)` do 4.4BSD deixava destinos da LAN sem slow start (cwnd 1 GB).
- Medido (benches novos `tests/tcp/rto_probe.py`, `cwnd_probe.py`): RTO 1,28/1,16/2,36/1,76 s → 0,24/0,20/0,26/0,56 s (RTT 0,4/50/200/500 ms); jitter 200±100 → 0,59 s sem espúrias; SYN 5,8 → 1,0 s. `loss_probe`: retransmissão perdida 1,68 → 0,55 s; com slow start, perda aleatória 0,33 → 1,34 s (esperado). 51 suítes ok nas duas execuções; bisect sem avisos; cppcheck sem achados novos. Evidência: `research/logs/2026-11-07/rto-granularity/`, `cubic-curve/`, `pr-group7b/`.
- **CUBIC em ms: descartado** — com o IW corrigido a curva já segue a RFC 9438 a 1-2 MSS (sem ganho para A/B).
- Achados para depois: `sb_max` 512 KB e `SO_SNDBUF` padrão 128 KB limitam a janela em caminhos longos; o tick rápido é ~60 ms (`UNIT_VBLANK`).
- **Próximo:** HyStart++ (RFC 9406), agora que a LAN tem slow start; depois RACK-TLP.

**Grupo 7c (2026-11-07), branch `review/arostcp-ss-hystart` (sobre o #2155), PR só depois do merge do #2155 (decisão: escopo separado, um PR AROSTCP por vez):**
- `cb21745794` ABC (`tcp_ss.c`, sysctl `abc_l`, padrão 1 = RFC 5681; L=2 dava 30-50% mais descartes no `ss_probe`).
- `75d2a1d719` HyStart++ (RFC 9406, sysctl `hystart` = 1). A/B isolando a detecção (L=8 sem detecção): descartes 100 KB 82/78 vs 190/169, 256 KB 62/64 vs 167/166; sem gargalo não sai cedo; fila de 1 MB sai pelo CSS sem perda.
- **Sem commit (working tree):** correção do CUBIC (`origin_point = cwnd` quando cwnd ≥ W_max, RFC 9438 §4.10): CA nos 5 s após a saída do HyStart++ cresce 7-16 → 40 MSS. E o caso CUnit `cunit-net-tcpinfo` "a route's ssthresh reaches a new connection" (passa 12/12: as métricas de rota chegam ao TCP no loopback v4/v6).
- Teste isolado do CUBIC (sem HyStart++) via `ssthresh` de rota na tap falhou: `tests/tcp/rtssthresh.c` muda `fe80::/64` (rc=0) mas a conexão não herda — hipótese: rota do vizinho clonada antes. Próximo: mudar a rota do próprio vizinho (ou criá-la antes) e confirmar.
- Fila de prioridades (com sugestões do ChatGPT via usuário): P0 fechar 7c; P1 métricas de rota (rota clonada/zona; comando `route` sem `-prefixlen`/zona) e stretch ACK na tap (loopback mostrou 12 segmentos em 2 ACKs, não conclusivo); P2 timers em `UNIT_VBLANK` (~60 ms; medir cadência antes/depois); P3 buffers (`SO_SNDBUF` 128 KB, `sb_max` 512 KB; medir RTT × buffer antes de autotuning, com limite global); P4 RACK-TLP; P5 pacing. Ferramentas (`netstat`/libkvm exige release idêntica; `route` IPv6) em frente paralela.
- Benches novos: `tests/tcp/ss_probe.py` (gargalo tbf via ifb; modos por sysctl; RTT/vazão da captura), `rtssthresh.c`; `sink` com thread por conexão (a de um boot anterior nunca fecha e travava a seguinte).
