# AROSTCP: RTT e RTO em milissegundos (grupo 7, item 1)

Status: **proposta** (2026-11-07). Nenhum código escrito. Medição em
[logs/2026-11-07/rto-granularity/](logs/2026-11-07/rto-granularity/README.md).

## 1. O que foi medido

`tests/tcp/rto_probe.py`, 5.37, 8 conexões por RTT, cauda perdida depois de 20 trocas:

| RTT | RTO mediano (mín.-máx.) | RFC 6298 | FreeBSD | Linux |
|---|---|---|---|---|
| 0,4 ms | 1,28 s (1,08-1,28) | 1,0 s | ~0,23 s | ~0,2 s |
| 50 ms | 1,16 s (1,16-2,46) | 1,0 s | ~0,28 s | ~0,25 s |
| 200 ms | 2,36 s (1,06-2,36) | 1,0 s | ~0,43 s | ~0,4 s |
| 500 ms | 1,76 s (1,74-1,78) | 1,0 s | ~0,73 s | ~0,7 s |

FreeBSD = max(30 ms, SRTT + 4·RTTVAR) + 200 ms (`TCPTV_MIN`, `TCPTV_CPU_VAR`, `TCPT_RANGESET` em
`tcp_timer.h`); Linux ≈ SRTT + max(4·RTTVAR, 200 ms). Valores aproximados, para RTT estável.

## 2. Estado atual (código, 4.4BSD)

- Relógio: `tcp_now` anda no `tcp_slowtimo()` (`PR_SLOWHZ` 2, 500 ms). É monotônico (conta ticks),
  não depende de `GetSysTime()`: o problema é só a resolução.
- Amostra de RTT: `t_rtt` começa em 1 no envio e soma 1 por tick lento; com timestamps,
  `tcp_now + t_ts_offset - tsecr + 1`. Tudo abaixo de 500 ms vira 1 ou 2 ticks.
- `tcp_xmit_timer()`: `srtt` com 3 bits de fração, `rttvar` com 2; `TCP_REXMTVAL` = `(srtt>>3) +
  rttvar`; mínimo `t_rttmin` = `TCPTV_MIN` = 2 ticks (1 s). Em LAN estabiliza em 3 ticks (1,5 s).
- Timer: `t_timer[TCPT_REXMT]` em ticks lentos, decrementado no `tcp_slowtimo()`; dispara até
  500 ms antes do nominal.
- Tipos (`netinet/tcp_var.h`): `t_timer[]`, `t_rxtcur`, `t_rtt`, `t_srtt`, `t_rttvar` são `short`.
  Em ms, um `short` estoura em 32 s, abaixo do teto de 64 s (`TCPTV_REXMTMAX`).
- Karn: `t_rtt = 0` ao retransmitir (`tcp_subr.c`, `tcp_timer.c`). O caminho com timestamps não
  precisa de Karn (RFC 7323, mecanismo RTTM: o eco identifica o segmento), mas o FreeBSD descarta o `srtt`
  depois de várias retransmissões (`TCP_RTT_INVALIDATE`); aqui não.
- Backoff: `tcp_backoff[]` (1, 2, 4, ... 64) × `TCP_REXMTVAL`, teto 64 s. Conforme RFC 6298 §5.5
  e §2.5 (máximo de pelo menos 60 s).
- **Também no tick de 500 ms:** o CUBIC (`tcp_cc_cubic.c`, `epoch_start`/`elapsed` em `tcp_now`):
  a curva W(t) da RFC 9438 anda em degraus de meio segundo. O HyStart++ (RFC 9406) precisa de
  RTT por rodada em ms, e o RACK-TLP (RFC 8985) do horário de envio de cada segmento.
- O timer rápido já é de 50 ms (`PR_FASTHZ` 20; o ACK atrasado roda nele).
- `TCP_INFO` (API do Linux) está em `<netinet/tcp.h>` com `struct tcp_info`, mas o
  `tcp_ctloutput()` não o implementa.

## 3. Desenho

Um relógio em milissegundos só para o que mede tempo de ida e volta; o resto da máquina de
estados (keepalive, 2MSL, persist, SYN cache, limites de ICMP) fica no tick lento, como está.

1. **Relógio `tcp_ms`**: milissegundos de `GetUpTime()`, `u_int32_t` que dá a volta em 49 dias,
   comparado só por diferença com sinal (como `SEQ_LT`). É o relógio do TSval, como o
   `tcp_ts_getticks()` do FreeBSD e o do Linux (RFC 7323 §5.4 aceita de 1 ms a 1 s por tick). O
   deslocamento por conexão (`t_ts_offset`, #2078) continua igual. A idade do PAWS
   (`ts_recent_age`) é tempo local e fica em `tcp_now`.
2. **Amostras de RTT em ms**: do eco do timestamp quando há timestamps, senão do horário de envio do
   segmento cronometrado (`t_rtttime`, como no FreeBSD), zerado ao retransmitir (Karn).
   `t_srtt`/`t_rttvar` passam a `int`, em ms, com as frações do FreeBSD (5 e 4 bits).
3. **Timer de retransmissão em ms**: `t_rxtcur` `int` em ms; o REXMT vira um prazo em `tcp_ms`,
   conferido no `tcp_fasttimo()` (50 ms): granularidade G = 50 ms. RTO como RFC 6298 §2.3:
   `SRTT + max(G, 4·RTTVAR)`, com piso (seção 4 desta nota) e teto de 64 s; backoff como hoje.
4. **CUBIC em ms**: `epoch_start`/`elapsed` em `tcp_ms` (a RFC 9438 conta t em segundos, com a
   resolução que houver). Muda o comportamento de vazão: precisa de A/B.
5. **`TCP_INFO`**: `tcpi_rtt`, `tcpi_rttvar`, `tcpi_rto` (µs, como o Linux), `tcpi_snd_cwnd`,
   `tcpi_snd_ssthresh`, `tcpi_state`, retransmissões. Dá o teste CUnit do RTO e serve a
   aplicações (e aos benches).

## 4. Decisão: o piso do RTO

**Decidido (usuário, 2026-11-07): 200 ms, com o sysctl `net.inet.tcp.rexmit_min`** (como o
FreeBSD); o PR explica o desvio do SHOULD da RFC 6298 §2.4. Condições:

- O piso é só o piso: o RTO continua `SRTT + max(G, 4·RTTVAR)`, então pode ficar bem acima de
  200 ms. Backoff exponencial e teto de 64 s mantidos.
- **RTO inicial separado do piso: 1 s** (RFC 6298 §2.1), sem amostra de RTT. Hoje ele é 6 s
  nominais: `tcp_newtcpcb()` faz `t_rxtcur` = `((TCPTV_SRTTBASE >> 2) + (TCPTV_SRTTDFLT << 2)) >> 1`
  = 12 ticks (4.4BSD). Medir primeiro (SYN descartado, intervalo até a retransmissão).
- **A/B obrigatório contra a 5.36**, com RTT alto, jitter, reordenação e ACK atrasado do par;
  contar retransmissões espúrias (dado que o par já tinha, pela captura) e só concluir sem
  aumento relevante delas.

- **RFC 6298 §2.4:** o RTO deve ser arredondado para 1 s se for menor (SHOULD), por cautela com
  timers grossos e ACKs atrasados.
- **FreeBSD e Linux:** ~200-230 ms em LAN, há muitos anos.
- O ACK atrasado do par (até 200 ms no Linux, 40 ms típico; o AROS usa o tick de 50 ms) é o que
  um piso menor precisa cobrir para não retransmitir à toa.

Com piso de 1 s o ganho medido seria pequeno (mediana 1,16-2,36 s → ~1,0-1,05 s); a perda de
cauda continua custando 1 s até existir o TLP (que usa 2·SRTT, independente do piso). Com piso de
200 ms (sysctl `net.inet.tcp.rexmit_min`, como o FreeBSD), o RTO em LAN cai para ~0,25 s.

## 5. Commits previstos (um por mudança, cada um com o seu teste)

1. `TCP_INFO` (sem mudar o RTO): o teste mostra o estado atual (`tcpi_rto` 1,5 s em loopback).
2. Relógio em ms + amostras de RTT + timer em ms + piso de 200 ms + RTO inicial de 1 s:
   `rto_probe` A/B nos 4 RTTs, com jitter e com ACK atrasado, contando retransmissões espúrias;
   SYN descartado (RTO inicial); `tcpi_rto` no CUnit; `run_tcp`, `loss_probe` (reorder conta as
   espúrias), `tsval_probe` (que conta o TSval em ticks) sem regressão.
3. CUBIC em ms: A/B de vazão no `run_tcp`/`loss_probe` e no roteador estreito do grupo 3.

## 6. Riscos

- **Pausas do hosted** (~1,7-2,4 s sem pacotes): viram amostras de RTT grandes; o `rttvar` sobe e
  o RTO também. É o que um host real lento faria; o bench já marca STALL.
- **Custo:** um `GetUpTime()` por segmento enviado e por ACK com amostra (Disable/EClockUpdate).
  Medir no m68k antes de fechar; se pesar, ler o relógio uma vez por pacote recebido.
- **ABI:** o `tcpcb` muda de tamanho; só a libkvm/netstat o leem, e eles exigem a mesma release.
