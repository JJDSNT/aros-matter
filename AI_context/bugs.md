# Bugs encontrados — AROSTCP e arredores

Regra (usuário, 2026-11-09): todo bug achado entra aqui, com estado. Se um PR aberto o expõe, a correção
(com teste) vai nesse PR ([memória: bug-found-check-open-prs]).

Estados: **aberto** (sem correção), **corrigido (branch)** (commit local/fork, PR ainda não aberto),
**em PR** (PR aberto), **mesclado**.

## Abertos

| # | Onde | Bug | Como aparece | Achado em |
|---|---|---|---|---|
| B3 | `tcp_drain()` / recuperação de memória | **Auditado 2026-11-10, não demonstrado.** `tcp_drain()` vazio; `m_reclaim()` (que chama os `pr_drain`) só roda na falta de **mbuf** (`m_retry()`); a falta de **cluster** (`MCLALLOC`→`m_clalloc()`) não chama nada. O que um `tcp_drain()` liberaria (como o FreeBSD): as filas de remontagem, limitadas a `MAX(100, sb_hiwat/MSS)` segmentos por conexão (~543 com 768 KB). Os buffers padrão (128 KB) não entram no orçamento do autosizing: ~30 conexões com buracos poderiam segurar ~3,8 MB de fora de ordem num pool de 4 MB. No esgotamento já medido os clusters estavam em buffers não lidos (fila de remontagem vazia), onde drenar não ajuda. Para virar defeito demonstrado: bench com muitas conexões, cada uma com um buraco segurado, sob pool apertado | — | 2026-11-09 (buffers); auditado 2026-11-10 |
| B5 | rotas IPv6 / ND | **Reavaliado 2026-11-10 — é defeito de tráfego, não só gerência.** A tabela de rotas guarda `fe80::/64` uma vez (o da 2ª interface dá `EEXIST`, engolido em `in6_ifinit()`) e as entradas de vizinho são clones de rota sem zona (a zona nunca é embutida, Readme §6.6): `fe80::1` do eth0 e do eth1 são a mesma entrada. `nd6_lookup()` a muda de interface e a resolve de novo a cada uso noutro enlace. `tests/ipv6/zone_probe.py` + captura ICMPv6: 16 datagramas alternando `fe80::1%eth0`/`%eth1` → **16 NS multicast (um antes de cada datagrama)**; controle, 16 para o mesmo enlace (`--links "eth0 eth0"`) → 1 NS. Os datagramas saem pelo enlace certo (por isso parecia só gerência), mas cada troca custa uma resolução e segura o pacote até o NA. Caso real: dois roteadores com `fe80::1` (comum) em dois enlaces com tráfego. Causa de fundo: cache de vizinhos IPv6 dentro da tabela de rotas, indexado só pelo endereço | `zone_probe.py` (agora `--links`) | 2026-11-08; reavaliado 2026-11-09 e 2026-11-10 |


## Corrigidos

| Bug | Correção | Estado |
|---|---|---|
| B23 (Kal no #2218) ACD: dois ARP em 10 s tiravam para sempre um IP estático em uso (ataque trivial) | política por origem (RFC 5227 §2.4): manual nunca abandonado em uso; DHCP → dhclient recusa (socket de rotas); IPv4LL troca; duplicado sondado de novo a cada minuto (`acd_probe.py`, `dhcp_decline_probe.py --claim`, `acd_reprobe_probe.py`) | **em PR** #2218 |
| B24 (Kal no #2218) ACD: reload em lugar deixava cada endereço tentativo 3–7 s | endereço em uso que volta em 30 s mantém o estado (`arp_dad_forget()`/`arp_dad_kept()`); teste `ACD_RELOAD` | **em PR** #2218 |
| B25 (Kal no #2218) ACD: endereço não pronto capturava o tráfego do dono real — `arpresolve()` mandava ao loopback e o ARP do dono era descartado como conflito | `arpresolve()` ignora endereço não pronto; ARP do dono de um duplicado entra no cache; `arpwhohas()` pergunta de um endereço pronto; teste no `ACD_HOST` | **em PR** #2218 |
| B26 (Kal no #2218) `cunit-net-acd.c` não compilava no GCC 14 (`size_t *` onde `MiamiSysCtl()` pede `LONG *`) | `LONG mib[4]`, `LONG len` | **em PR** #2218 |
| B22 (meu, ACD não enviada): duas interfaces `IP=AUTO` — a 2ª recebe `EEXIST` da rota 169.254/16, o endereço fica sem sonda e o `autoip_claim()` tenta de novo a cada segundo para sempre | `EEXIST` = endereço posto (ACD sonda; autoip loga o limite da RFC 3927 §3.2) | corrigido antes do envio (#2218) |
| B20 ARP: entrada completa nunca reverificada e nunca envelhece enquanto usada (`arpresolve()` zera `at_timer`) — vizinho que troca de MAC sem anunciar recebe no MAC velho indefinidamente | NUD para ARP (RFC 4861 §7.3, RFC 1122 unicast poll) + dica do TCP; `arp_stale_probe.py`: master nunca volta, agora 21,4 s | **em PR** #2218 |
| B21 IPv6: `nd6_nud_hint()` existe mas ninguém chama — o TCP não confirma alcançabilidade (sondas NS desnecessárias) | ligado com `nd6_nud_hint_dst()` (próximo salto, zona pelo rcvif); `tests/ipv6/nd_hint_probe.py`: 2 → 0 NS em 90 s | **em PR** #2218 |
| B16 autoip (RFC 3927 §2.5 b): no estado DEFEND um segundo conflito era ignorado (só BOUND reagia) — o endereço nunca era abandonado | autoip passa pela ACD (defesa única, depois duplicado → outro endereço) | **em PR** #2218 |
| B17 autoip: a queda do link parava o autoip para sempre (`sana_connect()` só reiniciava se não estivesse parado) | `ss_autoip.wanted` (IP=AUTO) | **em PR** #2218 |
| B18 autoip: sondas e anúncios desde o início, com ou sem link — no boot hosted nenhum frame ARP dele chegou ao fio antes de assumir o endereço | sondas esperam a interface subir (ACD) | **em PR** #2218 |
| B19 endereço IPv4 configurado usado na hora mesmo em uso por outro host (só log "duplicate IP address") | ACD RFC 5227 (modelo NetBSD) | **em PR** #2218 |
| B14 autosizing (nosso, mesclado no #2194): conexão em TIME_WAIT (2 MSL, 1 min) segurava sua parte do orçamento com os buffers vazios — servidor enviando arquivos em sequência a 100 ms: 59 → 20 → 10 Mbit/s | `tcp_autobuf_release()` na entrada em TIME_WAIT (como o FreeBSD libera o socket ali); `cwnd_probe --repeat 3`: 59/59/59 Mbit/s | **mesclado** #2208 |
| B15 `cunit-net-tcpinfo` AUTOSIZE (nosso, #2194): uma transferência de 4 MB no loopback às vezes não enche o buffer (2 em 24 no master) — falhava 1× em 51 suítes | até três transferências antes de olhar | **mesclado** #2208 |
| B11 `cunit-net-sblock` (nosso, #2078): `BLOCKING_WAITS` exigia ≥ 2 s com os dados chegando ~2 s depois de `t0` (margem zero; falhou 1× na suíte, execução básica) | asserção: esperou ≥ metade disso; commit próprio no A | **mesclado** #2194 |
| B12 tap.device (nosso, A): frame retido para sempre — um opener que lê um tipo uma vez e para, aberto, trava a recepção da unidade (Kal no #2194) | prazo de 50 ms (`TAP_HOLD_MS`), depois descarta e esquece o tipo até o próximo `CMD_READ`; `tests/tap/hold_probe.py` | **mesclado** #2206 |
| B13 autosizing (nosso, A): `SB_MAX` 2 MB deixava `SO_SNDBUF`/`SO_RCVBUF` pegarem ~1,8 MB fora do orçamento; tetos de 1 MB e orçamento de 3/8 de um teto configurado, não da memória existente (o pool nunca devolve) — Kal no #2194 | `SB_MAX` 512 KB, `sbreserve_max()`; tetos pela memória livre (off < 16 MB, 1/64, ≤ 1 MB e ≤ orçamento), pool pelo que o sistema pode ceder a cada crescimento | **mesclado** #2194 |
| `tcp_reass()` recusava o segmento em `rcv_nxt` com 100 na fila: conexão travava para sempre | segmento em `rcv_nxt` sempre entra; limite = janela de segmentos de pelo menos o MSS padrão (Kal: `MAX(t_maxseg, tcp_mssdflt)`); teste CUnit | **mesclado** #2178 |
| B10 `TCP_MINMSS` declarado e não aplicado: MSS do par até 64, MTU de rota/PMTU sem piso (achado pelo Kal no #2178) | `tcp_minmss` 216 (sysctl `net.inet.tcp.minmss`) para oferta, rota e PMTU; IPv4 sem DF abaixo do piso; `TCP_MAXSEG` respeita; testes tcpinfo (MTU de rota 128: 204, master 76) e sysctl | **mesclado** #2178 (3º commit, 5.40) |
| tap.device informava 10 Mbit/s → poucos pedidos de leitura → rajadas descartadas | BPS 1 Gbit/s | **mesclado** #2178 |
| tap.device descartava quadro sem pedido pendente (órfão) | segura o quadro até o próximo CMD_READ | **mesclado** #2206 |
| `sana_poll()` esvaziava a porta antes de rodar o IP → `ipintrq` transbordava | protocolos a cada 32 respostas | **mesclado** #2194 |
| Conexão aceita (syncache) sem RTT até enviar dados (RTO 1 s em receptor) | amostra do timestamp no ACK final | **mesclado** #2194 |
| B8 Rota com gateway link-local ignorava a zona (tráfego saía pela 1ª interface) | `ifa_ifwithroute()` usa a interface da zona; teste em `cunit-net-prefix6if` | **mesclado** #2193 |
| B6 `route` sem zonas IPv6 nem prefixos | `ADDR%ZONE`, `ADDR/LEN`, `-prefixlen` | **mesclado** #2179 |
| (meu, no #2179) `K_PREFIXLEN` com 41, o valor do `K_SHOW`: `route prefixlen` rodava show e `-show` virava `-prefixlen` (Kal) | `K_PREFIXLEN` 42, depois do `K_SHOW`; testado no AROS | **mesclado** #2179 |
| B9 `route` imprimia gateway de enlace em bytes crus | `link#N` / `link_ntoa()` (netlib, que já existia; corrigido o `:` sobrando e o limite do buffer) | **mesclado** #2179 |
| B4 `IPV6_CHECKSUM` ausente e com o número do `IPV6_V6ONLY` | número 7 (Linux), saída/entrada no raw6 com o `m_copyback()` que já existia em `net/rtsock.c` (agora declarado em `<sys/mbuf.h>`); testes no `cunit-net-raw6` | **mesclado** #2193 |
| B7 RTO/PTO esperavam o tique de 50 ms | pedido próprio ao timer.device no prazo mais cedo (`tcp_timer_want()`/`tcp_rexmt_due()`): RTO 0,200 s exato, cauda 134 → 59 ms | **mesclado** #2208 |
| B2 Segmentos parciais no meio de uma escrita (10 KB em 10 segmentos) | `SB_MORETOCOME` (FreeBSD `PRUS_MORETOCOME`), teste CUnit (7 segmentos; antes 10) | **mesclado** #2208 |
| B1 Guerra de ACKs (dropafterack sem limite; AROS travava) | 5/s por conexão (`tcp_ackwar_ok()`, FreeBSD `ack_war`), teste CUnit (11 ACKs/s; antes travava) | **mesclado** #2208 |
| Recuperação falsa (reordenação) nunca desfeita | anulação por D-SACK | **mesclado** #2208 |
| `netstat -m` falhava sempre ("unexpected change to mbstat") | `MTCOUNT` + `m_memused` | **mesclado** #2179 |
| timer.device hosted contava tiques de SIGALRM (perdidos) | relógio monotônico do host | **mesclado** #2175 |
| Esgotamento do pool com buffers grandes (orçamento só pelo uso instantâneo) | orçamento em custo de pool | nunca chegou ao upstream (corrigido antes do commit, G9) |

## Bugs do bench (aros-matter) já corrigidos

- netem com limite padrão de 1000 pacotes descartava janelas grandes a 100 ms (`run_tcp.tc_delay`, `limit 10000`).
- `tail_probe`: PSH não marca fim de rajada (filtro por número de sequência); Nagle segurava a cauda (TCP_NODELAY).
- Relógio de parede do WSL2 dá saltos (+1,2 s/32 s): capturas convertidas para monotônico (`ClockMap`).
