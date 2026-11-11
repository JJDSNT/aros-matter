# B5 — cache de vizinhos IPv6 por interface — plano (2026-11-11)

Decisão do usuário (2026-11-10): corrigir o B5 **antes** do grupo multicast e do G12, em branch e PR próprios;
cache de vizinhos por interface separado da tabela de rotas (não embutir zona no endereço); planejar antes de
implementar. Requisitos trazidos pelo usuário (texto do ChatGPT): integração com o roteamento preservada (a rota
escolhe próximo salto e interface; o ND resolve o L2 do par (interface, endereço)), ciclo de vida, concorrência,
regressão ampla e o critério de aceitação abaixo.

## Evidência (B5 em bugs.md)

`tests/ipv6/zone_probe.py`: 16 datagramas alternando `fe80::1%eth0`/`%eth1` → 16 NS multicast; controle
(`--links "eth0 eth0"`) → 1 NS.

## Critério de aceitação

Depois da primeira resolução em cada interface, alternar os dois vizinhos **não provoca nova resolução** enquanto as
entradas estiverem alcançáveis: 16 datagramas alternados → **2 NS** (um por enlace).

## Estado atual (lido no código)

- Modelo KAME antigo: cada vizinho é uma **rota de host clonada** (`RTF_LLINFO`) de uma rota de prefixo
  `RTF_CLONING`; o estado (`struct llinfo_nd6`: estado, fila, prazos, `ln_router`) fica em `rt_llinfo`; o MAC no
  `rt_gateway` (sockaddr_dl) da própria rota; lista global `llinfo_nd6`.
- Chave = só o endereço (zona nunca embutida, Readme §6.6) → `fe80::1` do eth0 e do eth1 são **a mesma entrada**;
  `nd6_lookup(dst, create, ifp)` a **move de interface e a resolve de novo** (`nd6.c:358`).
- **Ponto único de resolução:** `nd6_resolve(ifp, rt, m, dst, lladdr)`, chamado por `sana_output()`
  (`if_sana.c:1632`); para `RTF_GATEWAY` já resolve o roteador como próximo salto (`nd6_lookup(gw, 1, ifp)`).
- Consumidores de `rt_llinfo`/`RTF_LLINFO`/`nd6_lookup()` fora do `nd6.c`: `ip6_output.c` (o atalho link-local que
  põe o clone do vizinho em `ro_rt`; `ip6_pathmtu()` para link-local), `nd6_nbr.c` (NA/NS: criar/atualizar entrada),
  `nd6_rtr.c:281` (alcançabilidade do roteador padrão), `api/amiga_roadshow.c:829` (listagem: `ip neigh` lê os
  vizinhos da tabela de rotas, expiração do `ln_expire`), `kern/amiga_cstat.c` (flag `L` no netstat).
- **Concorrência:** `nd6.c`/`nd6_nbr.c` não usam `spl`; dependem de quem chama: saída via `sosend()` em `splnet`
  (`uipc_socket.c:612`), timers em `splsoftclock` (mesmo mutex único do `spl`, `amiga_time.c:387`), entrada no daemon.
  A listagem pela API varre a tabela de rotas.

## Desenho proposto

**Entrada de vizinho = (interface, endereço IPv6)**, num cache por interface, fora da tabela de rotas — o conceito
do `lltable` do FreeBSD (8+: "arp-v2", ND/ARP desacoplados do `rtentry`), **não o código**.

- `struct nd6_nbr` (evolução da `llinfo_nd6`): `ifp`, endereço, endereço de enlace (+ comprimento), estado,
  prazos (`ln_expire`/`ln_ntick`, relógio monotônico atual), `ln_asked`, `ln_router`, fila. Tabela hash por
  interface pendurada no `nd_ifinfo` (`nd6_ndi[]`), com **limite por interface** (ex.: 256; despeja o STALE mais
  antigo) — memória limitada em máquina pequena.
- **Roteamento:** continua escolhendo próximo salto e interface. As rotas de prefixo IPv6 **deixam de clonar**
  rotas de host para o ND (`nd6_rtrequest(RTM_RESOLVE)` não cria mais `llinfo`). `nd6_resolve()`: próximo salto =
  gateway (se `RTF_GATEWAY`) ou destino; entrada = `nd6_nbr_lookup(ifp, salto, criar)`. Some o "mover entre
  interfaces" do `nd6_lookup()` e o atalho do `ip6_output()` que punha o clone em `ro_rt` (fica só a escolha do
  enlace pela zona, com `rt = NULL` para o `if_output`).
- **PMTU:** as rotas de host de PMTU (RTF_DYNAMIC via roteador, #2005) não dependem do `RTF_LLINFO` — ficam. Para
  link-local, `ip6_pathmtu()` passa a usar o MTU do enlace (`nd6_ifinfo()->linkmtu` / `if_mtu`).
- **Consumidores reescritos:** `nd6_cache_lladdr()` (NS/RS/RA/Redirect), entrada de NA (`nd6_nbr.c`), alcançabilidade
  do roteador padrão (`nd6_rtr.c`: busca por `(dr->ifp, dr->rtaddr)`), dicas de NUD (`nd6_nud_hint_dst()` por
  `(ifp, salto)`), Redirect, timer (`nd6_timer()` percorre as tabelas por interface), listagem (`amiga_roadshow.c`:
  as linhas de vizinho passam a vir das tabelas, mesmo formato — `ip neigh` continua igual; o `netstat -r` deixa de
  mostrar clones `L`, como no FreeBSD moderno).
- **Ciclo de vida:** criar ao resolver e ao receber NS/RS/RA/NA/Redirect com endereço de enlace; remover ao esgotar
  as sondas (como hoje), por coleta de STALE antigos e pelo limite; **interface removida** (`nd6_ifdetach()`):
  libera a tabela; **queda de enlace** (`S2EVENT_DISCONNECT`): esvazia a tabela (rede nova); mudança dos nossos
  endereços não mexe nos vizinhos; prefixo removido: entradas ficam até a coleta (FreeBSD igual).
- **Concorrência:** mesma regra do código atual, escrita: todo acesso às tabelas em `spl` (saída/entrada/timer já
  chegam assim); a listagem da API passa a tomar `splnet`; alocação `M_NOWAIT`, nenhuma espera dentro do `spl`.

## O que do `lltable` do FreeBSD é necessário

Necessário: a **ideia** — tabela L3→L2 por interface, independente do `rtentry`, consultada pelo próximo salto que a
rota deu. Não necessário agora: o framework genérico (ops por família, `LLE_WLOCK`/refcount/epoch, `ro_lle` no cache
de rota, ARP e ND na mesma estrutura). O ARP do AROS já tem tabela por interface própria (`sana2arp.c`); unificar
ARP e ND num `lltable` comum seria um refactor maior **sem lacuna demonstrada** — registrar como possibilidade futura.

## Escopo estimado

`nd6.c` (a maior parte), `nd6_nbr.c`, `nd6_rtr.c`, `ip6_output.c`, `in6.c` (flags da rota de prefixo),
`icmp6.c` (Redirect), `api/amiga_roadshow.c`; Readme §6.1/§6.6. Um commit (a mudança é uma), talvez dois se a
listagem da API ficar separável. Bump no último. PR próprio depois do #2218 (um PR do AROSTCP por vez).

## Testes

- **Aceitação:** `zone_probe.py` passa a contar os NS (captura ICMPv6) — alternando: 2 NS; controle: 1. Antes: 16.
- **CUnit novo** (duas taps; cada uma tem `fe80::1` no host): mandar alternado a `fe80::1%eth0`/`%eth1` e conferir
  (a) duas entradas de vizinho `fe80::1`, uma por interface, na listagem; (b) o contador de NS enviados (`icmp6stat`)
  subiu 2, não 16 — se o contador estiver exposto.
- **Regressão** (as suítes de IPv6 e as 52): `ndqueue6`, `nud6`, `naflags6`, `narouter6`, `redirect6`, `rio6`,
  `route6`, `prefix6if`, `slaac6`, `slaaclife`, `pmtu6`, `scope6`, `srcaddr6`, `sendto6`, `tcpmss6`, `mld6`,
  `bindtodev6`, `addrflags6`, `unreach6`, `frag6`, `icmp6err`. Benches: `zone_probe.py` (aceitação),
  `defrouter.py` (alcançabilidade do roteador), `nd_hint_probe.py` (dica do TCP), `remloop.py` (remoção de interface).
