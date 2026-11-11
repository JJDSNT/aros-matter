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

## Condições acrescentadas (texto do ChatGPT trazido pelo usuário, 2026-11-11, aceitas)

1. **Escopo:** a zona nunca é embutida (§6.6); o par (interface, endereço) é o vizinho com escopo — a zona de um
   link-local é a interface. Regra do código novo: nenhum caminho guarda/compara o endereço com índice embutido;
   uma só representação por vizinho. Teste dos dois `fe80::1`.
2. **Cache cheio** (limite por interface): reaproveitar primeiro um STALE sem fila (o mais antigo); nunca descartar
   INCOMPLETE com pacotes à espera; sem candidato, a resolução nova falha (`ENOBUFS`); contadores de despejo e de
   falha de alocação visíveis.
3. **Ponteiros na remoção de interface:** auditoria explícita — tabela, filas das entradas e referências guardadas
   (timer, dica do TCP, roteador padrão `dr->ifp`, notificações) liberadas/limpas no `nd6_ifdetach()`;
   `remloop.py` cobre remoção repetida.
4. **Gerência preservada:** listagem (`GetRouteInfo(AF_INET6, RTF_LLINFO)` da API Roadshow, usada pelo
   `ip -6 neigh show`) passa a vir das tabelas; **socket de rotas com `RTF_LLINFO`** (`RTM_GET`/`RTM_DELETE`/
   `RTM_ADD`) desviado para o cache, como o `lla_rt_output()` do FreeBSD (`ndp -d`/`-s`), para não perder apagar/
   consultar/entrada estática. `netstat -r` sem clones: aceito.

- **Aceitação:** duas entradas independentes, cada uma com o MAC do seu enlace, nenhuma troca de interface; os 2 NS
  (contra 16) confirmam. `icmp6stat` exposta (`amiga_kernvars.c`, como o `netstat -s` lê) — o CUnit confere a
  contagem de NS enviados e a listagem.
- **Tamanho e memória:** `.text`/`.data`/`.bss` do AROSTCP antes e depois; bytes por entrada; custo fixo por
  interface; comportamento com o cache cheio. m68k também, se o build m68k daqui servir.
- Sem `lltable` genérico nem unificação com o ARP.

## Resultado (2026-11-11) — branch `review/arostcp-nd6-ifcache`, commit local `c11fa0d45b` (sem push, sem PR: aguardando o usuário)

Base: upstream/master `994fc8c9df`. Um commit (código + `cunit-net-nd6cache` + ajuste do `ndqueue6` + Readme §6.1/§6.3). Bump de versão no PR (depende de o #2218 entrar antes).

**Funcional**
- Aceitação (`zone_probe.py --rounds 8`, agora conta NS): master **16 NS** (8+8), B5 **2 NS** (1+1); 16/16 datagramas no enlace e MAC certos nos dois; controle de um enlace: 1 NS.
- `cunit-net-nd6cache` 5/5 nas duas execuções: o mesmo endereço estático em dois enlaces = duas entradas com MACs próprios (RTM_GET e listagem); envio alternado sem NS; RTM_GET sem `RTF_LLINFO` devolve a rota do prefixo; apagar um deixa o outro; cache cheio: 256 entradas esperando, nenhuma descartada, 44 `ENOBUFS`, depois da falha de resolução as entradas somem e o cache aceita de novo.
- 52 suítes ok (duas execuções). `ndqueue6` passou a apagar o vizinho com `RTF_LLINFO` + `rtm_index` (senão se pularia em silêncio).
- Benches: `defrouter.py` 5/5 (troca aos 9 s, volta aos 68; master 10/69); `remloop.py` 3 boots × 30 recargas sem crash.
- Achado durante a validação: `narouter6`/`rio6` usam endereços nossos como roteadores; o KAME fazia de cada endereço nosso um vizinho permanente (o FreeBSD também: `LLE_IFADDR`). Mantido: entrada permanente com o nosso MAC, apagada com o endereço (`nd6_ifaddr_gone()` no `in6_purgeaddr()`); entrada fixa (estática ou nossa) só obedece à flag Router de um NA.
- Benches consertados: `zone_probe.py` (contagem de NS; datagramas lidos com filtro próprio), `defrouter.py` (garante `fe80::1` na tap; o `zone_probe` o remove).

**Mudanças de comportamento a avaliar**
- Entrada apagada quando a resolução ou o NUD falham (RFC 4861 §7.2.2/§7.3.3; antes ficava NOSTATE); STALE sem uso por 1 dia é coletada.
- Packet Too Big sobre destino no próprio enlace não é mais registrado (vale o MTU do enlace; antes ia para o clone).
- `netstat -r` sem clones `L`; `ip -6 neigh` igual (listagem sintetizada, uma linha por (interface, endereço)).
- Desvio do plano: uma tabela hash global de 64 baldes com chave (interface, endereço) em vez de uma tabela por interface (custo fixo menor); limite e contagem por interface no `nd_ifinfo`.

**Tamanho (AROSTCP, `size`)**

| alvo | text | data | bss | total |
|---|---|---|---|---|
| m68k master | 268906 | 3796 | 89300 | 362002 |
| m68k B5 | 269634 (+728) | 3800 (+4) | 89660 (+360) | 363094 (+1092) |
| x86_64 master | 493913 | 7104 | 117220 | 618237 |
| x86_64 B5 | 496053 (+2140) | 7104 | 117892 (+672) | 621049 (+2812) |

**Memória por vizinho:** m68k 62 B (uma alocação) contra ~230 B antes (estado 34 + `rtentry` 148 + chave e gateway da rota clonada, duas alocações); x86_64 96 contra ~430. Custo fixo: tabela hash 256 B (m68k) / 512 B (x86_64) + 4 B por interface. Teto: 256 vizinhos por interface (~16 KB no m68k); antes sem teto (NS de qualquer origem criava clones).

Build m68k da nossa árvore: `~/aros-build-ipv6-m68k-claude` (configure `--target=amiga-m68k` com o toolchain de `~/aros-build-emu68-m68k`; precisou de `make workbench-libs-fd` antes do AROSTCP). Serve à tarefa separada de tamanho/memória da pilha atual contra a legada.

## Auditoria (2026-11-11, pedida pelo usuário a partir de comentário do ChatGPT) — commit local `11df4517ea`

1. **Tabela de 64 posições:** encadeada (`ln_hnext`), sem teto de entradas; o limite é por interface (`nd_ifinfo.nbrs`). Simulação com endereços EUI-64: 256 vizinhos → 3 comparações médias por busca; 1024 (4 enlaces cheios) → 9; 4096 (16 cheios, patológico) → 33. **Falha achada e corrigida:** interfaces com índice ≥ `ND6_MAXIFS` (sem `nd_ifinfo`) não tinham limite; agora dividem um contador com o mesmo teto.
2. **Remoção após falha:** conforme RFC 4861 §7.3.3 ("the entry SHOULD be deleted", tanto para INCOMPLETE quanto para PROBE); a fila recebe os ICMP de destino inalcançável antes (§7.2.2 MUST); o roteador padrão é avisado depois, com cópias de endereço e interface. Igual ao `nd6_llinfo_timer()` do FreeBSD.
3. **PMTU no enlace — regressão real, corrigida.** No master o PTB sobre um vizinho caía no clone criado pelo tráfego; o B5 tinha tirado isso. Agora `rt_pmtu_update()` cria uma rota de host `RTF_HOST|RTF_DYNAMIC` também para destino no enlace (como o `icmp6_mtudisc_clone()` do KAME), na interface do enlace; para link-local, na interface por onde o PTB chegou (a zona), usada só nela (`ip6_llroute()` em `ip6_output()`/`ip6_pathmtu()`); PTB do mesmo endereço vindo de outro enlace não é gravado enquanto isso. IPv4 inalterado. `cunit-net-pmtu6` ganhou ON_LINK e LINK_LOCAL (falham no master e no B5 anterior, que sem tráfego prévio não gravavam; passam agora).

Depois das correções: 52 suítes ok (duas execuções), `zone_probe` 16/16 e 1+1 NS, precodacy limpo. Tamanho: m68k +1052 text / +4 data / +364 bss (+1420); x86_64 +2576 / 0 / +704 (+3280).
