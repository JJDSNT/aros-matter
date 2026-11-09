# Bugs encontrados — AROSTCP e arredores

Regra (usuário, 2026-11-09): todo bug achado entra aqui, com estado. Se um PR aberto o expõe, a correção
(com teste) vai nesse PR ([memória: bug-found-check-open-prs]).

Estados: **aberto** (sem correção), **corrigido (branch)** (commit local/fork, PR ainda não aberto),
**em PR** (PR aberto), **mesclado**.

## Abertos

| # | Onde | Bug | Como aparece | Achado em |
|---|---|---|---|---|
| B3 | `tcp_drain()` / `MCLALLOC` | `tcp_drain()` vazio, e a falta de **cluster** nem chama `m_reclaim()` (só a de mbuf, `m_retry()`). **Baixa prioridade**: no esgotamento medido, os clusters estavam em buffers de recepção não lidos, não em filas fora de ordem (0 segmentos), então não teria ajudado; testar exige esgotar o pool dentro das suítes | leitura do código + instrumentação do teste de pressão | 2026-11-09 (buffers) |
| B4 | `netinet/in.h` | `IPV6_CHECKSUM` vale 26, o mesmo número de `IPV6_V6ONLY`; e não está implementado para raw IPv6 não-ICMPv6 (RFC 3542 §3.1) | teste da remontagem (raw6 sem checksum) | 2026-11-09 |
| B5 | rotas IPv6 | Rotas link-local com zona 0: uma `fe80::/64` para todas as interfaces (limitação do G1) | `rtssthresh.c` precisou da zona 0 | 2026-11-08 |
| B6 | `route` (C:) | Sem zonas IPv6 nem `-prefixlen` | métricas de rota (P1) | 2026-11-08 |

## Corrigidos

| Bug | Correção | Estado |
|---|---|---|
| `tcp_reass()` recusava o segmento em `rcv_nxt` com 100 na fila: conexão travava para sempre | segmento em `rcv_nxt` sempre entra; limite = janela de segmentos; teste CUnit | **em PR** #2178 |
| tap.device informava 10 Mbit/s → poucos pedidos de leitura → rajadas descartadas | BPS 1 Gbit/s | **em PR** #2178 |
| tap.device descartava quadro sem pedido pendente (órfão) | segura o quadro até o próximo CMD_READ | corrigido (G9, `review/arostcp-rxbuf`) |
| `sana_poll()` esvaziava a porta antes de rodar o IP → `ipintrq` transbordava | protocolos a cada 32 respostas | corrigido (G9) |
| Conexão aceita (syncache) sem RTT até enviar dados (RTO 1 s em receptor) | amostra do timestamp no ACK final | corrigido (G8, `review/arostcp-ack-timers`) |
| B7 RTO/PTO esperavam o tique de 50 ms | pedido próprio ao timer.device no prazo mais cedo (`tcp_timer_want()`/`tcp_rexmt_due()`): RTO 0,200 s exato, cauda 134 → 59 ms | corrigido (`review/arostcp-robust`) |
| B2 Segmentos parciais no meio de uma escrita (10 KB em 10 segmentos) | `SB_MORETOCOME` (FreeBSD `PRUS_MORETOCOME`), teste CUnit (7 segmentos; antes 10) | corrigido (`review/arostcp-robust`) |
| B1 Guerra de ACKs (dropafterack sem limite; AROS travava) | 5/s por conexão (`tcp_ackwar_ok()`, FreeBSD `ack_war`), teste CUnit (11 ACKs/s; antes travava) | corrigido (`review/arostcp-robust`) |
| Recuperação falsa (reordenação) nunca desfeita | anulação por D-SACK | corrigido (G10, `review/arostcp-tlp`) |
| `netstat -m` falhava sempre ("unexpected change to mbstat") | `MTCOUNT` + `m_memused` | **em PR** #2179 |
| timer.device hosted contava tiques de SIGALRM (perdidos) | relógio monotônico do host | **em PR** #2175 |
| Esgotamento do pool com buffers grandes (orçamento só pelo uso instantâneo) | orçamento em custo de pool | corrigido antes do commit (G9) |

## Bugs do bench (aros-matter) já corrigidos

- netem com limite padrão de 1000 pacotes descartava janelas grandes a 100 ms (`run_tcp.tc_delay`, `limit 10000`).
- `tail_probe`: PSH não marca fim de rajada (filtro por número de sequência); Nagle segurava a cauda (TCP_NODELAY).
- Relógio de parede do WSL2 dá saltos (+1,2 s/32 s): capturas convertidas para monotônico (`ClockMap`).
