# AROSTCP: RACK (RFC 8985 §6) — desenho (P4b)

Status: **proposta** (2026-11-09). Complementa o TLP (G10, `review/arostcp-tlp`).

## 1. Por quê (medido)

- `loss_probe.py` **reorder** (sem perda; 1 em 10 segmentos chega 5 ms adiantado): 28-47 retransmissões
  por MB, **todas desnecessárias** (fast retransmit por DupThresh = 3 segmentos SACKados acima).
- **lostrexmit**: o AROS já recupera sem RTO (0,34-0,37 s), pela regra 3 do NextSeg. RACK tornaria isso
  explícito (retransmissão perdida detectada por tempo), mas não há ganho medido aqui.
- **Cauda com vários segmentos perdidos**: o TLP reenvia só o último; se ele for SACKado, os anteriores só
  viram "perdidos" com DupThresh (3 segmentos acima) — com 1 SACKado, esperam o RTO. RACK marca-os perdidos
  porque foram enviados antes do segmento entregue (há mais de RTT + reo_wnd).

## 2. O que falta no AROSTCP

RACK precisa do **horário de envio por segmento**; o AROSTCP guarda um fluxo de bytes (`so_snd`) e um
placar SACK de 32 faixas (`t_sack_blks`), sem horários. O TSecr dos ACKs dá o horário de envio do segmento
que provocou o ACK (TSval = `tcp_ms()` + offset), mas não o dos buracos.

## 3. Desenho

1. **Mapa de envio** (`t_xmap`, por conexão): anel de N (32-64) registros `{end_seq, xmit_ms, retx}`
   acrescentados em `tcp_output()` a cada segmento de dados (novos: no fim; retransmissões: um registro
   novo com o `end_seq` do trecho retransmitido e `retx`). Registros contíguos no mesmo ms fundem-se; o
   anel cheio funde os dois mais antigos (perde precisão só no passado). Podado quando `snd_una` passa.
   Custo: ~768 bytes por tcpcb (64 × 12).
2. **Estado RACK** (RFC 8985 §6.2): `rack_xmit_ts`, `rack_end_seq`, `rack_rtt`, `min_rtt` (janela de
   10 s, como o HyStart já mantém por rodada), `reo_wnd` = min_rtt/4 (até SRTT), multiplicador após
   D-SACK (§6.2.4, `reo_wnd_mult`, decai a cada 16 recuperações).
3. **No ACK** (`tcp_input`, depois de `tcp_sack_update()`): para os bytes recém-confirmados ou SACKados,
   achar no mapa o registro mais recente por horário (ignorando retransmissões ambíguas: Karn, salvo se o
   TSecr bater com o horário da retransmissão) → atualiza `rack_xmit_ts/end_seq` e `rack_rtt`.
4. **Detecção** (§6.2.5): um buraco do placar (byte não SACKado < `snd_max`) é perdido se seu registro
   tem `xmit_ms + rack_rtt + reo_wnd ≤ now` e foi enviado antes de `rack_xmit_ts`. Resultado: o
   **limite de perda** que hoje vem de `tcp_sack_lostbound()` (DupThresh). Com RACK: perdidos = os
   buracos marcados por tempo (e, durante a 1ª recuperação, ainda DupThresh, como o Linux faz com
   `tcp_recovery & RACK_NO_DUPTHRESH` desligado — decidir pelo bench).
5. **Timer de reordenação** (§6.2.6): se há buraco ainda não perdido mas que será em `t`, armar o
   deadline do REXMT como `TF_RACKT` (como o TLP faz com `TF_PTO`); ao disparar, refazer a detecção e
   entrar em recuperação.
6. **Entrada em recuperação**: hoje por 3 dupacks/DupThresh; com RACK, quando a detecção marca algo
   perdido (inclusive após o TLP: o ACK que SACKa a sonda marca os anteriores).
7. Sysctl `net.inet.tcp.rack` (1), para A/B no mesmo binário.

## 4. Riscos

- O placar tem 32 faixas e descarta a mais alta quando cheio; o mapa precisa casar com isso (buracos
  acima da última faixa conhecida não são avaliados).
- Granularidade de 1 ms (`tcp_ms()`) e o tique de 50 ms do timer rápido: `reo_wnd` de poucos ms é
  avaliado no ACK (preciso), mas o timer de reordenação dispara com até 50 ms de atraso.
- Interação com PRR/`tcp_sack_recover()`: só muda quem é "perdido" (NextSeg regra 1) e SetPipe.

## 5. Testes

- `loss_probe.py` A/B (sysctl): reorder → retransmissões desnecessárias ~0 (meta), random/partial/
  lostrexmit sem piora; `tail_probe.py` com cauda de vários segmentos (novo modo: descartar os 2-3
  últimos) → recuperação ~TLP, sem RTO.
- CUnit: sysctl; mapa de envio via TCP_INFO não é exposto — teste de unidade possível só no wire.
