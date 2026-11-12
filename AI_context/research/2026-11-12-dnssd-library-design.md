# `dnssd.library` e o mdnsd nativo — desenho e plano até substituir a `bonami.library` (2026-11-12)

Pedido do usuário: assumir a área do Codex e avançar até poder **substituir no upstream** o que existe hoje
(`bonami.library` + IPC `BonAmi` + mdnsd com estruturas Bonami) pela abordagem do ADR
(`aros-midihub` `review/mdns-modernization-plan`: `docs/dnssd-native-architecture-decision.md`). O ADR é a base;
este documento fixa as escolhas concretas que ele deixou abertas e a ordem.

## O que existe e o que é reaproveitado

- **Upstream:** mdnsd (`workbench/network/mdns/`, ~9 mil linhas), `bonami.library` 41.7 (21 funções, uma
  `struct MDNSIPCMsg` fixa de ~1,7 KB para tudo, porta `"BonAmi"`), ferramentas `dnssd`/`handshake`/`nearby`/
  `share`, consumidor `netmidid`; IPP (`workbench/devs/ipp/dnssd.c`) tem cliente mDNS próprio.
- **Do Codex, mantido:** modelo canônico de interfaces/endereços no mdnsd (`proposal/dnssd-canonical-model`,
  validado no hosted e no m68k, interoperabilidade com Avahi); formato de mensagem neutro `dnssd_model` (tamanho
  declarado, sem ponteiros, vários endereços com índice de interface, TXT binário, nomes em formato DNS);
  protótipo do coordenador de sessões (`prototypes/dnssd/coordinator.*`: gerações, cancelamento, limpeza por
  `TNA_REMOVED`).
- **Descartado:** eventos V2 na `bonami.library` (#2123, fechado), validação de hop limit (#2119, recusado).

## API pública v1 (`<dnssd/dnssd.h>`, `<proto/dnssd.h>`)

Escolhas: nomes com prefixo `DNSSD_`; tudo por message port nativa; o cliente nunca vê ponteiro do daemon;
estruturas com tamanho declarado; tags para opções; erros `DNSSD_ERR_*` (negativos), `DNSSD_OK` = 0.

| Função | O quê |
|---|---|
| `DNSSD_OpenSessionA(port, tags)` | sessão da task; `port` recebe as notificações (uma por lote, não por evento) |
| `DNSSD_CloseSession(session)` | cancela todas as operações; síncrono, nada chega depois |
| `DNSSD_LookupAddressA(session, name, tags)` | nome → endereços IPv4/IPv6 com índice de interface (`DNSSD_Family`, `DNSSD_Interface`, `DNSSD_Timeout`) — o que o resolver do sistema precisa (`DNSServiceGetAddrInfo`) |
| `DNSSD_BrowseA(session, type, tags)` | instâncias de um tipo (com subtipo), por enlace |
| `DNSSD_ResolveA(session, name, type, domain, tags)` | SRV + TXT + todos os endereços |
| `DNSSD_RegisterA(session, tags)` / `DNSSD_UpdateA(op, tags)` | publicar/atualizar (TXT binário contado, subtipos, auto-renomear) |
| `DNSSD_QueryRecordA(session, name, rrtype, tags)` | registro genérico (RDATA binário) |
| `DNSSD_Cancel(op)` | idempotente; confirmado; nada chega depois |
| `DNSSD_ReadEvent(session, buffer, size)` | copia o próximo evento; `DNSSD_ERR_TOOSMALL` diz o tamanho; `DNSSD_ERR_EMPTY` quando acabou |
| `DNSSD_LookupAddressSync(name, addrs, max, tags)` | conveniência síncrona (sessão e porta próprias, prazo, cancelável por sinal) — para o resolver e programas simples |
| `DNSSD_BuildTXT` / `DNSSD_ParseTXT` | ajudantes de TXT, sem o daemon |
| `DNSSD_GetStatusA(tags)` | estado do daemon (encarnação, contadores) |

Eventos: o `dnssd_model_message` do Codex vira `struct DNSSDEvent` pública (versão, tamanho, tipo
`ADD/REMOVE/RESOLVED/ADDRESS/RECORD/REGISTERED/RENAMED/ERROR/LOST`, sessão, operação, sequência, índice de
interface, TTL, porta, prioridade/peso, e referências por deslocamento para instância, tipo, domínio, alvo, TXT,
endereços e RDATA dentro do mesmo buffer). O layout é verificado em 32/64 bits e m68k (teste de ABI).

## Protocolo privado (biblioteca ↔ mdnsd)

Porta pública `"DNSSD"` (a `"BonAmi"` some no fim). Cada chamada é uma mensagem com cabeçalho
`{tamanho, versão, comando, resultado, encarnação, sessão, operação}` mais carga de tamanho declarado; o daemon
valida tamanho/versão/comando e responde. O daemon guarda os eventos em fila própria (limitada por operação e
por sessão; estouro → evento `LOST` e ressincronização) e manda **uma** notificação curta para a porta da
sessão quando a fila passa de vazia a não vazia; a biblioteca drena com `READ`. Sessões e operações com geração
e encarnação (coordenador do Codex); morte da task por `TNA_REMOVED` (com o reaproveitamento por ID estável de
reserva).

## Ordem de trabalho (cada passo testado no hosted, no m68k e com o Avahi)

1. **mdnsd: modelo canônico** (5 commits do Codex + correção m68k) — validado; PR com o aval do usuário.
2. **mdnsd: sessões e protocolo neutro** — coordenador no daemon, porta `"DNSSD"`, `OPEN/CLOSE/CANCEL/READ/
   STATUS`; a `"BonAmi"` continua até o passo 8.
3. **`dnssd.library` v1 esqueleto** — sessão, cancelamento, leitura, estado; header, AutoDocs, teste de ABI.
4. **Consulta de endereço** — A+AAAA pelo motor de consultas (`mdns_query.c`), eventos `ADDRESS` com índice
   de interface; `DNSSD_LookupAddressSync`.
5. **Resolver do sistema: `.local`** — no módulo `resolver.atcp` (AROSTCP): abre a `dnssd.library` sob demanda,
   `gethostbyname`/`getaddrinfo`/reverso de 169.254/16 e fe80::/10; sem a biblioteca, nada muda. (PR do AROSTCP,
   depois do #2218 e do B5.)
6. **Busca e resolução** — eventos do cache de descoberta no formato novo (vários endereços, SRV completo).
7. **Registro** — TXT binário, subtipos, nome final/renomeação, retirada (goodbye).
8. **Consulta genérica e estado**; **migração** das ferramentas, do `netmidid` e do IPP; **retirada** da
   `bonami.library`, do header `<bonami/mdns.h>` e da porta `"BonAmi"` do build; mdnsd sem tipos Bonami.

Fora do escopo agora: DNS-SD de área ampla (unicast DNS-SD), sleep proxy. **O IPP não migra** (decisão do usuário,
2026-11-12): continua com o cliente próprio.

## Redesenho do motor (decisão do usuário, 2026-11-12)

"O motor mdns pode ser redesenhado da forma que melhor se encaixa com a arquitetura do SO"; a Bonami é só origem do
código, sem compromisso arquitetural; o que faltar na pilha se implementa na pilha. O que destoa hoje e o alvo:

| Hoje | Alvo |
|---|---|
| um socket IPv4 por interface (`SO_BINDTODEVICE`), porque o IPv4 não dizia a interface de chegada | **R1** um socket por família; interface por `IP_RECVIF` (novo no AROSTCP, branch `review/arostcp-ip-recvif`) e `IPV6_PKTINFO`; adesões aos grupos reconciliadas por enlace sem fechar sockets; envio com enlace e família explícitos |
| contexto global implícito (`md_SendIf`, `md_SendFamily`, `md_Reply*`) salvo/restaurado em volta das chamadas | **R2** contexto do pacote explícito (enlace, família, origem, se a resposta é unicast) passado aos tratadores |
| qualquer mudança de endereço zera tudo (descoberta, consultas, nome, registros) | **R3** estado por enlace: sondagem/anúncio/goodbye só no enlace e na família que mudaram (RFC 6762 §8.3, §10.2), pela diferença do inventário canônico |
| espera fixa de 1 s / 250 ms / 20 ms | **R4** agendador por prazo: dorme até a próxima ação; ocioso não acorda (m68k) |
| cache de descoberta e motor de consultas separados | **R5** um cache de registros (TTL, renovação a 80/85/90/95 %, POOF §10.5), consultas contínuas com recuo exponencial e supressão por respostas conhecidas (§5.2, §7.1); `LookupAddress`/`Browse`/`Resolve`/`QueryRecord` são assinantes do cache |
| registros do host e dos serviços em caminhos distintos | **R6** um conjunto autoritativo (host, serviços, subtipos, TXT binário), conflito e renomeação únicos |
| duas portas (`BonAmi`, `DNSSD`) | **R7** só `DNSSD`; ferramentas e `netmidid` migram; `bonami.library` sai |

Ordem (revista 2026-11-12): **R1** (feito: `IP_RECVIF` e saída das adesões na pilha, um socket por família) → **API
completa sobre o motor atual** (passos 6–8: `Browse`/`Resolve`/`Register`/`QueryRecord` na porta `DNSSD` como
adaptadores) → **migração** das ferramentas e do `netmidid` → **R7** retirada da BonAmi → **R2, R4, R3, R5, R6**
reescrevendo os internos sem cliente antigo a preservar, com a API e os testes (`dnssdtest`, `interop.sh`, dois
enlaces `TWO=1`) como rede de segurança. Evita reescrever duas vezes módulos que a BonAmi ainda usa. Cada passo:
canários, `dnssd.sh`, `interop.sh`, hosted e m68k.

### R5 — cache e consultas contínuas (desenho)

Hoje: `mdns_query.c` repassa registros sem cache, sem TTL, sem supressão por respostas conhecidas; `mdns_discovery.c`
guarda 128 registros × ~800 B estáticos (~100 KB, pesado no m68k) e entrega o evento Bonami (um IPv4, nome de 64 B).
Nenhum dos dois serve `Browse`/`Resolve` com vários endereços. Alvo, `mdns_cache.c`:

- **Registro em cache:** nome e RDATA em formato de fio sem compressão (nomes do RDATA expandidos), tipo, classe,
  enlace (índice), TTL, recebido em; alocado sob orçamento em bytes (padrão menor no m68k), despejo do que expira
  antes; chave (enlace, nome sem caixa, tipo, classe, RDATA).
- **Regras do RFC 6762:** cache-flush (§10.2: os do mesmo nome/tipo/classe no mesmo enlace com mais de 1 s caem
  para TTL 1 s), goodbye (TTL 0 → some em 1 s, §10.1), renovação a 80/85/90/95 % só com interesse ativo (§5.2),
  POOF (§10.5) depois.
- **Pergunta contínua** (nome, tipo, enlace ou todos): primeira em 20–120 ms, depois 1, 2, 4 s… até 60 min; respostas
  conhecidas com mais de metade do TTL vão na pergunta (§7.1); compartilhada por todos os interessados.
- **Assinantes:** cada operação da porta `DNSSD` assina perguntas e recebe "entrou"/"saiu" por registro.
  `LookupAddress` = A+AAAA; `QueryRecord` = qualquer tipo; `Browse` = PTR do tipo (ADD/REMOVE por enlace);
  `Resolve` = SRV+TXT da instância, depois os endereços do alvo, um evento RESOLVED com tudo.
- **Registros próprios:** o que o host publica entra pelo mesmo caminho (reflexão hoje; o conjunto autoritativo
  do R6 depois), marcado como local.
- O `mdns_discovery.c` e o `mdns_query.c` antigos saem com a BonAmi (R7).
