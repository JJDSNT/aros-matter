# AROSTCP IPv6: análise de arquitetura e proposta de implementação

Status: **proposta revisada** (2026-10-28): D1, D4 e o local dos testes decididos (§4). Nenhum código foi escrito ainda.
Branch de trabalho: `arostcp-ipv6` na worktree `~/AROS-ipv6`, criada de `upstream/master` `4c2c268a53`.
Tracker: [ISSUE-0008](../issues/ISSUE-0008.md).

## 1. Objetivo

Levar o IPv6 do AROSTCP ao comportamento que as RFCs de API e de endereçamento especificam e que as pilhas BSD implementam. O alvo são **implementações corretas e completas por área**, não correções pontuais dos sintomas vistos nos testes. Os consumidores imediatos são o mDNS IPv6 (mdnsd) e o Matter; nada aqui deve depender deles.

## 2. O que existe hoje

`workbench/network/stacks/AROSTCP/bsdsocket/netinet6/` (~9 mil linhas), escrito do zero por Nick Andrews a partir de 2026-02-21 (`7cfe3914be`, "Initial IPv6 integration"), com estrutura inspirada no KAME:

- IPv6 in/out com fragmentação e PMTU (RFC 8201), ICMPv6, ND/SLAAC (`nd6*.c`), endereços temporários (RFC 4941).
- MLDv1 + MLDv2 host (RFC 3810, `mld6.c`).
- UDP6, TCP sobre IPv6, sockets dual-stack com endereços IPv4-mapped.
- Opções por socket: `IPV6_V6ONLY`, `IPV6_UNICAST_HOPS`, `IPV6_MULTICAST_IF/HOPS/LOOP`, `IPV6_JOIN/LEAVE_GROUP`, `IPV6_RECVPKTINFO`, `IPV6_PKTINFO`, `IPV6_HOPLIMIT`, `IPV6_TCLASS`.
- Associações a grupos por socket no modelo 4.4BSD/KAME: `struct ip6_moptions` com `im6o_membership[]` (`in6_var.h:132`), e a lista global `in6_multihead` com refcount (`in6.c:764`).

## 3. Lacunas, com evidência

Referências do AROS na revisão `4c2c268a53`; do FreeBSD em `freebsd-src@389ae8e4fa`, `sys/netinet6/`.

### G1 — Zonas de escopo (RFC 4007; RFC 3493 §3.3) — **lacuna de arquitetura**
- `sin6_scope_id` é lido num único lugar da pilha (`udp6_usrreq.c:177`). `bind`, `connect`, `recvfrom`, `getsockname`/`getpeername` ignoram a zona ou não a preenchem.
- A interface de um link-local é adivinhada: "primeira interface UP não-loopback" (`ip6_output.c:120-128`, `in6_proto.c:196-203`) ou "a interface do endereço de origem" (`ip6_srcifp`). O próprio comentário em `ip6_output.c:148-156` registra que a tabela de rotas guarda `fe80::/64` uma vez só para todas as interfaces.
- Referência: o KAME/FreeBSD embute o índice da zona em `s6_addr16[1]` dentro do kernel e converte na fronteira da API (`scope6.c:318 sa6_embedscope`, `:355 sa6_recoverscope`, `:400 in6_setscope`, `:450 in6_clearscope`). O Linux mantém o endereço limpo e carrega o `ifindex` à parte (no socket, `sk_bound_dev_if`, e na consulta de rota, `flowi6_oif`).
- Impacto: com mais de uma interface, link-local e multicast link-scope saem pela interface errada. Responder a um `fe80::` recebido exige saber a zona de origem.

### G2 — Escolha da interface de saída e do endereço de origem (RFC 6724) — **lacuna de arquitetura**
- A escolha está duplicada e incompleta em três lugares: `in6_pcbconnect()` (`in6_pcb.c:179-196`, só `rtalloc`), `udp6_output()` (`udp6_usrreq.c:222-249`) e as heurísticas de `ip6_output()`. `in6_ifawithifp()` (`in6.c:403`) só compara escopo.
- Sintoma medido: `sendto(ff02::fb)` de um socket ligado a `[::]` retorna `EADDRNOTAVAIL`. O `in6_pcbconnect()` roda antes e não há rota para `ff02::/16`, de modo que `IPV6_MULTICAST_IF` e `sin6_scope_id` nunca são consultados ([testes](2026-10-28-hosted-tests.md)).
- Referência: o FreeBSD tem uma função única, `in6_selectsrc()` (`in6_src.c:174`), que trata as regras da RFC 6724 e, antes delas, escolhe a interface de saída (`in6_selectif`) a partir de `IPV6_PKTINFO`, `IPV6_MULTICAST_IF`, zona do destino ou rota, nessa ordem. Todos os chamadores (UDP, TCP, ICMPv6, ND, raw) usam essa função.

### G3 — Recepção de multicast para grupos associados
- `ip6_input()` (`ip6_input.c:541-562`) aceita multicast só para solicited-node e `ff02::1`, por comparação fixa. A lista `in6_multihead`, que `IPV6_JOIN_GROUP` preenche, não é consultada; `ff02::fb` é descartado.
- Esses dois grupos já entram em `in6_multihead` pelo `in6_if_up()` (`in6.c:606,617`). Com uma consulta à lista, os dois casos fixos passam a ser cobertos pela regra geral.
- Referência: o FreeBSD aceita todo multicast no IP (`ip6_input.c:781`) e filtra por associação no transporte. O KAME clássico usava `IN6_LOOKUP_MULTI(dst, rcvif)` no IP.

### G4 — Entrega de multicast UDP a vários sockets
- `udp6_input()` entrega cada datagrama a **um** PCB (`udp6_usrreq.c:389`, `in6_pcblookup`).
- Referência: `udp6_multi_input()` (`udp6_usrreq.c:249-340` do FreeBSD) percorre os PCBs da porta, aplica `im6o_mc_filter()` (o socket precisa ter associação ao grupo **na interface de chegada**, RFC 3678) e entrega uma cópia a cada um. Encerra cedo se o socket não tem `SO_REUSEADDR`/`SO_REUSEPORT`. Um socket sem opções multicast não é filtrado.

### G5 — Ciclo de vida das associações (espelho da sua série IPv4)
- `in_pcbdetach()` (`netinet/in_pcb.c:395-416`) libera `inp_moptions` (IPv4, seu `95a501ff47`) mas não `in6p_moptions`. As associações IPv6 de um socket fechado ficam ativas, e o host continua respondendo MLD por elas.
- `if_detach()` não desliga as `in6_multi` da interface. É o equivalente IPv6 do seu `4b11ae149b` ("no group membership outlives its interface").
- `IPV6_JOIN_GROUP` com `ipv6mr_interface == 0` usa "primeira interface UP" (`in6_proto.c:196`). A RFC 3493 deixa a escolha ao kernel, mas o esperado é usar a rota do grupo ou uma interface multicast padrão definida, no mesmo espírito do seu `1787a72362` (envio IPv4 a grupo sem rota).

### G6 — Loopback de multicast na saída
- `ip6_output()` (`multicast_output:`, `ip6_output.c:222`) não entrega cópia local quando `im6o_multicast_loop` vale 1 (o padrão da RFC 3493) e o host participa do grupo naquela interface. Dois programas no mesmo AROS não se veem por `ff02::fb`.
- Referência: `ip6_mloopback()` (KAME/FreeBSD `ip6_output.c`), e o seu `ip_mloopback` no IPv4.

### G7 — API avançada (RFC 3542)
- `struct in6_pktinfo` não está nos headers públicos; só em `udp6_usrreq.c:104` e `dhcp/includes/config.h:225`.
- A entrega de ancillary data no `recvmsg` não foi exercitada por teste (nenhum multicast chegou).
- A origem recebida não leva `sin6_scope_id` (`udp6_usrreq.c:377-381`). Isso faz parte de G1.

### G8 — Route Information Option (RFC 4191)
- `nd6_rtr.c:745-794` trata SLLAO, PIO e MTU; a RIO (tipo 24) é ignorada.
- Impacto Matter: o border router Thread anuncia o prefixo OMR da malha na rede de infraestrutura como RIO nos seus RAs ([OpenThread Border Routing](https://openthread.io/reference/group/api-border-routing)). Sem RIO, o controlador só alcança os dispositivos Thread se o border router for também o roteador default.

### G10 — Tempo de vida endereço × rotas
- `ifa_refcnt` existe em `struct ifaddr`, mas não é usado; `in6_purgeaddr()` libera o endereço mesmo com rotas apontando para ele. Uso após liberação intermitente observado em `rtrequest()`. Ver [ISSUE-0009](../issues/ISSUE-0009.md).

### G15 — Rotas IPv6 via roteador perdem o gateway (**causa confirmada no código; efeito no envio ainda não medido**)
- `nd6_rtrequest()` (`netinet6/nd6.c`) trata toda rota nova numa interface IPv6 como entrada de vizinho: no `RTM_ADD` cai no caminho de `RTM_RESOLVE`, troca o gateway por um `sockaddr_dl` vazio (`nd6_storelladdr()`) e aloca `llinfo_nd6`. O FreeBSD 4.11, que o comentário diz seguir, sai logo no início para rotas com gateway (`sys/netinet6/nd6.c:1103-1104`, `if ((rt->rt_flags & RTF_GATEWAY)) return;`). Essa linha foi omitida.
- Evidência: na bancada RFC 4191, `RTM_GET` da rota instalada por RIO devolve `flags=0x413` (`RTF_UP|RTF_GATEWAY|…`), mas o gateway vem como `AF_LINK` (família 18, len 18), não como `fe80::4d54:a`.
- Afeta toda rota via roteador: a default aprendida de RA (já antes da S8), rotas estáticas IPv6 e as rotas da RIO.
- Suspeita relacionada (a confirmar): `nd6_resolve()` resolve o vizinho sobre a rota do destino; não há o desvio para a entrada de vizinho do gateway que o `nd6_output()` do KAME faz (`rt_gwroute`). Se confirmado, nenhum pacote IPv6 para fora do link sai pelo roteador.
- Para medir: o AROS precisa de um endereço global (o RA do host deve trazer PIO com SLAAC); só com link-local, `sendto()` para destino global devolve `EADDRNOTAVAIL`, o que está correto (RFC 4291: link-local não é roteado).
- Impacto Matter: é o caminho do controlador até um dispositivo Thread atrás do border router (rota da RIO → gateway = BR).

### G14 — Sockets raw IPv6 ignoram as opções IPv6
- `rip6_ctloutput()` (`netinet6/icmp6.c`) é um stub que devolve 0 para qualquer opção: `setsockopt()` "funciona" sem efeito.
- `rip6_output()` monta o cabeçalho com `ip6_defhlim` e chama `ip6_output()` com opções multicast `NULL`: `IPV6_MULTICAST_HOPS/IF/LOOP` e `IPV6_UNICAST_HOPS` não se aplicam; não há `ICMP6_FILTER`. O socket raw usa `struct rawcb`, sem lugar para opções (no KAME/FreeBSD, o raw IPv6 usa o `in6pcb` e herda as opções).
- Consequência: nenhum programa no AROS gera RS/RA/NS/NA válidos (hop limit 255, RFC 4861). Impediu o teste autocontido da S8, cujo RA saía com hop limit 64 e era descartado, corretamente.
- Cuidado registrado: um teste que envia RA por raw socket com hop limit certo também o envia pela tap ao host. Um RA com router lifetime > 0 instalaria rota default no Linux do host. Testes upstream não devem fazer isso.

### G13 — `IPV6_V6ONLY` e `IPV6_CHECKSUM` com o mesmo valor
- Ambos valem 26 em `common/include/netinet/in.h`; nos BSDs, `IPV6_V6ONLY` é 27. Anotado no #1947, sem mudança.

### G12 — Ancillary data truncada em LP64 (→ #1947)
- `udp6_saveopt()` faz `cmsg_len = sizeof(struct cmsghdr) + size`, mas o dado começa em `CMSG_DATA()`, alinhado após o cabeçalho de 12 bytes (offset 16 no x86-64). Os últimos 4 bytes do dado ficam fora: `ipi6_ifindex` chega com lixo e `IPV6_HOPLIMIT` sem valor. Em 32 bits não há preenchimento. Correção: `CMSG_LEN()`/`CMSG_SPACE()`, como o `sbcreatecontrol()` do BSD. Encontrado na bancada da S2 (`link.pktinfo`). Vai na S5.

### G11 — BPF para programas
- ~~Não há `<net/bpf.h>` público~~ → resolvido no #1924, a pedido do Kal (2026-10-29).
- ~~`BIOCGDLT` anuncia `DLT_EN10MB`, mas a captura vem sem cabeçalho de enlace~~ → corrigido pelo Kal em `13743b3160` (cabeçalho Ethernet reconstruído; `DLT_RAW` nos outros tipos SANA-II; `BIOCSETIF` recusa `lo0`/`sit0`).
- Encontrado ao escrever `tests/upstream/.../cunit-net-mld6.c`.

### G9 — `tap.device` (bancada hosted)
- Não implementa `S2_ADDMULTICASTADDRESS`/`S2_DELMULTICASTADDRESS`/`S2_MULTICAST`; repassa todo multicast (`arch/all-unix/devs/networks/tap/iotask.c:73-80`). Não bloqueia, mas a bancada não reproduz o filtro de hardware. Você já fez o equivalente no `eth.device` (unix), `22b888578a`.

## 4. Decisões de desenho (para o mantenedor)

**D1 — Representação da zona (G1). ✅ Decidido: seguir o modelo que o AROS já documenta.**
O `bsdsocket/Readme.md` §6.6 ("Scoped link-local and multicast output") define que o link de saída é o que o chamador nomeia: `sin6_scope_id` do destino, índice do `IPV6_PKTINFO` ou a interface do endereço de origem escolhido. A zona nunca é embutida no endereço, e `nd6_lookup(addr, create, ifp)` segue a mesma linha. É o modelo (b) abaixo. O trabalho é aplicá-lo de forma consistente onde ele ainda não vale (G1/G2: `in6_pcbconnect`, bind, recepção, `getsockname`/`getpeername`), não escolher outro. Análise original das alternativas, mantida como registro:
- (a) KAME/FreeBSD: embutir a zona no endereço dentro do kernel. Prós: rotas, ND e listas de endereços distinguem zonas sem mudar as estruturas; desenho testado há 25 anos. Contras: toca cada ponto em que um endereço entra ou sai do kernel e cada checksum/transmissão (`in6_clearscope`); um esquecimento vaza a zona para o fio ou para o usuário.
- (b) Linux: endereço sempre limpo, zona carregada explicitamente (no PCB: zona local e remota; nas chamadas de saída: `ifp` obrigatório para escopo link). Prós: casa com o código atual, que nunca embute e já resolve link-local por `nd6_lookup(addr, ifp)`; a RFC 4007 §6 diz que destinos link-scope estão sempre no link da zona, então não precisam de roteamento. Contras: cada estrutura que guarda um endereço link-scope precisa do campo de zona ao lado.
- Zona = `if_index`, como no §6.6. Antes da S6, fazer um inventário dos pontos que guardam endereços link-scope (PCB, `in6_ifaddr`, cache ND, rotas `RTF_HOST` de vizinhos).

**D2 — Onde filtrar multicast (G3/G4). ✅ Paridade com o IPv4 da própria pilha.** O IP aceita destinos presentes em `in6_multihead` para `rcvif`, como o `ip_input()` faz com `IN_LOOKUP_MULTI(dst, rcvif)` (o que também elimina os casos fixos de G3). O UDP entrega uma cópia a cada socket da porta que casa endereços e porta, respeitando `inp_boundif`, sem filtro por associação do socket, como o `udp_input()` IPv4 (`netinet/udp_usrreq.c:182-268`) e o Linux. O filtro `im6o_mc_filter` do FreeBSD foi descartado para não divergir do IPv4 do AROS.

**D3 — Escopo da seleção de origem (G2).** Recomendação: uma função `in6_selectsrc()` com as regras da RFC 6724 que se aplicam a um host (1 mesmo endereço, 2 escopo, 3 evitar deprecated, 5 interface de saída, 7 preferir temporário conforme a política do socket, 8 maior prefixo comum). A tabela de políticas (regra 6) fica com os valores padrão fixos e sem configuração, e a regra 4 (home address) fica fora.

**D4 — Coordenação upstream. ✅ Via Kal (Nick Andrews, kalamatee)**, com quem o mantenedor tem contato. Antes de S6/S7 (G1/G2), levar esta análise a ele. G3–G7 são isolados e seguem o padrão da série IPv4 do mantenedor, podendo ir primeiro. Commits e PRs upstream **sem assinatura do Claude Code**. Cada mudança atualiza o `bsdsocket/Readme.md` (§6, §11).

## 5. Plano em etapas

Cada etapa é uma série de commits focados com testes. Ordem pensada para entregar valor cedo sem bloquear no desenho de G1/G2.

| Etapa | Conteúdo | Depende de | Teste que fecha a etapa |
|---|---|---|---|
| S0 | Suíte de testes IPv6 **neste repositório** (`tests/`, evolução de `tests/m0/ipv6probe.c`) + roteiro de bancada hosted/tap | — | roda no hosted; os casos que falham hoje estão documentados |
| S1 ✅ mesclada [#1924](https://github.com/aros-development-team/AROS/pull/1924) | G5: liberar `in6p_moptions` no detach; solicited-node pertence ao endereço (`in6_ifaddr_priv`), all-nodes à interface; `in6_ifdetach()`. (A interface padrão do join ficou para S7.) | S0 | `mld.close-leaves`, `mld.addr-owned`, `mld.ifdetach` passam; ND sem regressão |
| S2 | G3: aceitar grupos em `in6_multihead` por `rcvif`; remover os casos fixos | S0 | o host envia para `ff02::fb`, o AROS recebe; ND e RA continuam funcionando |
| S3 | G4: entrega multicast UDP a todos os PCBs com filtro por associação/interface | S2 | dois sockets `SO_REUSEPORT` recebem; um socket sem associação na interface não recebe |
| S4 | G6: loopback de multicast na saída | S2 | dois programas no mesmo AROS se veem em `ff02::fb`; `IPV6_MULTICAST_LOOP 0` desliga |
| S5 | G7: `in6_pktinfo` público; verificar `recvmsg`/ancillary | S3 | `IPV6_PKTINFO` com ifindex e destino corretos |
| S6 | G1: zonas na API e no PCB (decisão D1) | discussão D4 | bind/connect/sendto/recvfrom com `%if`; origem recebida com `sin6_scope_id`; duas interfaces |
| S7 | G2: `in6_selectif` + `in6_selectsrc` únicos; remover as heurísticas | S6 | `sendto(ff02::fb)` de `[::]` funciona; testes de regras RFC 6724; TCP6 e ICMPv6 sem regressão |
| S8 | G8: RFC 4191 completa (preferência de roteador default + RIO, host tipo C) | — (teste autocontido usa o loopback do #1945/S4) | RA com RIO instala a rota via o roteador na interface do RA; lifetime 0 remove; expira; preferência desempata. Com várias interfaces, o gateway `fe80::` herda a limitação G1 da rota default atual, salvo se a interface for informada na instalação |
| S9 | G9: comandos multicast no `tap.device` (opcional, bancada) | — | filtro igual ao do `eth.device` unix |

Regressão em toda etapa: IPv4 multicast/mdnsd (`dnssd`), ND/SLAAC, DHCPv4, TCP sobre IPv6.

## 6. Decisões registradas (2026-10-28)

1. D1: seguir o modelo de zona explícita do `bsdsocket/Readme.md` §6.6.
2. D4: coordenação com Kal (Nick Andrews) pelo contato do mantenedor.
3. Testes: ficam neste repositório (`tests/`) até termos mais familiaridade; migrar para o tree do AROS é decisão futura.
4. Upstream: sem assinaturas do Claude Code em commits e PRs.
