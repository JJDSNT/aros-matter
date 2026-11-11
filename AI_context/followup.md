# Acompanhamento — correções, verificação e regressão

Pedido do usuário (2026-11-11): tudo anotado para acompanhar o que foi corrigido ou não, sem regressão e sem
nada deixado de corrigir. Este é o painel; o detalhe de cada bug fica em [bugs.md](bugs.md).

**Regra:** um item só sai daqui (estado **fechado**) quando: (1) a correção está no upstream (commit/PR
anotado); (2) foi verificada por nós no hosted **e**, se o item toca o m68k, no Amiga emulado; (3) existe um
teste que falharia se o defeito voltasse (anotado na coluna "Teste de regressão") e ele roda na nossa suíte.

## Procedimento a cada atualização do upstream

1. `git -C ~/AROS-ipv6 fetch upstream` e
   `git -C ~/AROS-ipv6 log --format='%h %ad %an %s' --date=short <último-visto>..upstream/master -- workbench/network`
   (anotar o último commit visto no fim deste arquivo).
2. Para cada commit: a que item daqui corresponde? Anotar na tabela (coluna "Onde"). Commit sem item: ler e ver
   se precisa de um.
3. Itens marcados como corrigidos pelo upstream: rodar a verificação da linha; se passar e houver teste de
   regressão na suíte, marcar **fechado**; se não houver teste, escrever (estado **falta teste**).
4. Rebasear o que está pendente nosso (B5, #2218) e rodar: 52+ suítes no hosted (`tools/cunit-suite.sh`), os
   benches da linha, e o delta de tamanho no m68k (`tools/stack-size-hist.sh` + `tools/stack-size-report.py`).
5. Ver se algum item aberto não tem dono: escolher (nós ou pedir ao usuário para combinar com o Kal).

## Itens

Estados: **aberto** · **em correção** (alguém trabalhando) · **corrigido (local)** (fora do upstream) ·
**em PR** · **no upstream** (falta nossa verificação) · **falta teste** · **fechado**.

| # | O quê | Origem | Quem corrige | Onde | Verificação | Teste de regressão | Estado |
|---|---|---|---|---|---|---|---|
| B31 | Nenhum socket UDP abre no m68k (`udp_recvspace` 266 KB > limite do `sbreserve` ~58 KB) | Kal, `a1ede9f0e6` | Kal | árvore local do Kal | `udpdiag` no Amiga emulado (UDP4/UDP6/TCP4/TCP6 abrem); DNS e DHCP no emulador; `cunit-net-udp`/`udpio` no hosted | rodar `udpdiag` no emulador em toda medição m68k; CUnit que abre UDP4/UDP6 (roda no m68k quando houver suíte lá) | corrigido (local) — **plano B** se não for ao upstream: `research/2026-11-11-stack-cost-m68k.md`, item 4 |
| B32 | Timers da pilha param de vez (requisição do timer de prazo do TCP usada por duas tasks) | **nosso**, `fa93417c95`/`e0f2b1e9c5` (#2194/#2208) | Kal | árvore local do Kal | transferências TCP de várias tasks ao mesmo tempo com perdas (netem) por minutos; RTO e sonda de perda continuam disparando (`tests/tcp/loss_probe.py`, `tail_probe.py`) | **a escrever (nós):** CUnit com N tasks enviando e perdas, que confere que o RTO dispara depois de muitos ciclos; e **auditoria** de todo `AbortIO`/`WaitIO`/`SendIO` alcançável da API (memória `io-request-one-task`) | corrigido (local) |
| B33 | `connect()` IPv6 escolhe par de portas ainda em TIME_WAIT | provavelmente nosso (`2aae838ba6`, `c388bc08e9`) | Kal | árvore local do Kal | conexões IPv6 seguidas ao mesmo servidor/porta, fechando do lado AROS: nenhum `connect` cai num par em TIME_WAIT (captura: SYN não reaproveita o 4-tupla) | **a escrever se o Kal não incluir:** CUnit IPv6 (e o mesmo para IPv4, conferir) com conexões/fechamentos em laço | corrigido (local) |
| B34 | Tráfego IPv6 nunca filtrado (`pfil` só no IPv4) | anterior ao nosso trabalho | Kal | árvore local do Kal | regra do firewall bloqueando ICMPv6/UDP6; o tráfego some; IPv4 igual | **a escrever se o Kal não incluir:** CUnit com regra de filtro IPv6 | corrigido (local); **atenção ao rebase do B5** (`ip6_output.c`) |
| B27 | `tcp_debug[100]` é memória morta (72 KB no m68k) | anterior; dobrou com o `tcpcb` maior | nós | — | `m68k-aros-nm` sem `tcp_debug`; m68k `.bss` ~17 KB | delta de tamanho m68k em cada PR (o símbolo não pode voltar) | aberto — PR próprio quando for a vez |
| B28 | Perfil `INET6=0` não compila | anterior | nós | — | build m68k com `INET6=0` | build `INET6=0` (m68k) junto com o delta de tamanho de cada PR | aberto |
| B30 | Alvo do AROSTCP não depende da `fd.library` (`proto/fd.h`) | anterior | nós | — | build limpo só do alvo `workbench-network-stacks-arostcp` | o mesmo, ao montar build novo | aberto |
| B29 | Hosted x86_64 trava com o perfil de mbuf do m68k | não investigado | nós | — | `tests/stack/memcost.py --profile m68k` (hosted) | o mesmo | aberto (investigar) |
| B5 | Cache de vizinhos IPv6 por (interface, endereço) | anterior | nós | branch `review/arostcp-nd6-ifcache`, `11df4517ea` (local) | `zone_probe.py` 2 NS; `cunit-net-nd6cache`, `pmtu6`; 52 suítes; `defrouter.py`, `remloop.py`; delta m68k +1.420 | `cunit-net-nd6cache`, `pmtu6` (ON_LINK, LINK_LOCAL), `ndqueue6` | corrigido (local) — **PR aguarda autorização do usuário** e o #2218; rebase sobre B32–B34 |
| G11 | IPv4: ACD, IPv4LL, DECLINE, NUD do ARP, opções | — | nós | PR #2218 (em revisão) | 52 suítes; benches `tests/ipv4` | `cunit-net-acd`, `cmsg` | em PR — rebase sobre B32–B34 quando entrarem |
| B3 | `tcp_drain()` vazio | anterior | — | — | auditado, não demonstrado | — | aberto (baixa prioridade) |
| H1 | Build paralelo perde headers gerados: `proto/security.h`, `interface/Hidd.h`, `partition_support.h` | AROS (fora da pilha) | — | — | build m68k `-j8` limpo | — | aberto (observação; reproduzir) |
| E1 | `egl.library` falha no m68k e para o build das bibliotecas seguintes | AROS (fora da pilha) | — | — | `make workbench-libs-complete` m68k | — | aberto (observação) |

## Planos ligados (sem item de bug)

- Regra "padrões ligados à máquina" + auditoria dos valores fixos da pilha — `research/2026-11-11-stack-cost-m68k.md`.
- Grupo multicast/SSM — issue #2220 (aguardando o Kal).
- G12 (mDNS/DNS-SD) — `research/2026-11-10-g12-mdns-integration.md`.

## Último commit do upstream visto

`e54d391643` (2026-11-11). B31–B34 corrigidos só na árvore local do Kal nesta data.
