# Bugs encontrados — AROSTCP e arredores

Regra (usuário, 2026-11-09): todo bug achado entra aqui, com estado. Se um PR aberto o expõe, a correção
(com teste) vai nesse PR ([memória: bug-found-check-open-prs]).

Estados: **aberto** (sem correção), **corrigido (branch)** (commit local/fork, PR ainda não aberto),
**em PR** (PR aberto), **mesclado**.

## Abertos

| # | Onde | Bug | Como aparece | Achado em |
|---|---|---|---|---|
| B3 | `tcp_drain()` / `MCLALLOC` | `tcp_drain()` vazio, e a falta de **cluster** nem chama `m_reclaim()` (só a de mbuf, `m_retry()`). **Baixa prioridade**: no esgotamento medido, os clusters estavam em buffers de recepção não lidos, não em filas fora de ordem (0 segmentos), então não teria ajudado; testar exige esgotar o pool dentro das suítes | leitura do código + instrumentação do teste de pressão | 2026-11-09 (buffers) |
| B5 | rotas IPv6 | **Rebaixado (não reproduz como defeito de tráfego):** `fe80::1` em dois links (`tests/ipv6/zone_probe.py`): UDP e TCP saem 8/8 pela interface da zona, para o MAC certo. Sobra só gerência: a tabela tem um `fe80::/64` (o da 1ª interface; o da 2ª dá `EEXIST` engolido em `in6_ifinit()`), então métricas/`route get` de link-local não distinguem a interface. Junto com o B6 | `rtssthresh.c` precisou da zona 0 | 2026-11-08; reavaliado 2026-11-09 |


## Corrigidos

| Bug | Correção | Estado |
|---|---|---|
| B11 `cunit-net-sblock` (nosso, #2078): `BLOCKING_WAITS` exigia ≥ 2 s com os dados chegando ~2 s depois de `t0` (margem zero; falhou 1× na suíte, execução básica) | asserção: esperou ≥ metade disso; commit próprio no A | **em PR** #2194 |
| B12 tap.device (nosso, A): frame retido para sempre — um opener que lê um tipo uma vez e para, aberto, trava a recepção da unidade (Kal no #2194) | prazo de 50 ms (`TAP_HOLD_MS`), depois descarta e esquece o tipo até o próximo `CMD_READ`; `tests/tap/hold_probe.py` | **em PR** #2206 |
| B13 autosizing (nosso, A): `SB_MAX` 2 MB deixava `SO_SNDBUF`/`SO_RCVBUF` pegarem ~1,8 MB fora do orçamento; tetos de 1 MB e orçamento de 3/8 de um teto configurado, não da memória existente (o pool nunca devolve) — Kal no #2194 | `SB_MAX` 512 KB, `sbreserve_max()`; tetos pela memória livre (off < 16 MB, 1/64, ≤ 1 MB e ≤ orçamento), pool pelo que o sistema pode ceder a cada crescimento | **em PR** #2194 |
| `tcp_reass()` recusava o segmento em `rcv_nxt` com 100 na fila: conexão travava para sempre | segmento em `rcv_nxt` sempre entra; limite = janela de segmentos de pelo menos o MSS padrão (Kal: `MAX(t_maxseg, tcp_mssdflt)`); teste CUnit | **mesclado** #2178 |
| B10 `TCP_MINMSS` declarado e não aplicado: MSS do par até 64, MTU de rota/PMTU sem piso (achado pelo Kal no #2178) | `tcp_minmss` 216 (sysctl `net.inet.tcp.minmss`) para oferta, rota e PMTU; IPv4 sem DF abaixo do piso; `TCP_MAXSEG` respeita; testes tcpinfo (MTU de rota 128: 204, master 76) e sysctl | **mesclado** #2178 (3º commit, 5.40) |
| tap.device informava 10 Mbit/s → poucos pedidos de leitura → rajadas descartadas | BPS 1 Gbit/s | **mesclado** #2178 |
| tap.device descartava quadro sem pedido pendente (órfão) | segura o quadro até o próximo CMD_READ | **em PR** #2206 |
| `sana_poll()` esvaziava a porta antes de rodar o IP → `ipintrq` transbordava | protocolos a cada 32 respostas | **em PR** #2194 |
| Conexão aceita (syncache) sem RTT até enviar dados (RTO 1 s em receptor) | amostra do timestamp no ACK final | **em PR** #2194 |
| B8 Rota com gateway link-local ignorava a zona (tráfego saía pela 1ª interface) | `ifa_ifwithroute()` usa a interface da zona; teste em `cunit-net-prefix6if` | **mesclado** #2193 |
| B6 `route` sem zonas IPv6 nem prefixos | `ADDR%ZONE`, `ADDR/LEN`, `-prefixlen` | **mesclado** #2179 |
| (meu, no #2179) `K_PREFIXLEN` com 41, o valor do `K_SHOW`: `route prefixlen` rodava show e `-show` virava `-prefixlen` (Kal) | `K_PREFIXLEN` 42, depois do `K_SHOW`; testado no AROS | **mesclado** #2179 |
| B9 `route` imprimia gateway de enlace em bytes crus | `link#N` / `link_ntoa()` (netlib, que já existia; corrigido o `:` sobrando e o limite do buffer) | **mesclado** #2179 |
| B4 `IPV6_CHECKSUM` ausente e com o número do `IPV6_V6ONLY` | número 7 (Linux), saída/entrada no raw6 com o `m_copyback()` que já existia em `net/rtsock.c` (agora declarado em `<sys/mbuf.h>`); testes no `cunit-net-raw6` | **mesclado** #2193 |
| B7 RTO/PTO esperavam o tique de 50 ms | pedido próprio ao timer.device no prazo mais cedo (`tcp_timer_want()`/`tcp_rexmt_due()`): RTO 0,200 s exato, cauda 134 → 59 ms | corrigido (B, `review/arostcp-recovery`; PR depois do #2194) |
| B2 Segmentos parciais no meio de uma escrita (10 KB em 10 segmentos) | `SB_MORETOCOME` (FreeBSD `PRUS_MORETOCOME`), teste CUnit (7 segmentos; antes 10) | corrigido (B, `review/arostcp-recovery`; PR depois do #2194) |
| B1 Guerra de ACKs (dropafterack sem limite; AROS travava) | 5/s por conexão (`tcp_ackwar_ok()`, FreeBSD `ack_war`), teste CUnit (11 ACKs/s; antes travava) | corrigido (B, `review/arostcp-recovery`; PR depois do #2194) |
| Recuperação falsa (reordenação) nunca desfeita | anulação por D-SACK | corrigido (B, `review/arostcp-recovery`; PR depois do #2194) |
| `netstat -m` falhava sempre ("unexpected change to mbstat") | `MTCOUNT` + `m_memused` | **mesclado** #2179 |
| timer.device hosted contava tiques de SIGALRM (perdidos) | relógio monotônico do host | **mesclado** #2175 |
| Esgotamento do pool com buffers grandes (orçamento só pelo uso instantâneo) | orçamento em custo de pool | nunca chegou ao upstream (corrigido antes do commit, G9) |

## Bugs do bench (aros-matter) já corrigidos

- netem com limite padrão de 1000 pacotes descartava janelas grandes a 100 ms (`run_tcp.tc_delay`, `limit 10000`).
- `tail_probe`: PSH não marca fim de rajada (filtro por número de sequência); Nagle segurava a cauda (TCP_NODELAY).
- Relógio de parede do WSL2 dá saltos (+1,2 s/32 s): capturas convertidas para monotônico (`ClockMap`).
