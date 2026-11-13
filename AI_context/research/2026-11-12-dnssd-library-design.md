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

## Auditoria: limitações herdadas da BonAmi (2026-11-12, a pedido do usuário)

Gatilho: o registro em nome de outro host saiu na API nova só com IPv4 (`DNSSD_HostAddress`), cópia do
`rs_HostAddr` (`ULONG`) do responder antigo. Diretriz: não transportar limitações da BonAmi para a API nativa.

| # | Onde | Limitação herdada | Correção |
|---|---|---|---|
| A1 | registro para outro host | um endereço, só IPv4; endereço do host anunciado mas **não sondado** nem defendido (RFC 6762 §8.1 pede sondar todos os registros únicos); consulta AAAA do host não respondida; sem conflito do nome do host; atualização não troca endereços | vários endereços IPv4/IPv6 (`struct DNSSDAddress`, tag repetível, zona por `da_Interface` para link-local), A e AAAA, sondagem e desempate do nome do host, conflito → operação termina com `DNSSD_ERR_CONFLICT`, `DNSSD_UpdateA` troca o conjunto (goodbye dos que saem) |
| A2 | TXT do registro | buffers de 512 B no anúncio, na sondagem e no conflito: um TXT de mais de 512 B saía **vazio** (erro meu ao ligar o TXT binário) | TXT alocado do tamanho certo, sem cópia em buffer fixo; limite do RFC 6763 §6.2 (recomenda ≤ 1300, permite até 8900) |
| A3 | cache novo (`mdns_cache.c`) | RDATA ≤ 512 B (o `MDNS_RECORD_DATA_MAX` da BonAmi): TXT maior era descartado e o `Resolve` falhava | RDATA até o tamanho do pacote, buffer de trabalho estático (pilha do m68k) |
| A4 | `Resolve` | TXT ≤ 1024 B no evento | alocado do tamanho do registro |
| A5 | limites de texto do responder | `MDNS_MAX_DOMAIN` 16, `MDNS_MAX_SUBTYPES` 8, `MDNS_MAX_TYPE` 32 vêm do IPC BonAmi | o domínio do mDNS é `local` (RFC 6762): a API recusa outro com erro claro; subtipos e tipo revistos no R6 |
| A6 | motor de descoberta/consulta antigo, porta `BonAmi` | eventos de um IPv4, nome de 64 B | saem no R7 (já previsto) |
| A7 | `md_HostAddr` | "o endereço do host" IPv4 único | só semente aleatória; sai |

Ordem: A1–A4 agora (antes da migração das ferramentas), com testes hosted e m68k nas duas famílias; A5 junto; A6/A7 no R7.

**Feito (2026-11-12, `77276cbd38`):** A1 (proxy com até 8 endereços IPv4/IPv6, link-local com zona, sondagem e
desempate do nome do host, `DNSSD_ERR_CONFLICT`, troca de endereços com goodbye), A2 (TXT alocado, até 8900 B;
serviço maior que um MTU vai em pacote próprio, RFC 6762 §17), A3 (`mdnsParseRecord()` não rejeita mais RDATA
> 512 B — antes descartava o pacote inteiro; cache até o tamanho do pacote), A4, A5 (só `local`). Achado junto: o
goodbye de registro próprio nunca saía do cache. `dnssdtest` 63/63 hosted e m68k; o host (Avahi) resolve
`proxyhost.local` em IPv4 e IPv6, vê o endereço trocado e o TXT de 2000 B.

## Realinhamento ao desenho do Codex (2026-11-12, pedido do usuário)

O usuário tinha pedido para achar o trabalho do Codex antes de continuar. Eu tinha lido só a ADR e construí sobre o
responder legado. O desenho do Codex (aros-midihub `review/mdns-modernization-plan`: roteiro D0–D9, auditoria de
reaproveitamento, auditoria do núcleo, inventário de proveniência; protótipo do coordenador `prototypes/dnssd/`,
`ports/aros/dnssd_coordinator_probe.c`, validado no hosted com `TNA_REMOVED`) passa a mandar. Triagem do que fiz:

| Peça minha | Desenho do Codex | Decisão |
|---|---|---|
| `IP_RECVIF`, B36, B37 (AROSTCP) e um socket por família (R1) | regra da lacuna genérica: corrige-se no AROSTCP, o mdnsd consome depois | **fica** |
| 5 commits do Codex (modelo, inventário, coletor, rescan, multi-endereço) | D2 | **fica** (é dele) |
| `mdns_cache.c` ao lado do `mdns_discovery.c` | "sem segundo cache"; reaproveitar os algoritmos do cache existente, redesenhar o modelo guardado | **revisar**: um cache só; trazer do `mdns_discovery.c` o que ele faz melhor (endereços pendentes antes do SRV, renovação, perda) e retirar o outro |
| `dnssd_ipc.h`: uma `DNSSDIPCMsg` fixa que cresce a cada função (`dm_Host`, `dm_Extra`, ...) | "envelope com tamanho + carga tipada por comando"; é a crítica que ele faz à `MDNSIPCMsg` | **refazer**: cabeçalho com tamanho/versão/comando/IDs e carga tipada, validada contra o tamanho recebido |
| sessões em `dnssd_server.c` com reaproveitamento por `FindTaskByPID()` | D1/D7: coordenador validado, `TNA_REMOVED`, reaproveitamento só como recuperação | **refazer** sobre o coordenador dele |
| `DNSSDEvent`/`EventParts` próprios | `dnssd_model` (retrato canônico do serviço, spans contados, conjunto de endereços, codificador validado) | **refazer**: o evento é a projeção do `dnssd_model`; um formato só |
| `MDNSRegisteredService` estendido (texto, `MDNS_MAX_*`, `rs_TaskID`) | D2/D4: objeto de registro canônico (nomes contados, TXT de fio, conjunto de endereços, ID do daemon, dono = sessão); estados pendente/estabelecido/conflito/atualizado/removido | **refazer**, reaproveitando os algoritmos de `mdns_reg.c`/`mdns_host.c` |
| `mdnsd.h` incluindo `<bonami/mdns.h>`/`mdns_ipc.h` | nenhum tipo Bonami no núcleo | sai com o objeto canônico; a porta BonAmi sai no D8 |
| `dnssd.library` (chamadas, tags) e `dnssdtest`/interop/dois enlaces | D3/D4/D5 | chamadas **ficam**; o evento muda; os testes viram critério de aceitação |
| D2 aberto no Codex: RRset maior que um pacote; retrato de serviço só-leitura | — | entra no D2 realinhado |

Ordem: (1) evento = `dnssd_model`; (2) envelope tipado; (3) coordenador com `TNA_REMOVED`; (4) objeto de registro
canônico e responder sobre ele, `mdnsd.h` sem Bonami; (5) um cache só; depois D8 (ferramentas, `netmidid`, retirada).

### Inventário completo do trabalho do Codex (varredura de 2026-11-12)

- **AROS `proposal/dnssd-canonical-model`** (`e812bd5be9`, `86a8e7cdc9`, `0b64c38bb0`, `bb6b138b31`, `d18246e864`):
  `dnssd_model.*` (retrato canônico), `dnssd_link.*` (inventário), `dnssd_link_aros.*` (coletor), rescan, publicação
  de vários endereços; testes em `developer/debug/test/dnssd/`. Já na minha branch.
- **aros-midihub `review/mdns-modernization-plan`:** ADR, roteiro D0–D9, auditorias, inventário de proveniência,
  `docs/dnssd-native-validation-2026-11-09.md`; **coordenador D1** `prototypes/dnssd/coordinator.{c,h}`,
  `tests/dnssd_coordinator.c`, `ports/aros/dnssd_coordinator_probe.c`, `tools/dnssd-coordinator-hosted.sh` (16
  verificações no hosted, `TNA_REMOVED`); **fixtures do responder e do cache** `tests/review/mdns_responder_rfc.c`,
  `mdns_query.c`, `mdns_discovery.c`, `mdns_wire_contract.c`, `mdns_text_capacity.c` com
  `tools/review-mdns-responder.py`, `review-mdns-*-hosted.sh`, `dnssd-canary-hosted.sh`.
- **Superados (era Bonami V2, antes da ADR):** `recovery/*`, `archive/mdns-v2-wip-20261108`, `design/mdns-discovery-api`,
  `g0/mdns-reconcile`, AROS `review/mdns-discovery-v2` (#2123), `review/mdns-tools-v2`. Não servem de base.
- Worktrees `~/AROS-*-codex`: limpas, sem trabalho não commitado.

Uso: o coordenador entra no lugar das minhas sessões; o `dnssd_model` no lugar do meu evento; as fixtures do responder
e do cache passam a rodar junto com `dnssdtest`/interop como critério de aceitação.

### Progresso do realinhamento

- **Passo 0 (linha de base):** fixtures do Codex em `tests/mdns/review/` + `tools/review-mdns-responder.py`: 44/45/16
  na árvore atual (igual à ponta do Codex). Única mudança: ponto no rótulo da instância é aceito (era regra legada).
- **Passo 1 feito (`33c35348d7`):** todo evento é a mensagem do `dnssd_model` (versão 2: `ADDRESS`, `RECORD`,
  `REGISTERED`, `END`, `LOST`; validação do que cada tipo carrega); `struct DNSSDEvent` = layout do modelo (116 B,
  igual em x86_64 e m68k, sem ponteiro); nomes em formato de fio + `DNSSD_NameToText()`; `DNSSD_UserData` saiu,
  `DNSSD_OperationID()` entrou; enumeração de tipos dá `TYPE`. `dnssd_model_test` (ASan/UBSan) ok; `dnssdtest`
  68/68 hosted e m68k; fixtures 44/45/16; interop íntegra.
- **Passo 2 feito (`ec347cac90`, 2026-11-13):** requisição = um bloco alocado pela biblioteca por chamada:
  cabeçalho de largura fixa (`struct dnssd_ipc_request`, 132 B iguais em x86_64 e m68k) + dados referenciados por
  deslocamento/tamanho, como os eventos; nenhum ponteiro do chamador (só a notificação da sessão é emprestada,
  `dnssd_ipc_port.h`). O mdnsd valida tudo antes de ler (`dnssd_ipc_validate()`: versão, comando, o que o comando
  exige/proíbe, referências dentro, alinhadas e sem sobreposição, nomes de fio, rótulos, TXT, endereços). READ: a
  sala de resposta nunca é maior que o buffer do chamador; evento que não cabe fica no mdnsd. Codec em C puro
  (`dnssd_ipc.c`) na biblioteca, no mdnsd e no `dnssd_ipc_test` (todo comando; cada malformação; cada byte de um
  REGISTER alterado: 1.277 aceitos / 899 recusados, leitura só dentro do bloco sob ASan/UBSan). Aceitação: host
  ASan ok; AROS hosted e m68k `dnssdipctest`/`dnssdmodeltest` 0 falhas; `dnssdtest` 68/68 hosted e m68k; interop
  TWO=1 íntegra; fixtures 44/45/16.
- **Passo 3 feito (`5241d57093`, 2026-11-13; linha mDNS rebaseada sobre o #2218 `283464c0b6`, que está sobre o master
  `834490510e`):** gancho `TNA_REMOVED` do `task.resource` (mecanismo do coordenador D1): no contexto de quem remove, sem
  esperar outra tarefa — sob `Forbid()` marca as sessões da tarefa como idas e tira a notificação; sinaliza o mdnsd, que
  as fecha na própria tarefa (operações acabam, serviços saem com goodbye). Notificação só sob `Forbid()` e nunca a sessão
  ida (fechou a corrida verificar/`ReplyMsg`); reap por ID fica como recuperação. `tests/mdns/dnssd_gone.sh`: tarefa
  filha com sessão + registro + browse, removida à força e saindo sem fechar: some em < 20 ms (passo 2, só reap: 380 e
  3.020 ms); Avahi viu o serviço vir e ir as duas vezes (goodbye). **m68k:** a ROM tem `task.resource` e o gancho funciona
  (some em < 20 ms também no A3000 emulado). Regressões na base nova: `dnssdtest` 68/68 hosted e m68k, interop TWO=1,
  saída IPv4 (route/ll/alias) ok, fixtures 44/45/16.
- **Passo 4 feito (`94f6117b70`, 2026-11-13):** registro = `struct dnssd_reg` (`dnssd_reg.h/.c`, C puro): rótulo da
  instância contado (UTF-8, ponto permitido), tipo e domínio em formato de fio, subtipos como rótulos, host substituído
  com endereços IPv4/IPv6, porta, enlace; validado uma vez na criação (tipo `_x._tcp|_udp`, subtipos únicos e não
  vazios, `fe80::` exige enlace, todo nome ≤ 255); renomeação "Nome (n)" cortada em início de caractere. O
  `mdns_reg.c` mantém os algoritmos (sondagem, desempate §8.2, anúncio, respostas atrasadas, conhecidas, legado, tipos,
  subtipos, proxy) com nomes de fio prontos (`rs_Name`, `rs_TypeName`, `rs_HostName`) comparados ao `qwire`/`wire` do
  que chega: nenhum texto no meio. `mdnsd.h` sem Bonami: códigos `MDNSD_OK`/`MDNSD_ERR_*` (mesmos valores),
  `MDNSD_HOST_MAX`, `MDNSD_TTL_MAX`; a porta BonAmi (mensagens, motores de descoberta/consulta) em `mdns_bonami.h`;
  registros BonAmi viram canônicos em `mdns_client.c` (mantém a regra LDH de subtipo dela); `dnssd_server.c` monta o
  registro direto dos rótulos da requisição. API do núcleo: `mdnsRegAddCanonical`, `UpdateRef` (endereços de fio,
  TTL), `RemoveRef`, `RemoveOwner`, `Find`. Pelo `dnssd.library`, subtipo passa a aceitar qualquer rótulo não vazio
  (RFC 6763 §7.1; antes a regra LDH da BonAmi). Aceitação: `dnssd_reg_test` (host ASan/UBSan, AROS hosted e m68k) 0
  falhas; fixtures 44/45/16 (shim `MDNS_CANONICAL_REG`: a fixture registra pela porta BonAmi como a biblioteca);
  `dnssdtest` 68/68 hosted e m68k (pegou um bug meu: a checagem de endereços do `UpdateRef` apontava para a struct que
  `dnssd_reg_init()` zera); `dnssd_gone` 8/8 ×2 hosted e m68k com goodbye no Avahi; interop TWO=1 hosted e interop
  m68k; saída IPv4 route/ll/alias ok. **m68k:** mdnsd texto +156 B, bss +4.352 B (`qwire[256]` das 16 perguntas e
  `wire[256]` do registro analisado; o `qname` em texto sai quando ninguém mais o usar, passo 5), cada registro ~1,2 KB
  a mais no heap (estimativa pelo layout: nomes de fio prontos).
- **Próximo:** passo 5 (um cache só: `mdns_cache.c`, trazendo do `mdns_discovery.c` o que ele faz melhor).

### Entrega (decisão do usuário, 2026-11-12)

Um PR maior que troca o código antigo pelo novo de uma vez ("capotar do código antigo para o novo"), em vez dos PRs
por fatia do roteiro do Codex: núcleo nativo do mdnsd + `dnssd.library` + ferramentas e `netmidid` migrados + retirada da
`bonami.library`, da porta `BonAmi` e dos headers `<bonami/*>`; alguns commits lógicos dentro dele; aval do usuário antes
de abrir (mdnsd é dele). Dependência: o PR do AROSTCP com `IP_RECVIF`, B36 e B37 (`review/arostcp-ip-recvif`) entra
antes, na fila de um PR do AROSTCP por vez (depois do #2218).

### Resolvido: saída IPv4 com um socket só (alerta do usuário, 2026-11-13)

**Resolvido (2026-11-13):** reproduzido no fio (`tests/mdns/ipv4_out.py`: route falha, ll perdido, alias ok); `IP_PKTINFO` implementado no AROSTCP (#2218, `67f7666bfd`) e consumido pelo mdnsd (envio e recepção); os três casos passam. Texto original abaixo.

`IP_RECVIF` diz por onde a pergunta **entrou**; não garante por onde a resposta **sai** nem de que endereço. Hoje:
- multicast: `IP_MULTICAST_IF` (endereço do enlace) antes de cada envio → interface certa; origem = um endereço pronto
  da interface (`in_srcia`/`in_readyia`), que pode não ser o anunciado se a interface tem vários;
- **unicast** (QU, resolvedor "legacy"): interface e origem pela **rota** do destino → errado com a mesma sub-rede em dois
  enlaces e com IPv4LL em dois enlaces (169.254/16 roteada uma vez, RFC 3927 §3.2).
O teste de dois enlaces (`TWO=1`) usa sub-redes distintas e não cobre isso. Antes de escolher o mecanismo (por
datagrama: interface de saída e origem — `IP_SENDSRCADDR` do FreeBSD só dá a origem; `IP_PKTINFO` do NetBSD/Linux/macOS
dá interface e origem e é o par do `IPV6_PKTINFO`; o número 25 do NetBSD colide com `IP_ADD_SOURCE_MEMBERSHIP` no AROS),
reproduzir os três casos: mesma sub-rede em dois enlaces; IPv4LL nos dois; interface com dois endereços (origem do
multicast). Até lá o `IP_RECVIF` não é apresentado como suficiente.
