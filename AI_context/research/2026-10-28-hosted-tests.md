# Testes no AROS hosted (linux-x86_64) — 2026-10-28

Primeiros testes **executados** (não só leitura de código). Logs em [`logs/2026-10-28/`](logs/2026-10-28/).

## Ambiente

- Imagem: `~/aros-midihub/build-aros-linux/bin/linux-x86_64/AROS`, compilada a partir de `~/AROS` em `95a501ff47` (2026-10-12; o binário AROSTCP é de 2026-10-11).
- `netinet6/` em `~/AROS` é **idêntico** ao upstream `cbca98214f` (2026-10-28): `diff -rq` não acusa nenhum arquivo. Os resultados de IPv6 valem para o upstream atual.
- Cross-compiler: `.../tools/crosstools/x86_64-aros-g++` 10.5.0.
- Execução: `tools/hosted-run.sh` (boot sem interface via `xvfb-run`, script em `S:User-Startup`, depois `Shutdown`).
- Rede: tap isolada `aros0` no host (`tools/tap-up.sh`, sem bridge), `tap.device` unit 0 → AROSTCP `eth0` 192.168.166.2.

## C++ (ISSUE-0002)

| Teste | Resultado |
|---|---|
| `-std=gnu++17` e `-std=gnu++20` com `-fno-exceptions -fno-rtti`: optional, variant, string_view, if constexpr, structured bindings, atomic, chrono::steady_clock | ✅ compila e roda (`cxx17.log`) |
| `std::mutex`/`std::recursive_mutex` + 4 `pthread`s × 1000 incrementos | ✅ `n=4000` (`mutex-pthread.log`) |
| `std::thread` create/join | ✅ rc=0 |
| `_GLIBCXX_HAS_GTHREADS` | definido |

## IPv6 / UDP / multicast (ISSUE-0001) — `tests/m0/ipv6probe.c` + `tests/m0/peer_mdns6.py`

| Verificação | Resultado |
|---|---|
| `socket(AF_INET6, SOCK_DGRAM)`, `IPV6_V6ONLY` | ✅ |
| unicast `[::1]` sendto/`WaitSelect`/recvfrom | ✅ |
| `if_nametoindex` (miami.library) | ✅ lo0=1, eth0=2 |
| `SIOCGLIFADDR` lista endereços IPv6 | ✅ `::1`, `fe80::…` em eth0 (link-local EUI-64 automático) |
| dois sockets `[::]:5353` com `SO_REUSEPORT` | ✅ bind |
| `IPV6_JOIN_GROUP ff02::fb`, `IPV6_MULTICAST_IF`, `IPV6_MULTICAST_LOOP` | ✅ setsockopt; o relatório MLD sai no fio |
| **sendto ff02::fb** de socket ligado a `[::]` | ❌ `EADDRNOTAVAIL` (lo0 e eth0) → bug A |
| sendto ff02::fb de socket ligado ao link-local (contorno) | ✅ o host recebe |
| **recepção** de multicast `ff02::fb` vindo do host | ❌ nada em 15 s; o host pôs ~15 datagramas no fio (tcpdump) → bug B |
| `IPV6_PKTINFO` na recepção | não verificado (nenhum datagrama chegou) |

Nota: numa rodada anterior o script do host entrou em loop com o próprio multicast e inundou a tap. Esse resultado foi descartado, e o script foi corrigido (`IPV6_MULTICAST_LOOP 0`, ritmo de 1/s).

## Bugs no AROSTCP (revisão `cbca98214f`) — causa confirmada pela leitura do código

**A. sendto multicast sem bind unicast falha.** `udp6_output()` chama `in6_pcbconnect()` antes de olhar `sin6_scope_id`/`IPV6_MULTICAST_IF`. Em `netinet6/in6_pcb.c:179-196`, `in6_pcbconnect()` escolhe a origem só por `rtalloc(dst)`. Como não há rota para `ff02::/16`, devolve `EADDRNOTAVAIL`. A seleção correta por interface (`udp6_usrreq.c:226-232`, `in6_ifawithifp(oifp, …)`) nunca é alcançada.
Fix proposto: em `in6_pcbconnect()`, quando o destino for multicast ou link-local, usar a interface de `sin6_scope_id` ou de `in6p_moptions->im6o_multicast_ifp` e selecionar a origem com `in6_ifawithifp(ifp, dst)`.

**B. Grupos multicast entrados não são aceitos na entrada.** `netinet6/ip6_input.c:541-562` aceita multicast só para solicited-node e `ff02::1`. A lista `in6_multihead`, que `IPV6_JOIN_GROUP` preenche via `in6_addmulti()` (`in6_proto.c:219`, `in6.c:764-806`), não é consultada. `ff02::fb` é descartado.
Fix proposto: aceitar quando `(dst, m->m_pkthdr.rcvif)` estiver em `in6_multihead`.

**C. Multicast UDP é entregue a um único socket.** `udp6_input()` (`udp6_usrreq.c:389-391`) usa um `in6_pcblookup()`. Para destino multicast, o BSD entrega uma cópia a cada PCB da porta que participa do grupo. Sem isso, `SO_REUSEPORT` na 5353 não permite que o Matter conviva com um mdnsd IPv6.
Fix proposto: no caso multicast, percorrer `udb`, filtrar por porta e grupo (`in6p_moptions`) e entregar com `m_copy`.

**D. (menor) `sin6_scope_id` não é preenchido no endereço de origem recebido** (`udp6_usrreq.c:377-381`). Responder a `fe80::…` exige saber a interface; dá para contornar com `IPV6_PKTINFO`, mas o certo é preencher a partir de `rcvif->if_index` para origem link-local.

Mantenedores da pilha IPv6 (git log de `netinet6/`): principalmente Nick Andrews (45 de 47 commits).

## Outras lacunas de API para o port

- `struct in6_pktinfo` ausente dos headers públicos (definida só em `udp6_usrreq.c:104`); `IPV6_PKTINFO`/`IPV6_RECVPKTINFO` estão em `netinet/in.h`.
- `getifaddrs()` não é exportada; use `SIOCGLIFADDR` (v6) / `SIOCGIFCONF` (v4) e `if_nametoindex` (miami.library).
- Sockets passam pela bsdsocket.library: `WaitSelect()` em vez de `select()`, `CloseSocket()`, `IoctlSocket()`, errno via `SocketBaseTags(SBTC_ERRNOPTR)`. O `SystemLayerImplSelect` do SDK precisa de uma camada de adaptação.
- `tap.device` não implementa `S2_ADDMULTICASTADDRESS`/`S2_MULTICAST`, mas repassa todo multicast (`iotask.c:73-80`). Para a bancada isso não bloqueia.
