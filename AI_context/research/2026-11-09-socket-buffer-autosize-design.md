# AROSTCP: buffers de socket com ajuste automático (P3)

Status: **implementado** (2026-11-09), branch local `review/arostcp-autobuf` (sobre `review/arostcp-ack-timers`) e
`review/tap-backpressure` (sobre `review/tap-device-bps`). Medição antes: [logs/2026-11-09/buffers/](logs/2026-11-09/buffers/);
depois: [logs/2026-11-09/autobuf/](logs/2026-11-09/autobuf/).

## 1. Medido

- Envio: vazão = `SO_SNDBUF`/RTT sempre que abaixo do teto do hosted (~115 Mbit/s). Com o padrão de
  128 KB: 49,5 Mbit/s a 20 ms, 10,1 a 100 ms; com 400 KB, 115 e 31,5.
- Recepção (depois do #2178, sem perdas no `tap.device`): 44,7 Mbit/s a 20 ms e 10,0 a 100 ms =
  128 KB/RTT, o `SO_RCVBUF` padrão.
- O cwnd não limita (validação de cwnd já no grupo 8).

## 2. O que existe

- Padrões: `tcp_sendspace`/`tcp_recvspace` 128 KB (x86), 16 KB (m68k); `SB_MAX` 512 KB / 64 KB.
- Pool global de mbufs e clusters: `mbconf.maxmem` 4 MB (x86) / 1 MB (m68k), elevado por
  `mb_autosize()` para MTUs grandes, nunca acima de 1/8 da memória livre. Ao esgotar, alocações
  falham (`mbstat.m_drops`) e pacotes se perdem para todas as conexões.
- Nenhum ajuste automático: o buffer é o padrão ou o que a aplicação pede.

## 3. Referência

FreeBSD (`tcp_output()` / `tcp_input()`): buffers com `SB_AUTOSIZE` (tirado quando a aplicação usa
`SO_SNDBUF`/`SO_RCVBUF`). Envio: cresce `sendbuf_inc` (8 KB) quando o buffer está ≥ 7/8 cheio e a
janela permite enviar o que está nele, até `sendbuf_max` (2 MB). Recepção: a cada RTT (medido pelo
timestamp), se chegaram ≥ 7/8 do buffer, cresce até `recvbuf_max` (2 MB). Linux: `tcp_wmem`/`tcp_rmem`
com teto e pressão de memória global (`tcp_mem`): sob pressão, não cresce e encolhe.

## 4. Desenho (como implementado)

1. **Teto por socket:** sysctls `net.inet.tcp.sendbuf_max` / `recvbuf_max` (0 desliga): 1 MB no x86, 48 KB no
   m68k. `SB_MAX` do x86 sobe de 512 KB para 2 MB (o `sb_max` do FreeBSD), pois o teto precisa caber sob ele.
2. **Envio:** como o FreeBSD: buffer ≥ 7/8 cheio, as janelas levariam tudo, a janela do par é maior → +16 KB.
3. **Recepção:** como o `tcp_autorcvbuf()` do FreeBSD: mais de 3/8 do buffer chegou em ordem em meio RTT → dobra.
   A escala de janela pedida no handshake cobre o teto (`tcp_rscale()`).
4. **Aplicação manda:** `SO_SNDBUF`/`SO_RCVBUF` explícitos tiram `SB_AUTOSIZE`; sockets aceitos herdam a marca.
5. **Orçamento global (`tcp_autobuf_grow()`):** o que o ajuste deu a todas as conexões vivas, **contado a 2× (custo no
   pool, premissa do `sb_mbmax`; medido 1,77×)**, fica em até 3/8 do pool (`mbconf.maxmem`); o buffer cresce o que
   sobra se for menos que o pedido; devolvido em `tcp_close()`; nada cresce com metade dos clusters em uso.
   - Lição: o primeiro desenho (só o uso instantâneo < 1/2) **esgotou o pool** com 8 conexões a 100 ms: cresceram com
     os buffers vazios e encheram juntos (leitores lentos). O segundo (orçamento 1/4 em bytes de dados) também: 1,9 MB
     de dados não lidos ocupavam 3,4 MB do pool.

## 4a. O que o trabalho expôs (commits próprios)

- **Remontagem travava para sempre** (bug antigo): com 100 segmentos fora de ordem, `tcp_reass()` recusava até o
  segmento em `rcv_nxt`; o par retransmite com backoff e a conexão nunca anda. Com 128 KB (~90 segmentos) não se
  chegava lá. Agora o segmento em `rcv_nxt` sempre entra e o limite é uma janela de segmentos (mín. 100).
- **Lado passivo sem RTT:** conexão vinda do syncache não tinha amostra até enviar dados (srtt 0, RTO 1 s para
  sempre num receptor). Agora a amostra vem do timestamp do SYN-ACK ecoado no ACK final (como FreeBSD). Atenção: o
  caminho rápido de timestamp já preenche `to` e zera `optp`.
- **`sana_poll()` sem orçamento:** esvaziava a porta SANA antes de rodar o IP; cada resposta repõe o pedido, então uma
  rajada enchia o `ipintrq` (1024) e era descartada lá (~800 segmentos com 8 conexões). Agora `net_poll()` a cada 32
  respostas (como o orçamento do NAPI).
- **tap.device sem contrapressão:** lia todo quadro do host e descartava (órfão) o que não tinha pedido pendente.
  Agora segura o quadro (de um tipo que algum opener lê) e não lê o descritor até chegar um CMD_READ; o resto espera
  na fila do tap do host (qlen 1000), como no anel de uma placa real.
- **Bench:** o netem tinha limite padrão de 1000 pacotes na linha de atraso; várias janelas grandes a 100 ms passavam
  disso. `run_tcp.tc_delay()` agora usa `limit 10000` (e `--rate` opcional).
- **`netstat -m` quebrado no AROS:** "unexpected change to mbstat; check source" (o `mbstat` do AROSTCP tem
  `m_memused`). Frente de ferramentas.

## 4b. Resultados (padrões, antes → depois)

| | 20 ms | 100 ms |
|---|---|---|
| recepção (ack_probe, 60 MB) | 44,8 → 130 Mbit/s, 0 retx | 10,1 → 54,6, 0 retx |
| envio (cwnd_probe, 20 s) | 49,1 → 111 (teto da CPU) | 10,2 → 69,6 (orçamento ~900 KB) |

8 conexões recebendo a 100 ms (mem_probe): pool nunca esgota; agregado igual (~62 Mbit/s, CPU do hosted). As
janelas maiores agora transbordam a fila do tap no host (o gargalo), como em qualquer enlace: as perdas batem com o
contador de descarte da interface (165/161, 251/246).

51 suítes CUnit passam; cunit-net-tcpinfo 17/17 (os dois testes novos falham na base).

## 5. Testes

- Fio: `cwnd_probe --sndbuf 0` (envio) e `ack_probe --delay` (recepção) a 20/100 ms: esperado
  ~115 Mbit/s a 20 ms (teto do hosted) e ~sendbuf_max/RTT a 100 ms; nenhuma perda nova.
- Pressão: N conexões simultâneas recebendo (p. ex. 8): o pool não passa de 3/4 de `maxmem`,
  `m_drops` não cresce.
- CUnit: `SO_SNDBUF` explícito desliga o ajuste (o valor lido não muda); `sysctl` dos tetos.
