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
| B31 | Nenhum socket UDP abre no m68k (`udp_recvspace` 266 KB > limite do `sbreserve` ~58 KB) | Kal, `a1ede9f0e6` | Kal | upstream `64d00bf2da` (refatoração em módulos) | `udpdiag` no Amiga emulado (UDP4/UDP6/TCP4/TCP6 abrem); DNS e DHCP no emulador; `cunit-net-udp`/`udpio` no hosted | `cunit-net-tcpinfo` (só hosted); **falta verificar no Amiga emulado** (`udpdiag`) | **fechado** — verificado no Amiga emulado (`tests/stack/udpdiag.c`: UDP4/UDP6 abrem, master `64d00bf2da`); teste do Kal em `cunit-net-tcpinfo` (hosted) |
| B32 | Timers da pilha param de vez (requisição do timer de prazo do TCP usada por duas tasks) | **nosso**, `fa93417c95`/`e0f2b1e9c5` (#2194/#2208) | Kal | upstream `64d00bf2da` (`amiga_time.c` reescrito) | transferências TCP de várias tasks ao mesmo tempo com perdas (netem) por minutos; RTO e sonda de perda continuam disparando (`tests/tcp/loss_probe.py`, `tail_probe.py`) | **sem teste específico — escrever (nós)**: N tasks enviando com perdas, RTO dispara; auditoria `AbortIO`/`WaitIO` da API | no upstream — falta teste |
| B33 | `connect()` IPv6 escolhe par de portas ainda em TIME_WAIT | provavelmente nosso (`2aae838ba6`, `c388bc08e9`) | Kal | upstream `64d00bf2da` | conexões IPv6 seguidas ao mesmo servidor/porta, fechando do lado AROS: nenhum `connect` cai num par em TIME_WAIT (captura: SYN não reaproveita o 4-tupla) | `cunit-net-tcpinfo` (teste do Kal) | no upstream — falta nossa verificação |
| B34 | Tráfego IPv6 nunca filtrado (`pfil` só no IPv4) | anterior ao nosso trabalho | Kal | upstream `64d00bf2da` | regra do firewall bloqueando ICMPv6/UDP6; o tráfego some; IPv4 igual | `cunit-net-filter6` (do Kal) | no upstream — falta nossa verificação; **B5 conflita** (4 arquivos) |
| B27 | `tcp_debug[100]` é memória morta (72 KB no m68k) | anterior; dobrou com o `tcpcb` maior | nós | upstream `64d00bf2da` ("72 KB TCP trace buffer and SYN cache allocated only when used") | `m68k-aros-nm` sem `tcp_debug`; m68k `.bss` ~17 KB | `cunit-net-synalloc` (SYN cache); para o `tcp_debug`: medir no m68k (sem o símbolo no `.bss`) | **fechado** — medido no m68k: `.bss` do núcleo 6.140 B, sem `tcp_debug` |
| B28 | Perfil `INET6=0` não compila | anterior | nós | — | build m68k com `INET6=0` | build `INET6=0` (m68k) junto com o delta de tamanho de cada PR | **perde a razão** — o IPv6 é o módulo `inet6.prot`, escolhido em tempo de execução (`PROTOCOLS=INET`: −97 KB em repouso no m68k); o `#define INET6 0` de compilação não é mais o perfil |
| B30 | Alvo do AROSTCP não depende da `fd.library` (`proto/fd.h`) | anterior | nós | — | build limpo só do alvo `workbench-network-stacks-arostcp` | o mesmo, ao montar build novo | aberto |
| B29 | Hosted x86_64 trava com o perfil de mbuf do m68k | não investigado | nós | — | `tests/stack/memcost.py --profile m68k` (hosted) | o mesmo | aberto (investigar) |
| B5 | Cache de vizinhos IPv6 por (interface, endereço) | anterior | nós | branch `review/arostcp-nd6-ifcache`, `11df4517ea` (local) | `zone_probe.py` 2 NS; `cunit-net-nd6cache`, `pmtu6`; 52 suítes; `defrouter.py`, `remloop.py`; delta m68k +1.420 | `cunit-net-nd6cache`, `pmtu6` (ON_LINK, LINK_LOCAL), `ndqueue6` | corrigido (local) — **PR aguarda autorização do usuário** e o #2218; rebase sobre B32–B34 |
| G11 | IPv4: ACD + IPv4LL pela ACD, DHCPDECLINE, NUD do ARP (**escopo reduzido 2026-11-12**: `IP_RECVIF`/`IP_SENDSRCADDR`, `ip_mreqn` e dicas do TCP saíram — sob demanda, como ganchos da família IPv4, quando o mdnsd/`dnssd.library` precisar de um socket IPv4 único) | — | nós | PR #2218; branch local `review/arostcp-ipv4-acd` (`fe5910c842`, `ba00219d06`, `a505f7a00e`) reimplementada sobre `64d00bf2da` (módulo `inet.prot`; reload/enlace pelos eventos de família; `dad_count` como `netvar`; bind duplicado em `inf_pcbbindaddr`) | 64 suítes ok (2 execuções); `acd_probe`, `dhcp_decline_probe` (+`--claim`), `acd_reprobe_probe` (pronto aos 66,8 s), `arp_stale_probe` (20,9 s); m68k: núcleo igual, `inet.prot` +2.468 B | `cunit-net-acd`, benches `tests/ipv4` | **pronto para force-push — aguarda o usuário** |
| B3 | `tcp_drain()` vazio | anterior | — | — | auditado, não demonstrado | — | aberto (baixa prioridade) |
| H1 | Build paralelo perde headers gerados: `proto/security.h`, `interface/Hidd.h`, `partition_support.h` | AROS (fora da pilha) | — | — | build m68k `-j8` limpo | — | aberto (observação; reproduzir) |
| E1 | `egl.library` falha no m68k e para o build das bibliotecas seguintes | AROS (fora da pilha) | — | — | `make workbench-libs-complete` m68k | — | aberto (observação) |

## Planos ligados (sem item de bug)

- Regra "padrões ligados à máquina" + auditoria dos valores fixos da pilha — `research/2026-11-11-stack-cost-m68k.md`.
- Grupo multicast/SSM — **cancelado pelo usuário (2026-11-12)**; issue #2220 fechada. O plano (`research/2026-11-10-multicast-ssm-design.md`) fica só como referência.
- G12 (mDNS/DNS-SD) — **área do Codex assumida (2026-11-12, decisão do usuário)**; ordem em `aros-midihub/docs/mdns-integration-agreements.md` (`85553db9d5`): (1) mdnsd no modelo canônico; (2) protocolo interno neutro; (3) `dnssd.library` v0 com consulta de endereço; (4) `.local` no `resolver.atcp`; (5) busca/resolução/registro, migração, retirada da `bonami.library`.
  - Passo 1: branch local `review/mdnsd-canonical-links` (5 commits do Codex sobre `64d00bf2da`, sem conflito). Testes do Codex no hosted modular: modelo, inventário e coletor AROSTCP, 0 falhas. Interoperabilidade com Avahi (`tests/mdns/interop.sh`): host resolve `arosbox.local` A+AAAA e navega no serviço da AROS; AROS navega no serviço do host e resolve `palerma.local`. Precodacy: 1 cppcheck (escopo) + `strncpy`/`strlen` nos testes — corrigir antes do PR. m68k (Amiga emulado): testes do modelo/inventário/coletor 0 falhas (com o `startnet` antes; ver B35) e interoperabilidade com Avahi idêntica ao hosted (`MODE=amiga`). Achado do Codex corrigido: `dnssd_link_aros.c` não compilava no m68k com `-Werror` (sign-compare; `fixup!` `56fec7cd49`). Falta: corrigir os achados do precodacy, dobrar o fixup, PR com o aval do usuário (mdnsd é dele).
  - Passos 2–4 (desenho `research/2026-11-12-dnssd-library-design.md`): **feitos e testados (2026-11-12)**, commits locais em `review/mdnsd-canonical-links`: `25781b00d2` (consulta com *sink*: todas as respostas, não só a primeira), `a68700b45c` (porta `"DNSSD"` no mdnsd: sessões/operações com geração e encarnação, fila por sessão com `LOST`, notificação emprestada, consulta A+AAAA com índice de interface), `7c54609b0d` (`dnssd.library` v1: `OpenSessionA`, `CloseSession`, `ReadEvent`, `Cancel`, `LookupAddressA`, `LookupAddressSyncA`, `GetStatusA`). Teste `tests/mdns/dnssd.sh` + `dnssdtest.c` (layout, parâmetros, consulta assíncrona/IPv6 só/inexistente, cancelamento imediato sem eventos depois, fechar com operação ativa, síncrona, contadores do daemon a zero): **20/20 no hosted e no m68k** (Amiga emulado; `DNSSDEvent` 56 B no x86_64, 52 B no m68k, mesmos offsets). Interop Avahi pelo caminho BonAmi sem regressão. m68k: `dnssd.library` 12.884 B; no mdnsd `dnssd_server.o` 2.566 B de texto. Falta: passo 5 (`.local` no `resolver.atcp`, PR do AROSTCP depois do #2218 e do B5), 6–8; AutoDocs geradas pelo build; PR só com o aval do usuário.
  - **Decisões do usuário (2026-11-12):** IPP não migra; motor do mdns livre para redesenho; Bonami é só origem do código; lacuna da pilha se implementa na pilha. Plano R1–R7 no documento de desenho (ordem revista: API completa → migração → retirada da BonAmi → internos).
  - **R1 feito:** pilha `review/arostcp-ip-recvif` (sobre `64d00bf2da`): `05508114ec` `IP_RECVIF`; `a3edf5f169` B36 (adesões órfãs, `cunit-net-mcastgone`); `735beaaf27` B37 (clusters de recepção vazavam na remoção de interface, `tests/stack/ifremove.sh`). mdnsd `9cd6386ae8` um socket por família (hosted/m68k: `dnssdtest` 20/20, interop igual; dois enlaces `TWO=1`: cada enlace com o próprio endereço). PR da pilha: depois do #2218 e do B5 (fila de um PR), bump no último commit, delta m68k a medir.
  - **R5 feito (2026-11-12)**, `6a4166580b`: cache de registros (`mdns_cache.c`, nomes em formato de fio, §10.1/§10.2, perguntas contínuas com respostas conhecidas §5.2/§7.1, renovação 80–95 %, orçamento 24 KB m68k/128 KB) e operações `LookupAddress`/`Browse`/`Resolve`/`QueryRecord` como assinantes; evento v1 completo (instância, tipo, domínio, alvo, porta, prioridade, peso, TXT, RDATA). `dnssdtest` 33/33 no hosted e no m68k (inclui instância `Dot.Test`: escapada em `de_Name`, crua em `de_Instance`); interop e dois enlaces íntegros. m68k: mdnsd 69.876 → 77.148 B (o motor antigo de descoberta, ~100 KB estáticos de RAM, sai no R7), `dnssd.library` 14.132 B.
  - **Próximo:** `DNSSD_RegisterA`/`UpdateA` (passo 7, com o R6: conjunto autoritativo), depois migração de `dnssd`/`handshake`/`nearby`/`share` e `netmidid`, e o R7.
  - #2123 (eventos V2 na `bonami.library`): **fechado (2026-11-12)** com nota apontando para a `dnssd.library`. Branches `review/mdns-tools-v2` e `review/mdns-receive-hoplimit` (#2119 recusado) abandonadas.

## Último commit do upstream visto

`64d00bf2da` (2026-11-12, Kal: núcleo + módulos `inet.prot`/`inet6.prot`/`transport.prot`, `resolver.atcp`/`admin.atcp`/`packet.atcp`/`netconfig.atcp`; serviços do núcleo em `net/netcore.def`). Trouxe B27, B31–B34. **As medições de tamanho/memória (`research/2026-11-11-stack-cost-m68k.md`) são da estrutura anterior: refazer a linha de base sobre ela** (núcleo + módulos carregados).
