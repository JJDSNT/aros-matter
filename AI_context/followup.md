# Acompanhamento — correções, verificação e regressão

Pedido do usuário (2026-11-11): tudo anotado para acompanhar o que foi corrigido ou não, sem regressão e sem
nada deixado de corrigir. Este é o painel; o detalhe de cada bug fica em [bugs.md](bugs.md).

**Regra:** um item só sai daqui (estado **fechado**) quando: (1) a correção está no upstream (commit/PR
anotado); (2) foi verificada por nós no hosted **e**, se o item toca o m68k, no Amiga emulado; (3) existe um
teste que falharia se o defeito voltasse (anotado na coluna "Teste de regressão") e ele roda na nossa suíte.


## Um PR com as pendências do AROSTCP (decisão do usuário, 2026-11-12)

Branch `review/arostcp-pending` (worktree `~/AROS-pr2218`, sobre `review/arostcp-ipv4-acd`): os 3 commits do #2218 +
`IP_RECVIF`, B36, B37 (cherry-pick sem conflito). Falta: **portar o B5** (`11df4517ea`, cache de vizinhos IPv6 por
interface) para a pilha modular — o `rtsock.c` está no `admin.atcp`, o `amiga_roadshow.c` foi repartido, a queda de
enlace é `NFE_LINKDOWN`: o ND6 é alcançado pelos ganchos da família IPv6, não por chamada do núcleo; e o B30. Depois:
se o #2218 ainda estiver aberto, tudo entra nele (um comentário explicando o escopo: o `IP_RECVIF` é o que foi prometido
"quando o mDNS de socket único precisar"); se já tiver sido mesclado, um PR só com o resto. Bump uma vez, no último commit.

**B5 portado (2026-11-13, não commitado ainda):** ND6 pelos ganchos da família (`NFC_LLINFO_RTMSG`/`ROWS` no
`nfo_control` do IPv6, admin sem conhecer o ND6), `rt_pmtu_update_if()` no fim do `netcore.def` (v11) com
`NFQ_GATEWAYLINK`, `nd6_lt_resolve()`, `NFE_LINKDOWN` limpa vizinhos, `nd6_deinit()` libera o cache próprio;
`netcore-update.sh`: 0 de 68 objetos de módulo chamam o núcleo; 11 suítes do B5 0 falhas.

**Critérios de fechamento do PR único** (usuário + ChatGPT, 2026-11-13):
1. bateria completa no build limpo; ✅ 66 suítes, 0 falhas, duas execuções (B5 portado, `24a5bc7ba1`);
2. **PMTU:** mesmo link-local em dois enlaces — sem corrupção entre eles, e recuperação depois que a rota dinâmica expira
   (teste novo, lendo a rota pelo socket de roteamento: a de A existe; B não é registrado; a de A some; B cria a sua no
   enlace de B com o MTU certo; tabela de rotas com zona fica como pendência à parte);
   ✅ (2026-11-13) `cunit-net-pmtu6` "the same link-local destination on two links" (rota de A apagada como na
   expiração): A 1400 na interface 2; B não registrado enquanto A existe; B 1300 na interface 3 depois. Bench
   `tests/ipv6/pmtu_expiry.sh` com a **expiração real** (600 s): A 1400/if 2 → rota de A sumiu → B 1300/if 3, PASS;
3. **ABI v11:** ✅ (2026-11-13) núcleo novo + módulos v10 (build da linha mDNS, hashes conferidos): carregam e as suítes
   que passam pela tabela de serviços dão 0 falhas (udp, inet6, addr6, adminmod, module, cmsg, mcast6, scope6,
   localhost); só o caso link-local do `pmtu6` falha, funcionalidade do B5 que o `inet6` antigo não tem. Núcleo v10 +
   módulos v11: "module library netconfig.atcp needs version 11 of the stack's services; this stack has version 10",
   a pilha não sobe, o sistema não trava;
4. **memória do B5 no m68k:** repouso/carga e cache com 0, 64 e 256 vizinhos: absoluto e por entrada, e mais uma
   medição depois que as entradas expiram (memória retida). **Contar antes de calcular:** ler o cache
   (`GetRouteInfo` com `RTF_LLINFO`, e o contador de estados no teste) e confirmar quantas entradas existem, por
   interface. O limite é **por interface** (`nd6_maxnbrs` 256 em cada uma das 16 primeiras, mais 256 compartilhadas
   acima disso: pior caso teórico 4.352 entradas): medir com 256 em um enlace e em dois. Se o pior caso medido for
   inaceitável no m68k, é defeito demonstrado (memória esgotada por enxurrada de NS) e a correção é um teto global além
   do por interface (como o `gc_thresh` do Linux);
   **Resultado (2026-11-13, `tests/ipv6/nd6_mem.py`, A3000 emulado, pilha do #2218; nd6mem-m68k-050623):** NS de N origens
   falsas, entradas contadas (`GetRouteInfo`) 1 s depois, memória livre e `netstat -m` a cada passo, 15 s de
   expiração entre passos. Entradas 64 / 234 / 256 (300 enviadas: o teto segura) / 236 na 2ª rodada de 256.
   Tomado do sistema em relação ao repouso: 64 → 24 B; pico com 256 → 182,6 KB; depois da expiração 116,6 KB;
   2ª rodada → 116,6 KB (nem pico nem patamar sobem: sem vazamento). O patamar retido é o pool de mbufs
   (`netstat -m`: 96 → 210 KB tomados para mbufs e clusters, +114 KB, pelo tráfego da enxurrada: NA e 3 sondas
   por entrada), que por desenho não é devolvido e no m68k tem teto (MAXMEM 1 MB). O custo das entradas é
   transitório (~66 KB com 256, devolvidos ao expirar). Uma enxurrada se limpa sozinha: sem resposta às sondas,
   cada entrada sai em ~8 s (RFC 4861 §7.3.3). Hosted: 0 B em todos os passos (pool pré-alocado).
   **Decisão (usuário, 2026-11-13):** sem teto global no #2218 — seria política nova de recursos (repartição
   entre interfaces, reação no limite, por plataforma); relatar ao Kal as opções (manter 256 por interface, ou
   política global/por plataforma depois). Só um vazamento ou crescimento ilimitado seria defeito a corrigir.
5. **saída IPv4 do mDNS**, com captura nas duas interfaces: QU em eth1 respondida por eth1 com a rota preferida em eth0;
   dois enlaces IPv4LL; interface com dois endereços (origem = anunciado); nenhuma cópia pela outra interface; uma
   interface só continua certa;
   **Resultado (2026-11-13, `tests/mdns/ipv4_out.py`, imagem da linha mDNS, um socket por família):**
   - `route`: **falha.** QU e legado saíram por aros0 com origem 192.168.166.2 (o A diz 192.168.167.2); o QM saiu
     certo por aros1. Defeito confirmado.
   - `ll`: a resposta legada **não saiu** (nem ARP). Causa: o autoip do master com duas interfaces IPv4LL deixa
     `default (0) U eth1` e nenhuma rota 169.254/16 (B38; o commit do ACD já corrige: na imagem do #2218 a tabela é
     `169.254 U eth0`). Mesmo corrigida, 169.254/16 é roteada por uma interface só (RFC 3927 §3.2): o responder de um
     socket precisa forçar a interface de entrada — o mdnsd antigo (socket por interface) acertava na imagem do #2218.
   - `alias`: **passa.** Toda resposta saiu por aros0, com origem de eth0 e só os A de eth0 (.2 e .50).
   Conclusão: item 6 confirmado.
   **Depois do `IP_PKTINFO` (2026-11-13, `5fc25bc8c4` no #2218; mdnsd `d8163cc691` na linha mDNS rebaseada sobre
   ele):** `route`, `ll` e `alias` passam: QU e legado saem pela interface perguntada, com a origem dela (ll:
   169.254 de eth1 com a rede roteada por eth0), sem cópia na outra. Regressões mDNS: `dnssdtest` 68/68, interop
   TWO=1 (cada enlace vê o seu endereço), fixtures do Codex 44/45/16.
   Ambiente: o Windows do WSL também se chama `palerma` e ganhou o nome no mDNS (Avahi virou `palerma-2`); os
   scripts `dnssd.sh`/`interop.sh` pegam agora o nome que o Avahi tem em aros0.
   Custo no m68k do `IP_PKTINFO` (build do commit anterior `5ea3ea051b` contra `5fc25bc8c4`): `inet.prot` +964 B;
   núcleo e demais módulos iguais. Bateria completa: 67 suítes, 0 falhas nas duas execuções.
   **PR inteiro contra o master no m68k (`fa21d0c38e` vs `64d00bf2da`):** núcleo +376 B, `admin.atcp` +252 B,
   `inet.prot` +5.028 B, `inet6.prot` +9.076 B, `dhclient` +2.208 B; `transport.prot` e os demais iguais.
   Versão 5.46 (kernel v0.85) movida para o último commit (13.11.2026). Codacy: `const char *end` no teste do
   pmtu6 e `memset` no `IP_RECVIF`, dobrados nos seus commits; `cunit-net-pktinfo` passou a usar .77 (ninguém) —
   o host respondia ao porto 9 e o ARP dele fazia a entrada (corrida vista na 2ª execução).
6. **feito** (`5fc25bc8c4`, `cunit-net-pktinfo` 8 testes): **`IP_PKTINFO` bidirecional** (envio: interface e origem forçadas, não só influência na rota;
   recepção: `IP_RECVPKTINFO`), `struct in_pktinfo` do Linux (`ipi_ifindex`, `ipi_spec_dst` = endereço local da
   interface de entrada, `ipi_addr` = destino do cabeçalho, ex. 224.0.0.251; no envio `ipi_spec_dst` é a origem),
   constante livre documentada; `IP_RECVIF`/`IP_RECVDSTADDR`/`IP_RECVPKTINFO` como
   vistas da mesma informação de recepção (`in_savecontrol`), sem segunda implementação; CUnit próprio; mdnsd consome;
7. mensagem do commit do `IP_RECVIF` corrigida (não basta sozinho).

**Enviado ao #2218 (2026-11-13):** força-push `67f7666bfd` (8 commits), descrição e título novos, comentário consolidado (correções comprovadas / limitações / custo com a tabela do ND6; teto global deixado ao Kal; B39 e B40 só descritos, PRs separados). mdnsd rebaseado: `cff8996a8d`. Aguarda o Kal.

**3ª revisão do Kal no #2218 (2026-11-13) — respondida, força-push `60a074e222`:** 1) protótipos (64-bit: `in_readyia` truncado por
`cltq`) — corrigido com protótipos canônicos nos cabeçalhos donos, `-Werror=implicit-function-declaration` limpo nos
arquivos do PR; 2) só IPv6: `cmsg` era o teste (índice por socket `AF_INET`, do nosso commit `IP_RECVIF`), `acd`
LIMITS `ST_V4`, `pmtu6` TWO_LINKS a reproduzir; 3) vizinhos estáticos mantidos no link down (e os dos nossos
endereços), tudo sai no detach — **testado pelo caminho real**: `tap.device` passou a relatar o enlace
(`review/tap-link-events` `28f608842d`, PR próprio) e `tests/ipv6/nd6_link.sh` (antes 1/1, down 1/0, up 1/0,
removida 0/0; controle sem a correção falha no down); 4) `if_fullname()` no lugar de `snprintf` (inet6.prot −6,6 KB
hosted); 5) `nd6_maxnbrs` por `AvailMem()` 16–256, limite global de pacotes retidos (descarta o mais antigo),
`nd6_maxqueuelen` em uso, netvars com faixa, `cunit-net-nd6limits`. A2065 (LANCE) não relata enlace.
Prova do ponto 1 em execução: hosted com 2 GB (RAM alta), `pmtu4` cai sem o protótipo ("Program failed") e passa com
ele. `pmtu6` TWO_LINKS **não reproduz** (só IPv6, sozinho e na bateria, memória padrão e 2 GB, tap antigo e novo: A 1400
índice 2 → B 1300 índice 3) — dito ao Kal com as condições. Baterias: dual 68/0, só IPv6 68/0 (5 IPv4 se pulam).
m68k: `inet6.prot` −6.316 B (agora +2.760 sobre o master), `inet.prot` +4.860; limites 256/256/16 no A3000; hosted 16 MB →
92. Pressão de pacotes retidos (`nd6_mem.py hold`): 512 envios → 256 entradas e 256 clusters (o teto), após expiração
clusters de volta a 32, pool fica em 796 KB (teto 1 MB). Infra nova: `tap.device` relata o enlace
(`review/tap-link-events` `6e64e46c66`, PR próprio, não enviado), `tests/tap/onevent.sh` 10/10 (direto no driver; achou o
`ln_Type` não marcado), `tests/ipv6/nd6_link.sh`. Fila depois do #2218: B40, B39, B41 (só as cópias locais de `ip6_output`). **tap: PR #2258 aberto** (`0e0171509f`, sobre o master `834490510e`). **#2218 rebaseado sobre o master `834490510e`** (o Kal tinha feito no master os mesmos protótipos: conflitos em `sana2arp.c`, `ip_output.c`, `ip_output_protos.h` resolvidos ficando com os do master; `ip_setmoptions`/`getmoptions` voltam a não-`static` como o master os declara; duplicatas nossas em `if_sana.c` e `in6_var.h` retiradas). Build sem supressão: 0 declarações implícitas, 0 avisos. Validado (nd6_link, dual 68/0, só IPv6 68/0) e enviado: `283464c0b6`, nota de rebase no PR.

**Apresentação ao Kal:** separar correção comprovada (incluindo os cenários que falhavam), limitação conhecida (zona nas
rotas de PMTU IPv6) e custo medido.

**Escopo congelado (2026-11-13):** nada além destes itens; só correções de defeitos demonstrados; resultados
consolidados para o Kal.

## Worktrees e builds (desde 2026-11-12)

Uma worktree e um build por linha de PR; a validação final de um PR roda numa imagem feita só da branch dele.

| Linha | Worktree | Build hosted | Branch |
|---|---|---|---|
| #2218 (ACD/IPv4LL/decline/NUD) | `~/AROS-pr2218` | `~/aros-build-pr2218-hosted` | `review/arostcp-ipv4-acd` |
| mDNS/`dnssd.library` (+ pilha `review/arostcp-ip-recvif` na base) | `~/AROS-ipv6` | `~/aros-build-ipv6-hosted-claude` | `review/mdnsd-canonical-links` |
| m68k (Amiga emulado) | `~/AROS-hist` (destacada) | `~/aros-build-hist-m68k` | conforme o teste |

`tools/cunit-suite.sh` e os benches tomam `AROS_SRC`/`AROS_BUILD`/`AROS_HOSTED_IMAGE`; apontar para o par certo.

## Procedimento a cada atualização do upstream

1. `git -C ~/AROS-ipv6 fetch upstream` e
   `git -C ~/AROS-ipv6 log --format='%h %ad %an %s' --date=short <último-visto>..upstream/master -- workbench/network`
   (anotar o último commit visto no fim deste arquivo).
2. Para cada commit: a que item daqui corresponde? Anotar na tabela (coluna "Onde"). Commit sem item: ler e ver
   se precisa de um.
3. Itens marcados como corrigidos pelo upstream: rodar a verificação da linha; se passar e houver teste de
   regressão na suíte, marcar **fechado**; se não houver teste, escrever (estado **falta teste**).
4. Rebasear o que está pendente nosso (B5, #2218) e rodar: 52+ suítes no hosted (`tools/cunit-suite.sh`), os
   benches da linha, e o delta de tamanho no m68k (`tools/stack-size-hist.sh` + `tools/stack-size-report.py`).
5. Ver se algum item aberto não tem dono: escolher (nós ou pedir ao usuário para combinar com o Kal).

## Itens

Estados: **aberto** · **em correção** (alguém trabalhando) · **corrigido (local)** (fora do upstream) ·
**em PR** · **no upstream** (falta nossa verificação) · **falta teste** · **fechado**.

| # | O quê | Origem | Quem corrige | Onde | Verificação | Teste de regressão | Estado |
|---|---|---|---|---|---|---|---|
| B31 | Nenhum socket UDP abre no m68k (`udp_recvspace` 266 KB > limite do `sbreserve` ~58 KB) | Kal, `a1ede9f0e6` | Kal | upstream `64d00bf2da` (refatoração em módulos) | `udpdiag` no Amiga emulado (UDP4/UDP6/TCP4/TCP6 abrem); DNS e DHCP no emulador; `cunit-net-udp`/`udpio` no hosted | `cunit-net-tcpinfo` (só hosted); **falta verificar no Amiga emulado** (`udpdiag`) | **fechado** — verificado no Amiga emulado (`tests/stack/udpdiag.c`: UDP4/UDP6 abrem, master `64d00bf2da`); teste do Kal em `cunit-net-tcpinfo` (hosted) |
| B32 | Timers da pilha param de vez (requisição do timer de prazo do TCP usada por duas tasks) | **nosso**, `fa93417c95`/`e0f2b1e9c5` (#2194/#2208) | Kal | upstream `64d00bf2da` (`amiga_time.c` reescrito) | transferências TCP de várias tasks ao mesmo tempo com perdas (netem) por minutos; RTO e sonda de perda continuam disparando (`tests/tcp/loss_probe.py`, `tail_probe.py`) | **sem teste específico — escrever (nós)**: N tasks enviando com perdas, RTO dispara; auditoria `AbortIO`/`WaitIO` da API | no upstream — falta teste |
| B33 | `connect()` IPv6 escolhe par de portas ainda em TIME_WAIT | provavelmente nosso (`2aae838ba6`, `c388bc08e9`) | Kal | upstream `64d00bf2da` | conexões IPv6 seguidas ao mesmo servidor/porta, fechando do lado AROS: nenhum `connect` cai num par em TIME_WAIT (captura: SYN não reaproveita o 4-tupla) | `cunit-net-tcpinfo` (teste do Kal) | no upstream — falta nossa verificação |
| B34 | Tráfego IPv6 nunca filtrado (`pfil` só no IPv4) | anterior ao nosso trabalho | Kal | upstream `64d00bf2da` | regra do firewall bloqueando ICMPv6/UDP6; o tráfego some; IPv4 igual | `cunit-net-filter6` (do Kal) | no upstream — falta nossa verificação; **B5 conflita** (4 arquivos) |
| B27 | `tcp_debug[100]` é memória morta (72 KB no m68k) | anterior; dobrou com o `tcpcb` maior | nós | upstream `64d00bf2da` ("72 KB TCP trace buffer and SYN cache allocated only when used") | `m68k-aros-nm` sem `tcp_debug`; m68k `.bss` ~17 KB | `cunit-net-synalloc` (SYN cache); para o `tcp_debug`: medir no m68k (sem o símbolo no `.bss`) | **fechado** — medido no m68k: `.bss` do núcleo 6.140 B, sem `tcp_debug` |
| B28 | Perfil `INET6=0` não compila | anterior | nós | — | build m68k com `INET6=0` | build `INET6=0` (m68k) junto com o delta de tamanho de cada PR | **perde a razão** — o IPv6 é o módulo `inet6.prot`, escolhido em tempo de execução (`PROTOCOLS=INET`: −97 KB em repouso no m68k); o `#define INET6 0` de compilação não é mais o perfil |
| B30 | Alvo do AROSTCP não depende da `fd.library` (`proto/fd.h`) | anterior | nós | — | build limpo só do alvo `workbench-network-stacks-arostcp` | o mesmo, ao montar build novo | **não se reproduz na pilha modular** (2026-11-13: `proto/fd.h` e o diretório da `fd` apagados, o alvo do AROSTCP os regenera pela cadeia de `includes`); fora do PR |
| B29 | Hosted x86_64 trava com o perfil de mbuf do m68k | não investigado | nós | — | `tests/stack/memcost.py --profile m68k` (hosted) | o mesmo | aberto (investigar) |
| B5 | Cache de vizinhos IPv6 por (interface, endereço) | anterior | nós | branch `review/arostcp-nd6-ifcache`, `11df4517ea` (local) | `zone_probe.py` 2 NS; `cunit-net-nd6cache`, `pmtu6`; 52 suítes; `defrouter.py`, `remloop.py`; delta m68k +1.420 | `cunit-net-nd6cache`, `pmtu6` (ON_LINK, LINK_LOCAL), `ndqueue6` | corrigido (local) — **PR aguarda autorização do usuário** e o #2218; rebase sobre B32–B34 |
| G11 | IPv4: ACD + IPv4LL pela ACD, DHCPDECLINE, NUD do ARP (**escopo reduzido 2026-11-12**: `IP_RECVIF`/`IP_SENDSRCADDR`, `ip_mreqn` e dicas do TCP saíram — sob demanda, como ganchos da família IPv4, quando o mdnsd/`dnssd.library` precisar de um socket IPv4 único) | — | nós | PR #2218; branch local `review/arostcp-ipv4-acd` (`fe5910c842`, `ba00219d06`, `a505f7a00e`) reimplementada sobre `64d00bf2da` (módulo `inet.prot`; reload/enlace pelos eventos de família; `dad_count` como `netvar`; bind duplicado em `inf_pcbbindaddr`) | 64 suítes ok (2 execuções); `acd_probe`, `dhcp_decline_probe` (+`--claim`), `acd_reprobe_probe` (pronto aos 66,8 s), `arp_stale_probe` (20,9 s); m68k: núcleo igual, `inet.prot` +2.468 B | `cunit-net-acd`, benches `tests/ipv4` | **2ª revisão do Kal respondida (2026-11-12):** força-push `3e633650bc`; origem por endereço (`SIOCAIFADDR_ORIGIN`), origem pronta/broadcast /32, dhclient por sinal; validado em build só da branch (64 suítes; benches); m68k `inet.prot` +3.708 B, `dhclient` +2.208 B; memória no Amiga emulado: repouso +2,9 KB (638,2→641,1), pós-carga +3,0 KB, pico sob carga +7 a +24 KB (variável). Aguarda o Kal |
| B3 | `tcp_drain()` vazio | anterior | — | — | auditado, não demonstrado | — | aberto (baixa prioridade) |
| H1 | Build paralelo perde headers gerados: `proto/security.h`, `interface/Hidd.h`, `partition_support.h` | AROS (fora da pilha) | — | — | build m68k `-j8` limpo | — | aberto (observação; reproduzir) |
| E1 | `egl.library` falha no m68k e para o build das bibliotecas seguintes | AROS (fora da pilha) | — | — | `make workbench-libs-complete` m68k | — | aberto (observação) |

## Planos ligados (sem item de bug)

- Regra "padrões ligados à máquina" + auditoria dos valores fixos da pilha — `research/2026-11-11-stack-cost-m68k.md`.
- Grupo multicast/SSM — **cancelado pelo usuário (2026-11-12)**; issue #2220 fechada. O plano (`research/2026-11-10-multicast-ssm-design.md`) fica só como referência.
- G12 (mDNS/DNS-SD) — **área do Codex assumida (2026-11-12, decisão do usuário)**; ordem em `aros-midihub/docs/mdns-integration-agreements.md` (`85553db9d5`): (1) mdnsd no modelo canônico; (2) protocolo interno neutro; (3) `dnssd.library` v0 com consulta de endereço; (4) `.local` no `resolver.atcp`; (5) busca/resolução/registro, migração, retirada da `bonami.library`.
  - Passo 1: branch local `review/mdnsd-canonical-links` (5 commits do Codex sobre `64d00bf2da`, sem conflito). Testes do Codex no hosted modular: modelo, inventário e coletor AROSTCP, 0 falhas. Interoperabilidade com Avahi (`tests/mdns/interop.sh`): host resolve `arosbox.local` A+AAAA e navega no serviço da AROS; AROS navega no serviço do host e resolve `palerma.local`. Precodacy: 1 cppcheck (escopo) + `strncpy`/`strlen` nos testes — corrigir antes do PR. m68k (Amiga emulado): testes do modelo/inventário/coletor 0 falhas (com o `startnet` antes; ver B35) e interoperabilidade com Avahi idêntica ao hosted (`MODE=amiga`). Achado do Codex corrigido: `dnssd_link_aros.c` não compilava no m68k com `-Werror` (sign-compare; `fixup!` `56fec7cd49`). Falta: corrigir os achados do precodacy, dobrar o fixup, PR com o aval do usuário (mdnsd é dele).
  - Passos 2–4 (desenho `research/2026-11-12-dnssd-library-design.md`): **feitos e testados (2026-11-12)**, commits locais em `review/mdnsd-canonical-links`: `25781b00d2` (consulta com *sink*: todas as respostas, não só a primeira), `a68700b45c` (porta `"DNSSD"` no mdnsd: sessões/operações com geração e encarnação, fila por sessão com `LOST`, notificação emprestada, consulta A+AAAA com índice de interface), `7c54609b0d` (`dnssd.library` v1: `OpenSessionA`, `CloseSession`, `ReadEvent`, `Cancel`, `LookupAddressA`, `LookupAddressSyncA`, `GetStatusA`). Teste `tests/mdns/dnssd.sh` + `dnssdtest.c` (layout, parâmetros, consulta assíncrona/IPv6 só/inexistente, cancelamento imediato sem eventos depois, fechar com operação ativa, síncrona, contadores do daemon a zero): **20/20 no hosted e no m68k** (Amiga emulado; `DNSSDEvent` 56 B no x86_64, 52 B no m68k, mesmos offsets). Interop Avahi pelo caminho BonAmi sem regressão. m68k: `dnssd.library` 12.884 B; no mdnsd `dnssd_server.o` 2.566 B de texto. Falta: passo 5 (`.local` no `resolver.atcp`, PR do AROSTCP depois do #2218 e do B5), 6–8; AutoDocs geradas pelo build; PR só com o aval do usuário.
  - **Decisões do usuário (2026-11-12):** IPP não migra; motor do mdns livre para redesenho; Bonami é só origem do código; lacuna da pilha se implementa na pilha. Plano R1–R7 no documento de desenho (ordem revista: API completa → migração → retirada da BonAmi → internos).
  - **R1 feito:** pilha `review/arostcp-ip-recvif` (sobre `64d00bf2da`): `05508114ec` `IP_RECVIF`; `a3edf5f169` B36 (adesões órfãs, `cunit-net-mcastgone`); `735beaaf27` B37 (clusters de recepção vazavam na remoção de interface, `tests/stack/ifremove.sh`). mdnsd `9cd6386ae8` um socket por família (hosted/m68k: `dnssdtest` 20/20, interop igual; dois enlaces `TWO=1`: cada enlace com o próprio endereço). PR da pilha: depois do #2218 e do B5 (fila de um PR), bump no último commit, delta m68k a medir.
  - **R5 feito (2026-11-12)**, `6a4166580b`: cache de registros (`mdns_cache.c`, nomes em formato de fio, §10.1/§10.2, perguntas contínuas com respostas conhecidas §5.2/§7.1, renovação 80–95 %, orçamento 24 KB m68k/128 KB) e operações `LookupAddress`/`Browse`/`Resolve`/`QueryRecord` como assinantes; evento v1 completo (instância, tipo, domínio, alvo, porta, prioridade, peso, TXT, RDATA). `dnssdtest` 33/33 no hosted e no m68k (inclui instância `Dot.Test`: escapada em `de_Name`, crua em `de_Instance`); interop e dois enlaces íntegros. m68k: mdnsd 69.876 → 77.148 B (o motor antigo de descoberta, ~100 KB estáticos de RAM, sai no R7), `dnssd.library` 14.132 B.
  - **Registro feito** (`5283b25a20`): `DNSSD_RegisterA`/`UpdateA`, instância com ponto, TXT binário, subtipos, `REGISTERED` com nome final (conflito → `Nome (2)`), `EXISTS`; codec em formato de apresentação RFC 1035 (`\.`). `dnssdtest` 44/44 hosted e m68k; host vê o registro pelo Avahi. Depois (commit seguinte): `Browse` de `_services._dns-sd._udp` (tipos) e registro para outro host (`DNSSD_Host`/`DNSSD_HostAddress`, IPv4) — compilado, 44/44 hosted, **ainda não testado no m68k nem com teste próprio** (enumeração de tipos e proxy).
  - **Auditoria de limitações herdadas da BonAmi (2026-11-12):** A1–A5 corrigidos (`77276cbd38`; ver documento de desenho); `dnssdtest` 63/63 hosted e m68k.
  - **Próximo:** teste da enumeração de tipos; reescrever as ferramentas (`ba_common` sobre sessões `dnssd.library`; `dnssd` com -B resolvendo cada instância para manter a saída que `interop.sh` confere, -L, -R, -P, -q, -G; `Nearby`, `Share`, `Handshake`), depois `netmidid` (`workbench/network/netmidid/discovery.c`), e o R7 (retirar `bonami.library`, porta `BonAmi`, `mdns_client.c`, `mdns_discovery.c`, `mdns_query.c`). IPP não migra.
  - #2123 (eventos V2 na `bonami.library`): **fechado (2026-11-12)** com nota apontando para a `dnssd.library`. Branches `review/mdns-tools-v2` e `review/mdns-receive-hoplimit` (#2119 recusado) abandonadas.

## Itens a não perder (pedido do usuário, 2026-11-14)

- **B42** (troca de hostname sem reconfiguração não chega ao mdnsd; desde `db1826863d`): resolver **junto da integração
  do `.local` no `resolver.atcp`** (passo 5 do desenho, PR do AROSTCP depois do #2218), que depende do nome atual do
  mdnsd. Duas partes: o AROSTCP avisa a troca de hostname em `Miami_sethostname()`/ARexx — de preferência por uma
  notificação própria (ex.: um `SBTC_SIG_HOSTNAME_CHANGE_MASK`), não sobrecarregando o sinal de troca de endereço
  (decisão a tomar no PR do AROSTCP, com o Kal); o mdnsd relê o nome quando avisado, não só quando o inventário muda.
  **Não implementar agora** (usuário, 2026-11-14). Teste:
  trocar o hostname por `Miami_sethostname()` sem reconfiguração e ver o mdnsd anunciar o novo.
- **Provedor canônico de registros locais** (investigação futura, fora do PR do mDNS por decisão do usuário): medir
  três benefícios possíveis antes de decidir — (1) memória residente (os registros locais copiados no cache: host e
  serviços), (2) caminhos duplicados de atualização e invalidação (reflexo no envio + `mdnsCacheDropLocal` nos pontos de
  troca), (3) código total, incluindo a notificação. Desenho a avaliar: as observações do cache consultam o estado
  autoritativo (`mdnsNetAddressAt()`, registros de `mdns_reg.c`) e são avisadas das mudanças, sem cópia.

## Último commit do upstream visto

`64d00bf2da` (2026-11-12, Kal: núcleo + módulos `inet.prot`/`inet6.prot`/`transport.prot`, `resolver.atcp`/`admin.atcp`/`packet.atcp`/`netconfig.atcp`; serviços do núcleo em `net/netcore.def`). Trouxe B27, B31–B34. **As medições de tamanho/memória (`research/2026-11-11-stack-cost-m68k.md`) são da estrutura anterior: refazer a linha de base sobre ela** (núcleo + módulos carregados).
