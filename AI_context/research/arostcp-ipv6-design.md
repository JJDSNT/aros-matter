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
- **S8 pronta (2026-10-30)**, branch `review/arostcp-ipv6-rfc4191-v2` sobre o #1974: host tipo C (preferência do roteador default, RIO por (prefixo, roteador), `::/0` sobrepõe o cabeçalho, lifetimes de 32 bits) e limpeza dos roteadores da interface no deconfigure/detach (as entradas ficavam `installed` e a default nunca voltava depois de um reload). Teste `cunit-net-rio6` manda os RAs ao próprio link-local, sem nada no fio. Evidência: `logs/2026-10-30/s8-rfc4191/`.
- **Política de aceitação:** a S8 aceita RIOs válidas por padrão, como host tipo C da RFC 4191, que é o que os dispositivos Apple fazem como controladores Matter/Thread. O Linux, por padrão, ignora RIO (`net.ipv6.conf.*.accept_ra_rt_info_max_plen = 0`, além de `CONFIG_IPV6_ROUTE_INFO`); por isso a documentação do OpenThread manda ajustar esse sysctl no host Linux. O AROS não tem sysctl; se for preciso desligar, seria uma opção de configuração futura.
- **S8b (pendente, não reproduzida):** depois de um reload da interface, o prefixo SLAAC continua com `ndpr_autoconf = 1`, e o `nd6_prefix_slaac()` não recria o endereço global apagado no teardown; o endereço some até o prefixo expirar. Reproduzir na bancada antes de corrigir (PR separado, mexe na autoconfiguração).
- Impacto Matter: o border router Thread anuncia o prefixo OMR da malha na rede de infraestrutura como RIO nos seus RAs ([OpenThread Border Routing](https://openthread.io/reference/group/api-border-routing)). Sem RIO, o controlador só alcança os dispositivos Thread se o border router for também o roteador default.

### G10 — Tempo de vida endereço × rotas
- `ifa_refcnt` existe em `struct ifaddr`, mas não é usado; `in6_purgeaddr()` libera o endereço mesmo com rotas apontando para ele. Uso após liberação intermitente observado em `rtrequest()`. Ver [ISSUE-0009](../issues/ISSUE-0009.md).

### G16 — Observações a confirmar (captura de 2026-10-29, host como roteador com PIO/SLAAC)
- **MLD com origem global:** os Listener Reports saem de `2001:db8:4d54:1:…`; RFC 3810 §5 / RFC 2710 §3 exigem origem link-local.
  - **G16a, confirmada e corrigida → AROS #1970.** Duas causas: `in6_ifawithifp()` deixava um endereço de escopo maior, mais adiante na lista, substituir o de escopo exato (um destino link-local recebia origem global); e o MLD pedia a origem com o grupo como destino, o que dá origem global para grupos `ff05::`/`ff0e::`. Correção: comparação RFC 6724 §5 regras 2/3/7 e MLD sempre via `in6_ifaof_ifpforlinklocal()`. Evidência: `logs/2026-10-30/pr1970/`.
- **Endereços temporários se acumulando:** 5 grupos solicited-node distintos depois de ~17 RAs iguais: parece um endereço temporário (RFC 4941) novo por RA, em vez de um por prefixo até a regeneração.
- **Envio para destino global falha com `EADDRNOTAVAIL`** mesmo com endereço global SLAAC já formado: a seleção de origem via a rota default não acha o endereço. Pode ser G15 (rota default corrompida) ou outra causa; investigar junto com a G15.

### G15 — Roteamento IPv6 via roteador: quatro defeitos encadeados
Medido em 2026-10-29 com `research/logs/2026-10-29/g15/g15probe.c`, o host como roteador (RA com router lifetime 600 + PIO SLAAC):

- **G15a — gateway reescrito (confirmado).** Detalhe abaixo: `nd6_rtrequest()` sem o `return` do FreeBSD 4.11 para `RTF_GATEWAY`.
- **G15b — a rota default de RA nunca é instalada (confirmado).** `defrouter_select()` chama `rtrequest(RTM_ADD, ::, gw, NULL, RTF_GATEWAY)`. Sem máscara, a chave `::` é rota de host e colide com o nó-raiz zero da árvore radix; o `RTM_ADD` falha e o `RTM_GET` não acha nem `::`. Na prática, **o AROS nunca teve rota default IPv6 aprendida de RA**. Por isso o envio a destino global dá `EADDRNOTAVAIL` mesmo com endereço SLAAC. A rota default precisa de máscara `::/0` explícita, e o `nd6_router_route()` da S8 repetiu esse erro para `plen = 0`.
- **G15c — o próximo salto não resolve pelo vizinho do gateway (no código; medir depois de a/b).** `nd6_resolve()` guarda o estado de vizinho na própria rota do destino e pergunta (NS) pelo endereço que recebe. Falta o desvio para a entrada de vizinho do gateway, que o `nd6_output()` do KAME faz (`rt_gwroute`). O NA do roteador atualiza a entrada de vizinho dele, não a rota, então ela ficaria `INCOMPLETE` para sempre.
- **G15d — a rota do prefixo sobrevive à remoção do endereço (confirmado).** `in6_control(SIOCAIFADDR_IN6)` faz `ia->ia6_flags = ifra->ifra_flags`, mas `ia6_flags` é `ia_ifa.ifa_flags`: os `IN6_IFF_*` do pedido sobrescrevem `IFA_ROUTE`, que o `in6_ifinit()` acabou de ligar, e vão para o campo errado (deveriam ir para `ia6_ifaflags`). Sem `IFA_ROUTE`, o `in6_ifscrub()` não apaga a rota do prefixo. Medido: `fd00:4d54:77::/64` (`flags=0x101`) continua depois de `SIOCDIFADDR_IN6`, apontando para o endereço liberado. **Causa provável do uso após liberação da ISSUE-0009**, e o motivo do comentário em `if_sana.c` sobre o `in6_ifscrub()` "not reliably" apagar a rota.
- **G15e — endereços que não são link-local não passam por DAD (no código).** `nd6_dad_start()` só é chamado em `in6_if_up()`; SLAAC, temporários e estáticos (`SIOCAIFADDR_IN6`) nunca fazem DAD (RFC 4862 §5.4 exige DAD para todo unicast).

**G15a/b/c → AROS #1948** (https://github.com/aros-development-team/AROS/pull/1948): `cunit-net-route6` (master 3/3 falham, branch 3/3), e de ponta a ponta com o host como roteador: master `EADDRNOTAVAIL` ×5 e host recebe 0; branch NS para o roteador e host recebe 5. A G15c ficou confirmada pela medição (NS para o roteador, não para o destino).

Plano: ~~PR "roteamento via roteador" (G15a, b, c, com teste)~~ → PR "ciclo de vida de endereço" (G15d, e, G16; resolve a ISSUE-0009) → G14 → S8.

#### G15a — detalhe
- `nd6_rtrequest()` (`netinet6/nd6.c`) trata toda rota nova numa interface IPv6 como entrada de vizinho: no `RTM_ADD` cai no caminho de `RTM_RESOLVE`, troca o gateway por um `sockaddr_dl` vazio (`nd6_storelladdr()`) e aloca `llinfo_nd6`. O FreeBSD 4.11, que o comentário diz seguir, sai logo no início para rotas com gateway (`sys/netinet6/nd6.c:1103-1104`, `if ((rt->rt_flags & RTF_GATEWAY)) return;`). Essa linha foi omitida.
- Evidência: na bancada RFC 4191, `RTM_GET` da rota instalada por RIO devolve `flags=0x413` (`RTF_UP|RTF_GATEWAY|…`), mas o gateway vem como `AF_LINK` (família 18, len 18), não como `fe80::4d54:a`.
- Afeta toda rota via roteador: a default aprendida de RA (já antes da S8), rotas estáticas IPv6 e as rotas da RIO.
- Suspeita relacionada (a confirmar): `nd6_resolve()` resolve o vizinho sobre a rota do destino; não há o desvio para a entrada de vizinho do gateway que o `nd6_output()` do KAME faz (`rt_gwroute`). Se confirmado, nenhum pacote IPv6 para fora do link sai pelo roteador.
- Para medir: o AROS precisa de um endereço global (o RA do host deve trazer PIO com SLAAC); só com link-local, `sendto()` para destino global devolve `EADDRNOTAVAIL`, o que está correto (RFC 4291: link-local não é roteado).
- Impacto Matter: é o caminho do controlador até um dispositivo Thread atrás do border router (rota da RIO → gateway = BR).

### G19 — TCP no fio (bancada `tests/tcp/`, 2026-10-30, master `be237767fa`)
Bancada nova: o AROS é cliente do Linux do host pela tap, em IPv6; `tc` molda o link (descarte na entrada do host, atraso na saída) e o `tcpdump` lê o resultado. Evidência: `logs/2026-10-30/tcp-wire/`.
- **G19a — TCP sobre IPv6 não transfere dados em volume por um link real.** ✔ O handshake completa; cada segmento de dados sai fragmentado e só um fragmento chega ao fio; o host nunca remonta, o AROS retransmite para sempre. Três defeitos encadeados:
  - **G19b — `tcp_mss()`/`tcp_mssopt()` não conhecem IPv6.** ✔ `tcp_mss()` procura a rota pelo `inp_faddr` (IPv4, zero numa conexão IPv6): sem rota, fixa `t_maxseg = tcp_mssdflt` (1460) e retorna **antes de aplicar o MSS do par** (o Linux anunciou 1440; RFC 9293 §3.7.1). `tcp_mssopt()` anuncia MTU − `sizeof(struct tcpiphdr)` (40, IPv4): em IPv6 os cabeçalhos são 60 (RFC 6691), o certo é 1440. Segmento de 1460 + 32 (TCP com timestamps) + 40 = 1532 > 1500.
  - **G19c — a fragmentação IPv6 manda só o primeiro fragmento.** ✔ Em `ip6_output()` o laço recalcula `flen`/`more` com `m->m_pkthdr.len`, que não diminui; só `off2` avança. A segunda volta pede `m_copy()` além do fim, recebe NULL e descarta o pacote com `ENOBUFS`. Afeta também UDP maior que o MTU.
  - **G19d — o bit M (mais fragmentos) na ordem de bytes errada.** ✔ `IP6F_MORE_FRAG` já está na ordem da rede (0x0100 em little-endian); o código faz `offlg |= IP6F_MORE_FRAG` e depois `htons(offlg)`: no fio sai "offset 256, sem M" (`frag (…:256|1448)`). Em big-endian (m68k, PPC) não aparece.
- **G19e — T/TCP ainda no SYN.** ✔ O SYN leva `ccnew` (RFC 1644, Histórico pela RFC 6247; permite transação com SYN falsificado). Retirar.
- **G19f — ECN não pedido no SYN** (flags só `S`). ? O Readme diz que há suporte; ver se está desligado por padrão.
- **G19g — portas efêmeras sequenciais** (1024, 1025, …): ✔ confirma R1 no fio. ISNs aleatórios ✔.
- **G19h — fechar com dados não lidos manda FIN, não RST** (RFC 1122 §4.2.2.13, SHOULD). ✔
- **G19i — RTO: primeira retransmissão em 1,4 s, a segunda só 9 s depois** (esperado ~2,8 s com backoff). ? A investigar (relógio de 500 ms, backoff).
- Ordem proposta: G19c+d (fragmentação, simples e grave) → G19b (MSS IPv6) → G19e (T/TCP) → G19h, G19g/R1 → G19i.

### G18 — Pendências registradas nas notas dos PRs (reunidas em 2026-10-30)
Itens que cada PR declarou como "não coberto aqui". Nenhum bloqueia o Matter hoje; ficam como trabalho futuro, com a origem anotada.

**Roteamento (RFC 4191 / RFC 4861) — do #1976**
- **G18a — Seleção por alcançabilidade (RFC 4191 §3.2/§3.5, RFC 4861 §6.3.6):** um roteador preferido que o NUD julga inalcançável não é pulado; a rota continua por ele. O correto é preferir roteadores alcançáveis e, depois, a preferência.
- **G18b — Redirects (RFC 4861 §8):** `nd6_redirect_input()` não foi tocado; falta verificar se ele valida e aplica redirects corretamente com as rotas aprendidas.

**SLAAC / prefixos — achados na S8b (não reproduzidos)**
- **G18c — `nd6_prefix_lookup()` ignora a interface:** o mesmo prefixo anunciado em duas interfaces vira uma entrada só, da primeira.
- **G18d — Endereço SLAAC apagado à mão:** depois de `SIOCDIFADDR_IN6` num endereço SLAAC, o prefixo fica com `ndpr_autoconf = 1` e o RA seguinte não o recria até o prefixo expirar.

**Seleção de origem e de interface**
- **G18e — RFC 6724 regras 1, 5, 6 e 8 (do #1970):** só as regras 2, 3 e 7 estão em `in6_ifawithifp()`; as outras escolhem entre interfaces ou precisam da tabela de políticas.
- **G18f — `IPV6_PKTINFO` × endereço vinculado (do #1973):** o endereço vinculado ganha da origem dada por `IPV6_PKTINFO`, como já era para socket conectado. A RFC 3542 §6.1 e o KAME dão precedência ao `IPV6_PKTINFO`.
- **G18g — `connect()` a um grupo (do #1975):** a origem vem da zona (#1974) ou da tabela de rotas, não de `IPV6_MULTICAST_IF`.
- **G18h — Fallback da primeira interface (do #1975):** sem interface nenhuma indicada, o `ip6_output()` ainda manda multicast pela primeira interface ativa.

**API / decisões deixadas ao Kal**
- **G18i — Zona em `inp_boundif` (do #1974):** `SO_BINDTODEVICE` continua só IPv4; `connect()` link-scope sem `sin6_scope_id` mantém o comportamento antigo (o Linux devolve `EINVAL`).
- `IPV6_CHECKSUM` (G13), ICMPv6 Parameter Problem para next header desconhecido e os auxiliares de cmsg compartilhados com o UDP6 já estavam anotados em G14.

### G17 — `sendto()` prende a origem UDP6 ao socket (→ AROS #1973)
- `udp6_output()` fazia `sendto()` com `in6_pcbconnect()` + `in6_pcbdisconnect()`, e o disconnect só limpa o par: a origem escolhida ficava em `inp_laddr6`. Depois do primeiro datagrama, um socket em `[::]` só recebia no endereço de onde enviou (um responder em `[::]:5353` que responde por unicast deixa de ouvir `ff02::fb`), e nem `IPV6_PKTINFO` nem o `sin6_scope_id` escolhiam a origem (`sendto(ff02::fb%eth0)` dava `EADDRNOTAVAIL`). O IPv4 salva e restaura `inp_laddr`; o KAME nunca conecta.
- Encontrado em 2026-10-30 ao levantar a S6. Correção: destino e origem por datagrama, sem mexer no PCB (só a porta efêmera fica). `cunit-net-sendto6` master 3/3 falham, branch 3/3; bancada: `link.send-scopeid` passa a funcionar, sem regressão. Impacto Matter direto (mDNS em `[::]:5353`).

### S6 — levantamento (2026-10-30, master `343de5cddf` + #1945)
- **Zona = `inp_boundif`** (o campo do `SO_BINDTODEVICE`, hoje só usado pelo UDP IPv4; o #1945 já o respeita na entrada multicast UDP6). É o modelo do Linux (`sk_bound_dev_if`) e não muda a ABI do `struct inpcb`.
- Lacunas: `in6_pcbbind()` não confere que o endereço é nosso; `in6_pcbconnect()` ignora `sin6_scope_id`; `in6_setsockaddr()`/`in6_setpeeraddr()` e `udp6_input()` nunca preenchem `sin6_scope_id`; pacote para o próprio link-local volta por `lo0` com `rcvif = lo0` (o KAME passa o `origifp` ao `looutput()`); a conexão TCP aceita não guarda a zona (derivável do dono do endereço local link-scope).
- Abordagem: código primeiro (o Kal não respondeu às perguntas de desenho; responde a PRs). Pontos de decisão vão nas notas do PR.

### G14 — Sockets raw IPv6 ignoram as opções IPv6
- `rip6_ctloutput()` (`netinet6/icmp6.c`) é um stub que devolve 0 para qualquer opção: `setsockopt()` "funciona" sem efeito.
- `rip6_output()` monta o cabeçalho com `ip6_defhlim` e chama `ip6_output()` com opções multicast `NULL`: `IPV6_MULTICAST_HOPS/IF/LOOP` e `IPV6_UNICAST_HOPS` não se aplicam; não há `ICMP6_FILTER`. O socket raw usa `struct rawcb`, sem lugar para opções (no KAME/FreeBSD, o raw IPv6 usa o `in6pcb` e herda as opções).
- Consequência: nenhum programa no AROS gera RS/RA/NS/NA válidos (hop limit 255, RFC 4861). Impediu o teste autocontido da S8, cujo RA saía com hop limit 64 e era descartado, corretamente.
- Cuidado registrado: um teste que envia RA por raw socket com hop limit certo também o envia pela tap ao host. Um RA com router lifetime > 0 instalaria rota default no Linux do host. Testes upstream não devem fazer isso.
- **Levantamento de 2026-10-30 (master `343de5cddf`): o raw IPv6 é mais incompleto que "ignora opções".**
  - Entrada: o `icmp6_input()` só repassa Echo Reply aos sockets raw (ND, RA, MLD, erros e Echo Request nunca chegam). O `rip6_input()` (protocolos sem tratador) entrega o pacote **com** o cabeçalho IPv6, e a RFC 3542 §3 diz que socket raw IPv6 nunca recebe esse cabeçalho. Além disso, usa `ip6->ip6_nxt` como protocolo, o que erra quando há cabeçalho de extensão (o `ip6_input()` já passa o `nxt` certo).
  - Opções: `rip6_ctloutput()` e `icmp6_ctloutput()` devolvem 0 sem fazer nada; o `getsockopt()` não preenche o valor. Não existe a constante `ICMP6_FILTER` no `<netinet/icmp6.h>` (só a struct e as macros).
  - Saída: o `raw_usrreq()` recusa ancillary data com `EOPNOTSUPP`; o hop limit é sempre `ip6_defhlim` (64), mesmo para multicast (o padrão RFC 3542 é 1); não há interface de saída para multicast.
- **Desenho (KAME `raw_ip6.c`, FreeBSD 4.11):** o raw IPv6 passa a usar `inpcb` numa lista própria (`rip6cb`), e as opções IPv6 vêm do `ip6_ctloutput()`, como no UDP6. O que é só do raw (protocolo, `struct icmp6_filter`) fica num bloco privado em `inp_ppcb`, sem mudar o `struct inpcb` público. Na entrada, o `icmp6_input()` passa **cópias** aos tratadores do kernel (o Echo Request recebe cabeçalhos próprios antes do `icmp6_reflect()`, porque o `m_copym()` compartilha clusters) e entrega o original aos sockets raw, filtrado por `ICMP6_FILTER`, sem o cabeçalho IPv6 e com `IPV6_PKTINFO`/`IPV6_HOPLIMIT` se pedidos. Na saída: destino pelo `sendto()` ou pelo `connect()`; `IPV6_PKTINFO`/`IPV6_HOPLIMIT` em ancillary data; hop limit por cmsg > `IPV6_MULTICAST_HOPS`/`IPV6_UNICAST_HOPS` > padrão; checksum ICMPv6 sempre calculado pelo kernel (RFC 3542 §3.1).
- **→ AROS #1971** (`review/arostcp-ipv6-raw-options`): `cunit-net-raw6`, master 8/8 falham, branch 8/8 passam; no fio, hop limit 255/1/255 a partir da link-local (master: 64 a partir de `::`, e o `sendmsg()` com cmsg nem sai). Evidência: `logs/2026-10-30/pr1971/`.
- **Fora deste PR:** `IPV6_CHECKSUM` (o número colide com `IPV6_V6ONLY`, G13: decisão de ABI para o Kal); ICMPv6 Parameter Problem para next header desconhecido (RFC 8200 §4); `sin6_scope_id` na origem recebida (S6); a escolha de origem multicast sem interface (S7); usar os mesmos auxiliares de cmsg no UDP6 (depois do #1945, que mexe no `udp6_usrreq.c`).

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
