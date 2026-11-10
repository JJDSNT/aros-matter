# Grupo multicast dual-stack (SSM) — desenho (2026-11-10, em andamento)

## Decisões do usuário (2026-11-10)

- Ordem: **G11 (#2218) → multicast dual-stack (este) → G12 (mDNS/DNS-SD)**. Motivo: consolidar a pilha antes de
  integrar consumidores; o SSM muda a representação das inscrições multicast, que o G12 usa (inscrições em
  224.0.0.251 / ff02::fb por interface).
- RFC 1256 (ICMP Router Discovery): **backlog**, sem PR, até haver caso de uso (preferência de roteadores, validade,
  expiração, convivência com DHCP/rotas manuais seriam responsabilidade nova). Se feito: programa à parte (`rdisc`),
  não código na pilha.
- Separado do #2218 (branch próprio).
- Refinamentos aceitos (texto do ChatGPT trazido pelo usuário): não decidir de antemão um núcleo compartilhado entre as
  famílias — homogêneo no **modelo e na API**, compartilhar implementação só onde reduzir duplicação; não supor que tudo
  será reescrito; **regressão do multicast comum desde o início**; quinta investigação: **filtragem na entrega**.

## Escopo funcional

IGMPv3 host (RFC 3376), MLDv2 host completo (RFC 3810), API RFC 3678 nas duas famílias (protocol-independent
`MCAST_*` e as `IP_*_SOURCE_*`), SSM (RFC 4604/4607), estados INCLUDE/EXCLUDE, relatórios de mudança de estado,
compatibilidade com IGMPv1/v2 e MLDv1 (modo de compatibilidade por interface conforme o querier), limites explícitos de
memória, filtragem efetiva na entrega aos sockets.

## Estado atual do AROSTCP (apurado)

| Peça | IPv4 | IPv6 |
|---|---|---|
| Inscrição do host | `struct in_multi` (grupo, ifp, refcount, estado, timer), lista global | `struct in6_multi`, idem |
| Inscrição do socket | `ip_moptions.imo_membership[IP_MAX_MEMBERSHIPS=20]` (ponteiros para `in_multi`), sem estado de fonte | `ip6_moptions.im6o_membership[20]`, idem |
| Protocolo | IGMPv2 (aceita relatório v1), `igmp.c` 398 linhas | MLDv1 + relatório MLDv2 só MODE_IS_EXCLUDE{} (`mld6.c` 591 linhas) |
| API SSM | `IP_ADD_SOURCE_MEMBERSHIP` (25) e `MCAST_*` (46…) **declarados**, não implementados | idem (`MCAST_*`) |
| **Entrega UDP** | `udp_input()`: todo socket na porta (laddr/faddr batendo) recebe — **não confere a inscrição do socket** (4.4BSD) | `udp6_input()`: idem, comentário explícito "the sockets are not filtered by their own memberships" |

As duas famílias seguem o mesmo modelo clássico (4.4BSD/KAME), simétrico.

## Modelo: FreeBSD (verificado no código)

Só o FreeBSD tem SSM completo no kernel (Bruce Simpson, 2009): `sys/netinet/in_mcast.c` (78 KB),
`sys/netinet6/in6_mcast.c` (81 KB), IGMPv3 em `igmp.c`, MLDv2 em `mld6.c`. NetBSD e OpenBSD: IGMPv2/MLDv1 apenas.
O FreeBSD tem **o mesmo modelo nas duas famílias, em implementações paralelas** (`in_mfilter`/`ip_msource`/`in_msource`
e os `in6_*`), com um filtro por socket na entrega (`imo_multi_filter()` / `im6o_mc_filter()`), estado "t0/t1" para
calcular as mudanças a reportar, e um limite de fontes por inscrição (`net.inet.ip.mcast.maxsocksrc`, `maxgrpsrc`).

## Investigações (pendentes)

1. **Estado no AROS** (feito, acima) — falta: timers do IGMP/MLD, como o querier é tratado, `IN_LOOKUP_MULTI`,
   raw sockets (raw_ip/raw_ip6) na entrega multicast.
2. **FreeBSD em detalhe**: estruturas de filtro (árvore RB por fonte), cálculo de deltas t0→t1, compatibilidade de
   versão por interface, quanto disso é compartilhável sem abstração artificial.
3. **Limites de memória**: por socket, por grupo; valores do FreeBSD (`maxsocksrc` 128, `maxgrpsrc` 512) frente às
   máquinas pequenas do AROS; alocação do vetor de inscrições (hoje fixo em 20).
4. **Testes**: regressão do multicast comum (`cunit-net-cmsg` v4, `mcast6`, `mcast6if`, `mld6`) a cada commit;
   novos CUnit da API; bench com **querier IGMPv3/MLDv2 no host** (consultas gerais, por grupo e por grupo-e-fonte;
   verificação dos relatórios na captura) e fontes múltiplas na tap.
5. **Filtragem na entrega** (achado: hoje nenhuma, nas duas famílias): filtro por socket (grupo + interface + fonte)
   em `udp_input`/`udp6_input` e nos raw; avaliar a mudança de comportamento para sockets na porta que não se
   inscreveram (o FreeBSD passou a filtrá-los) — decidir com teste de regressão e nota no PR.

## Apurado na pesquisa (2026-11-10)

- **FreeBSD** (código lido): `ip_moptions` com `STAILQ` de `in_mfilter` (alocação sob demanda; sem o vetor fixo de 20);
  `in_mfilter` = árvore RB de `in_msource` + modo t0/t1; `in_multi` ganhou árvore de `ip_msource` com contadores
  ex/in em t0/t1 (os deltas viram relatórios de mudança de estado), fila de relatórios pendentes, timers de
  retransmissão. `imo_multi_filter()` decide por socket: `MCAST_NOTGMEMBER` / `NOTSMEMBER` / `PASS`.
  Limites: `net.inet.ip.mcast.maxgrpsrc` 512, `maxsocksrc` 128. Tamanho: igmp.c 3732, in_mcast.c 2994, mld6.c 3296,
  in6_mcast.c 3051 linhas (~13 mil; VNET/locks somam boa parte).
- **Política de entrega para socket não inscrito** — as referências divergem:
  FreeBSD estrito (sem `ip_moptions` → não recebe multicast); **Linux permissivo** (`IP_MULTICAST_ALL` padrão 1: recebe
  os grupos em que o host está inscrito; o filtro de fontes só vale para sockets inscritos). O AROS hoje = Linux com
  `IP_MULTICAST_ALL` ligado.
- AROS tem `sys/tree.h` (RB) e `sys/queue.h` (STAILQ).
- IGMP do AROS: só host IGMPv2, sem o modo de compatibilidade com querier v1 (RFC 2236 §4 pede) — o port resolve.
- Raw sockets (`raw_ip`, `raw_ip6`): entregam multicast sem filtro por inscrição, como o UDP.

## As quatro verificações (2026-11-10) — evidências

1. **Consumidores de multicast sem inscrição no AROS: nenhum.** `mdns/mdns_net.c`, `dhcp/common/socket.c` (grupos de
   servidor/relay DHCPv6) e o WirelessManager (IAPP, SSDP/WPS) se inscrevem; `devs/ipp/dnssd.c` faz a consulta
   one-shot da RFC 6762 §6.7 em porta efêmera (respostas unicast, o próprio código diz que não precisa de inscrição);
   `ping`/`traceroute` recebem ICMP unicast; `ip maddr` só lê. Nenhum receptor de ICMPv6 em espaço de usuário (RA/ND
   são do kernel).
2. **Sockets raw de controle:** a pilha não usa nenhum internamente (IGMP e MLD são tratados no kernel,
   `igmp_input()`, `mld6_input()`). Política do FreeBSD (lida em `raw_ip.c`/`raw_ip6.c`): um socket raw só é filtrado
   se tiver estado multicast (`inp_moptions`), e a exceção é **por protocolo**, não por tipo de socket — IGMP sempre
   passa (v4), MLD sempre passa (v6, pela opção Router Alert, `M_RTALERT_MLD`); o resto é filtrado. Sem exceção
   genérica para raw.
3. **Concorrência (Readme §3.2):** a API roda na task de quem chama, sob o `syscall_semaphore` global (uma chamada por
   vez); o daemon (entrada, timers) nunca o pega e só se exclui da API pelo `spl`. Mapeamento das travas do FreeBSD:
   `IN_MULTI_LOCK` (sx, operações de setsockopt) → `syscall_semaphore` (já tido pela API);
   `IN_MULTI_LIST_LOCK`, `IGMP_LOCK`/`MLD_LOCK` e o `INP` lock → **`splnet`** — todo estado que o daemon lê ou muda
   (filtros do socket lidos na entrega, árvore de fontes do grupo, fila de relatórios, timers) muda em `splnet`, mesmo
   com o semáforo; alocação `M_NOWAIT` sob `spl` (o `malloc_semaphore` é folha na ordem de travas). A liberação
   adiada do FreeBSD (epoch, `inm_release_deferred`) não é necessária: o `spl` já serializa o daemon contra a API.
   O fechamento do socket libera os filtros em `splnet`.
4. **Limites:** no FreeBSD, `maxsocksrc` (128) é **por inscrição**, `maxgrpsrc` (512) por grupo×interface (todos os
   sockets), e `IP_MAX_MEMBERSHIPS` 4095 por socket — sem teto por socket somado (4095×128 fontes ≈ 20 MB). Linux:
   `igmp_max_memberships` 20, `igmp_max_msf` 10. Atomicidade: o FreeBSD já faz as mudanças de filtro em duas fases
   (`imf_commit()`/`imf_rollback()`, `inm_commit()`): uma falha de alocação desfaz tudo — mantido no porte.

## Plano final (para aprovação do usuário)

- **Entrega estrita por inscrição (como o FreeBSD)**: UDP só entrega multicast a socket inscrito no grupo naquela
  interface e cuja lista de fontes permite; raw filtrado só com estado multicast, IGMP/MLD sempre passam. Sem
  `IP_MULTICAST_ALL`. Nota explícita no PR (mudança de comportamento; nenhum consumidor do AROS afetado).
- **Porte do FreeBSD com critério**: modelo de estado por socket e por interface, máquinas IGMPv3/MLDv2, agregação
  INCLUDE/EXCLUDE (t0/t1), relatórios de mudança de estado e timers, commit/rollback; fora VNET, epoch, sysctls de
  debug, roteamento multicast. Atribuição: cabeçalhos de copyright do FreeBSD preservados nos arquivos portados.
- **Limites AROS** (sysctls `net.inet.ip.mcast.*` e `net.inet6.ip6.mcast.*`): inscrições por socket 20 (o atual);
  fontes por inscrição 64; fontes por grupo×interface 256; **teto por socket somado** de fontes 256 (novo, para
  máquinas pequenas). Valores a confirmar no commit, com teste de cada limite.
- **Sete commits**: (1) estruturas dinâmicas de inscrição, comportamento preservado; (2) filtragem estrita na entrega
  para multicast comum, v4 e v6; (3) RFC 3678 + filtros por fonte IPv4; (4) IGMPv3 completo; (5) RFC 3678 + filtros
  IPv6; (6) MLDv2 completo; (7) documentação, sysctls, versão.
- **Testes**: regressão do multicast comum em cada commit (`cmsg`, `mcast6`, `mcast6if`, `mld6` + 52 suítes); CUnit
  novos (API, limites, erros, entrega filtrada com duas fontes, socket não inscrito não recebe); bench com querier
  IGMPv3/MLDv2 no host (consultas geral/grupo/grupo-e-fonte, relatórios na captura, compatibilidade v2/MLDv1).

## Requisitos acrescentados (texto do ChatGPT trazido pelo usuário, aceitos)

- A entrega filtra pela combinação **interface de entrada + grupo + fonte + inscrições/filtros do socket**, preservando
  sockets ligados a endereço específico. Teste: duas interfaces, mesmo grupo — inscrição na A não autoriza entrega do
  que chega pela B.
- O limite de fontes por grupo vale sobre o **estado agregado por interface** (todos os sockets); exceder falha de forma
  atômica (sem mudar o estado anterior nem gerar relatório IGMP/MLD inconsistente). Sysctl reduzido abaixo do consumo
  atual vale só para operações futuras.
- Sincronização: respeitar a ordem de travas (Readme §3.2) e nenhuma espera bloqueante dentro de `spl`.

## Consulta ao Kal (decisão do usuário, 2026-11-10)

O usuário prefere ouvir o Kal antes de implementar este grupo (escopo e mudança de comportamento grandes). Rascunho de
issue preparado; publicação só com aprovação do usuário.
