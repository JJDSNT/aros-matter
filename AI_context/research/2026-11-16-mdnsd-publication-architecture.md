# mdnsd: arquitetura de publicação (B60, B62, B75, B76)

2026-11-16. Pedido do usuário: investigar um redesenho da máquina de estados de publicação do mdnsd,
sem preservar o desenho herdado por compatibilidade interna; comparar ao menos duas alternativas;
apresentar arquitetura, invariantes, transições, riscos, custo e migração **antes** de implementar.
Base: ramo `review/mdnsd-record-lifecycle` (sobre o #2304, `aee82e6af8`), com a diferença de inventário
já feita (`c58cce7bf5`, local).

## 1. O que existe hoje

| Peça | Onde | Forma |
|---|---|---|
| Estado do nome do host | `md_HostState/Step/NextTick/Announced`, `md_HostMulticast` | **um** para todos os enlaces e famílias |
| Estado de cada serviço | `rs_State/Step/NextTick`, `rs_Multicast` | **um** para todos os enlaces e famílias |
| Limite de 1 s por enlace (§6) e PTR de tipo | `rs_MulticastTick[32]`, `rs_TypeTick[32]` | por **slot** de enlace, 256 B fixos por serviço, mesmo com 1 enlace |
| Enlaces | `md_Ifs[32]` (só o índice), reconstruídos a cada rescan | slots podem mudar de ordem |
| Mudança de endereço | `mdnsNetRescan()` → `mdnsHostRestart()` + `mdnsRegRestartAll()` | reinício **global**: sonda e anuncia tudo em todo enlace |
| Respostas | host/serviço só responde se o estado **global** é ANNOUNCED | sondar em um enlace cala todos (B76: 0,8-0,9 s) |

Tamanhos: `mdns_host.c` 531 linhas, `mdns_reg.c` 1704. Um serviço ocupa ~1,6 KB (nomes em wire, `dnssd_reg`, os dois arrays de 32).

## 2. O que a RFC 6762 pede (o que decide o desenho)

- **§8 / §8.3:** ao iniciar ou quando a conectividade muda, **MUST** sondar e anunciar.
- **§8.4 Updating:** dados de um registro mudaram → **MUST** reanunciar; **não** precisa sondar (o nome já é seu).
  Registros **compartilhados** (PTR): **MUST** goodbye do dado velho antes do novo. **Únicos** (A, AAAA, SRV, TXT):
  goodbye **SHOULD [be omitted]** - o cache-flush do anúncio novo limpa.
- **§9:** conflito → o registro volta a sondar; o perdedor **MUST** deixar o nome; escolhe outro.
- **§8.2:** empate na sondagem → o perdedor espera 1 s e sonda de novo.
- **§6:** um registro não vai ao grupo **numa interface** mais de uma vez por segundo (exceto respostas a sondas);
  **§6.2:** os endereços de uma resposta **MUST** ser válidos na interface por onde ela sai.
- **§10.1:** goodbye (TTL 0) quando um registro vai deixar de valer; **§10.2:** cache-flush invalida o resto do RRset > 1 s.
- **§14:** defender o nome em todas as interfaces; **conflito em qualquer interface → nome novo** (global);
  as interfaces podem ser geridas independentemente; em pontes, os próprios anúncios voltam por outra interface.
- **RFC 5227** (com o B62): endereço IPv4 só é usado/anunciado depois da ACD.

Consequência: a unidade natural de **publicação** é o par (nome, enlace); a de **posse do nome** é o nome
(um conflito em qualquer enlace muda o nome em todos).

## 3. Alternativas

### A. Evoluir o estado global com máscaras por (enlace, família)
Cada dono (host, serviço) mantém o estado único e ganha máscaras "enlaces/famílias desta rodada".
- Prós: menos código mudado; reaproveita `mdnsHostTick/mdnsRegTick`.
- Contras: **um** passo/tempo para todos os enlaces - uma mudança no enlace B reinicia a rodada em andamento no A;
  respostas precisam de exceções por máscara; os arrays de 32 slots ficam (256 B/serviço); máscaras indexadas por
  slot precisam ser remapeadas a cada rescan; a lógica "quem responde onde" fica espalhada. O B76 vira regra de
  exceção, não propriedade do modelo.

### B. Publicações por (dono, enlace) com um coordenador de mudanças  ← recomendada
Separar o **nome** (posse, global) da **publicação** (estado, por enlace):

```
Owner (o nome e seus registros)              Pub (o nome num enlace)
  host:    nome do host, A/AAAA                state  PROBING | ANNOUNCING | ANNOUNCED | DEFERRED
  service: instância (SRV, TXT, PTRs),         step   sondas/anúncios enviados nesta rodada
           e o host do proxy (A/AAAA)          fams   famílias já alcançadas (IPv4, IPv6)
  pubs: lista de Pub, uma por enlace ativo     round  famílias desta rodada
                                               next   mdnsTicks() do próximo passo
                                               last4, last6  último multicast (§6) por família
                                               link   índice da interface (identidade estável)
```
**Coordenador** (`mdns_pub.c`): recebe as mudanças do inventário (`dnssd_link_inventory_reconcile_changes()`) e
os eventos de nome, e só ele cria/destrói/reinicia `Pub`s. Envios, respostas e conflitos olham **a Pub do enlace**.

## 4. Arquitetura B em detalhe

### 4.1 Invariantes
1. Existe `Pub(dono, L)` ⇔ o dono publica em L (escopo do dono inclui L) e L tem ao menos uma família utilizável.
2. `Pub.fams ⊆` famílias utilizáveis em L; nada sai por (L, f) com f ∉ `fams ∪ round`.
3. O dono responde perguntas em L ⇔ `Pub(dono, L).state ∈ {ANNOUNCING, ANNOUNCED}` - outros enlaces não importam.
4. Os registros enviados em L só levam endereços válidos em L (§6.2, §14).
5. Um nome por dono, o mesmo em todas as Pubs; mudar o nome reinicia **todas** as Pubs do dono (posse é global).
6. Cada registro multicast em (L, f) respeita 1 s desde o último (`last4/last6`), exceto respostas a sondas.
7. Cada Pub tem **um** tempo `next`; o laço acorda no menor de todos (o modelo do B69-B71 continua).
8. Qualquer inconsistência (overflow da diferença) → todas as Pubs voltam a PROBING (rede de segurança = hoje).

### 4.2 Transições por Pub
| De | Evento | Para | Sai na rede |
|---|---|---|---|
| (nova) | enlace/família veio; dono registrado | PROBING (`round` = famílias do enlace) | 3 sondas, 250 ms (14 ticks) |
| PROBING | 3ª sonda + 250 ms sem conflito | ANNOUNCING | anúncio 1 (cache-flush) |
| ANNOUNCING | 1 s (51 ticks) | ANNOUNCED | anúncio 2 |
| PROBING | empate perdido (§8.2) | DEFERRED (1 s) → PROBING | - |
| ANNOUNCED | **família veio** em L (FAMILY_UP) | ANNOUNCED, `round` = {f}: sondas e anúncios só em f; continua respondendo | 3 sondas + 2 anúncios em f |
| ANNOUNCED | **endereço mudou** em L (ADDRESS_*) - só o dono host/proxy | ANNOUNCED, 2 anúncios de atualização (§8.4) | 2 anúncios cache-flush, sem sonda |
| qualquer | **família sumiu** (FAMILY_DOWN) | `fams -= f`; goodbye dos A/AAAA de f **pela outra família**, se houver (B75) | goodbye |
| qualquer | enlace sumiu | Pub destruída | - (não há por onde) |
| qualquer | **nome do dono mudou** (rename B42, conflito §9) | todas as Pubs → PROBING com o nome novo; goodbye do nome velho onde estava ANNOUNCED (rename voluntário; **não** no conflito, B68) | goodbye + sondas |
| ANNOUNCED | TXT/porta do serviço mudou | 2 anúncios de atualização (§8.4) | SRV/TXT cache-flush |
| ANNOUNCED | serviço retirado | Pub destruída | goodbye de PTR (MUST), SRV, TXT |

Serviços **não** reagem a ADDRESS_* do host (o SRV aponta o **nome**); reagem a FAMILY_UP (precisam ser sondados na
família nova) e aos próprios eventos. Um serviço não anuncia em L antes de `Pub(host, L)` estar ANNOUNCED
(hoje: antes do host global) - o anúncio do serviço segue o do host **no mesmo enlace**.

### 4.3 Como cada B se apoia nisso
- **B76:** invariantes 1, 3, 7 - um enlace que não mudou não sonda nem para de responder.
- **B75:** ADDRESS_REMOVED → atualização imediata com cache-flush (limpa em ~1 s; §8.4 dispensa goodbye para únicos);
  FAMILY_DOWN → goodbye pela família que resta.
- **B62:** FAMILY_UP(L, IPv4) quando o IPv4 fica pronto: sonda e anuncia **só** em IPv4 naquele enlace; o IPv6 segue
  respondendo (hoje: ressonda tudo).
- **B60 (fora desta mudança):** reconhecer os próprios pacotes ouvidos por outra interface é do **transporte**, não do
  estado: um diário dos pacotes enviados (a base experimental de `4bb7fcfd3e`) consultado antes de tratar sondas e
  registros como conflito. Com Pubs por enlace, o B60 também ganha: uma sonda própria do enlace A ouvida no B
  compara com a `Pub(dono, B)` (mesmo nome) - sem o diário seria empate consigo mesmo; com ele, ignorada.
  Fica como etapa própria, com o teste de conflito verdadeiro (`foreignaddr.sh`).

## 5. Custo estimado (m68k) - estimativa inicial; os números medidos estão em §9.4

| Item | Hoje | B |
|---|---|---|
| Estado por serviço | ~1,6 KB, dos quais 256 B de arrays por slot | ~1,35 KB + 24 B por enlace ativo (1-3 em geral) |
| Estado do host | ~20 B globais | 24 B por enlace |
| Código | `mdns_host.c` + parte de `mdns_reg.c` | coordenador novo (~400-600 linhas C), host/reg reescritos nos caminhos de envio, resposta e conflito; a diferença de inventário (+1000 B, a enxugar) |
| Tempo de CPU | reinício global por mudança | só o que mudou; sem acordar a mais (invariante 7) |

Com 50 serviços e 2 enlaces: hoje ~12,8 KB de arrays de slot; B: ~2,4 KB de Pubs. O código deve crescer alguns KB;
o número exato sai das medições de cada etapa.

## 6. Riscos
- **Tamanho da mudança:** reescreve os caminhos de publicação de `mdns_host.c` e boa parte de `mdns_reg.c`
  (respostas atrasadas, subtipos, enumeração de tipos, proxies). Mitigação: etapas com testes de regressão a cada uma.
- **Regras de resposta** espalhadas hoje (`rs_AnswerIf`, `md_TypesAnswerIf`, famílias pendentes): passam a usar a Pub
  do enlace; o maior risco de regressão está aqui (dnssdtest, tools, follow, interop cobrem).
- **Proxy:** dois nomes únicos por dono; a sonda cobre os dois (como hoje).
- **Conflito em pontes / mesmo segmento** (B60) continua até a etapa própria; o desenho não piora (a sonda própria
  vista no outro enlace já é um falso conflito hoje).

## 7. Migração (cada etapa: um commit que compila e passa a regressão)
0. Diferença de inventário (feito, `c58cce7bf5`).
1. **Pubs do host** + coordenador: `Pub(host, L)`; o host deixa o estado global; serviços ainda globais, mas
   respeitam "host ANNOUNCED no enlace". Resolve B76 para o nome do host, B75, B62 (rodada só na família nova).
2. **Pubs dos serviços:** troca `rs_State/Step/...` e os arrays de 32 por Pubs; respostas e anúncios por enlace.
   Resolve B76 para os serviços.
3. Limpeza: some o caminho de reinício global (fica só o fallback de overflow); enxugar a diferença de inventário.
4. (Depois) **B60**: diário de pacotes enviados no transporte.

## 8. Testes
- Existentes, a cada etapa: dnssdtest, tools, netmidid, follow, dnssd_gone, hostname, resolver, timing, clockstep,
  ipv4only, addrchange, addrreplace, interop; m68k: os mesmos + resolver-stack.
- Novos: `availability.sh` (nenhuma lacuna no enlace intocado), serviços registrados durante mudanças de endereço
  (nenhum PTR/SRV/TXT nem sonda de serviço quando só o endereço do host muda; sondas de serviço só na família nova),
  conflito verdadeiro com o Avahi (rename global, §14), empate de sonda (§8.2, só o enlace), família que some
  (goodbye pela outra), testes unitários do coordenador (lógica pura de transições, sem rede).
- Medidas: texto/dados/bss do mdnsd por etapa; pico de pilha; memória com 50 serviços em 2 enlaces.

## 9. Etapa 1 implementada (2026-11-16, local, sem push)

Ramo `review/mdnsd-record-lifecycle` em `~/AROS-ipv6`:
- `5f58ff74f0` dnssd_link: FAMILY_DOWN vem seguido de um ADDRESS_REMOVED por endereço que a família tinha (para
  poder retirar os registros); `dnssd_link_aros_reconcile()` recebe a lista (NULL = nenhuma). Compila sozinho.
- `1ff96c058e` mdnsd: publicações do host por enlace e família + coordenador.

### 9.1 O modelo como ficou
- `struct MDNSPub { p_Link; p_Family[2] }`, `struct MDNSFamilyPub { state, step, updates, next, multicast }` (12 B):
  **dois sub-estados por família** em cada enlace (OFF, PROBING, ANNOUNCING, ANNOUNCED). Identidade do enlace =
  índice da interface (não o slot). `mdns_pub.c`: só a mecânica (achar/criar/remover Pub, iniciar rodada, "responde?").
- O host: `md_HostPubs[32]` substitui `md_HostState/Step/NextTick/Announced/Multicast`.
- Coordenador: `mdnsHostLinksChanged()` consome a lista do inventário:
  FAMILY_UP → só (L, f) sonda e anuncia; ADDRESS_ADDED/REMOVED com a família presente → `fp_Updates = 2`
  (dois anúncios cache-flush, §8.4, sem sonda) nas famílias que respondem em L; FAMILY_DOWN → (L, f) OFF e goodbye
  dos endereços perdidos **pela outra família** se ela responde em L; enlace sumido → Pub removida;
  overflow → todo enlace volta a sondar (rede de segurança).
- Nome (rename B42, conflito §9): todas as Pubs recomeçam (posse global, §14); goodbye do nome velho só no rename
  voluntário (B68). Os serviços são reanunciados com o nome novo quando o host está pronto em toda Pub.
- Respostas: o host responde em (L, f) só se (L, f) responde; a resposta multicast sai **pela família da pergunta**;
  o "unicast direto" (§5.4) usa o último multicast de (L, f). Serviços do host só respondem onde o host responde.
- Serviços continuam globais (etapa 2), mas: endereço do host mudou → **nada** para eles (o SRV aponta o nome; os
  A/AAAA adicionais vêm do host); só FAMILY_UP/overflow ainda reinicia os serviços (globalmente, até a etapa 2).
- **Proxy:** a etapa 1 não toca o ciclo do proxy (os registros dele são do serviço); mudanças do host local não o
  afetam - a invariante vale por construção e será explícita nas Pubs de serviço (etapa 2).

### 9.2 Limites do B75 (documentados, não "resolvidos pelo cache-flush")
- Endereço removido com a família ainda presente: o reanúncio cache-flush do conjunto restante retira o velho em
  ~1 s (§10.2) para quem ouve aquela família - correto pelo §8.4.
- **Última família removida** no enlace: nada mais sai por ela. O goodbye vai pela família que resta
  (`addrreplace`: TTL 0 de 192.168.166.2 com origem fe80::…); um cliente **só IPv4** não o recebe e guarda o
  registro até expirar (TTL do host, 120 s). Sem transporte nenhum (enlace caiu), nenhum goodbye é possível.
- "Retirar antes de perder o transporte": não há aviso prévio da pilha (o endereço já some/fica tentativo quando
  o sinal chega); ficaria para um sinal "vai remover" da pilha - fora do escopo.

### 9.3 Resultados (hosted, imagem `aros-build-ipv6-hosted-claude`)
- `availability.sh` (B76): eth1 **sem nenhuma lacuna** de resposta e 0 sondas em ambos os enlaces enquanto o alias
  vem e vai no eth0 (antes: 4 lacunas de 0,8-0,9 s e 18 sondas no eth1); eth0: 2 anúncios por família com o alias e 2
  sem ele, sem sonda.
- `ipv4only`: IPv6 anunciado a 1,1 s durante a ACD; IPv4 sonda só quando pronto (5,4 s) e o ouvinte só-IPv4 ouve.
- `addrchange`: mesmo IPv4 reaplicado → 3 sondas (só IPv4; antes 6); IPv4 que chega no eth1 → só eth1/IPv4 sonda.
- `addrreplace`: alias = 0 sondas; troca .2→.3 (passa pela ACD) → goodbye de .2 via IPv6, 3 sondas IPv4, anúncio .3.
- Regressão: hostname, dnssd (69/0), dnssd_gone, resolver, follow, timing, tools, interop, clockstep,
  foreignaddr - sem falha; dnssdlinktest e dnssdlinkarostest 0 falhas.
- m68k (A3000/68030, 1 placa, ROM com B73): ipv4only, dnssd (69/0), tools, hostname, resolver, follow,
  dnssd_gone, clockstep sem falha; resolver-stack ≤ 4196 B de pilha. `timing` falha também na base (anúncios
  965-987 ms, reenvios 937-994 ms no fio): **B77**, anterior, do relógio do m68k emulado, não da etapa 1.
- Atenção de bancada: `resolver`, `resolver-stack`, `foreignaddr` e `samesegment` são bash (`$'\n'`); sob `sh`
  o `resolver` em m68k não apagava `services.d/mdns` e falhava "no mdnsd" (falso).
- **`samesegment` (B60) continua falhando, com outro sintoma:** antes ficava preso sondando (~230 sondas, nunca
  anunciava); agora um enlace vence, anuncia, e o outro enlace ouve o anúncio como conflito → 50 renomeações
  (arosbox-2 … -51). Mesma causa (sem classificação de pacotes próprios no transporte); decisão pendente: B60
  antes de publicar a série.

### 9.4 Custos medidos
- m68k (`m68k-aros-size`): texto 50 650 → 53 490 (+2 840), bss 62 348 → 63 696 (+1 348: `md_HostPubs` 896 B,
  `md_LinkChange` 448 B). `MDNSPub` 28 B; `MDNSRegisteredService` 2 444 B (dos quais 256 B de arrays por slot).
- Memória real (`tests/mdns/memory.sh` + `memsvc`, AvailMem, cliente + mdnsd):
  - m68k A3000/68030, 1 enlace: 1 / 10 / 50 serviços = 16 432 / 50 128 / 200 432 B (base: 16 432 / 66 560 / 192 216);
    ~3,6-3,8 KB por serviço; degraus de 4 KB (puddles do alocador) - diferenças ±16 KB são granularidade.
    mdnsd ocioso: 4 784 B a mais livres na base (≈ estático + alinhamento de hunk).
  - hosted x86-64: 1 enlace 76 336 / 44 224 / 202 720 (base) vs 76 336 / 44 192 / 202 704; 2 enlaces 221 312 vs
    221 264 com 50 serviços. O 2º enlace custa ~370 B por serviço - o **cache** do mdnsd (cópia dos próprios
    registros por enlace), não o estado de publicação: ponto para a etapa 2.
  - A etapa 1 não muda o custo por serviço (não toca serviços); 2 enlaces no m68k não foram montados (só A2065):
    o comportamento multi-enlace é provado no hosted e confirmado no m68k com 1 placa (decisão do usuário).

## 10. Desempate por enlace, B60 e etapa 2 (2026-11-16/17, local, sem push)

Ordem dos commits em `review/mdnsd-record-lifecycle` (`~/AROS-ipv6`), cada um compilável:
`c58cce7bf5` diferença de inventário → `5f58ff74f0` FAMILY_DOWN nomeia endereços → `1ff96c058e` etapa 1 (host) →
`e9f94e5d91` reivindicação por enlace (desempate) → `7808574ff7` B60 → `e1cf7a20ed` etapa 2 (serviços).

### 10.1 Reivindicação por enlace (`e9f94e5d91`)
`probetie.sh` mostrou: com sub-estados por família, perder o desempate atrasava só a família da sonda; a outra
anunciava no mesmo segmento. Regra: a reivindicação é do **enlace**. Se o nome já responde no enlace por qualquer
família → não há desempate; a sonda do outro é pergunta, respondida em defesa pela família dela (§8.1, §9). Senão,
perda → todas as famílias ainda sondando no enlace recomeçam em 1 s (§8.2). Outros enlaces seguem.
`probetie` LOSE/WIN/WIN4 passam (WIN: 0 anúncios em qualquer família enquanto o outro sonda; WIN4: IPv6 já tinha o
nome, IPv4 defende; um só renome quando o outro anuncia mesmo assim). Serviço só responde depois da própria
sondagem (`rs_State`), conferido.

### 10.2 B60: diário de pacotes enviados no transporte (`7808574ff7`)
- `mdnsNetIsOwnPacket()` antes de qualquer lógica: próprio = origem nossa no enlace de recepção (loopback), ou
  **eco**: chega por outro enlace, com origem = endereço nosso **no enlace por onde saiu**, e é o mesmo pacote byte a
  byte (FNV-1a + soma tipo Fletcher + tamanho, por família). Sem identificador no pacote (EDNS0 Owner tem semântica
  própria; decisão do usuário: não estender o protocolo).
- Expiração pelo progresso da recepção: a assinatura sai quando o socket da família foi visto vazio ≥ 1 s depois do
  envio (`mdnsNetIdle()`, só quando o `WaitSelect()` olhou os sockets - não quando um sinal o encerrou); teto de 30 s.
  Anel cresce enquanto cheio de assinaturas pendentes; volta a zero quando esvazia; com 1 enlace nada é guardado.
- **Conservador:** na dúvida (assinatura sumida, eco > 1 s atrasado, sem memória) o pacote é de outro host → no
  máximo falso conflito; nunca esconde conflito de outro host (cópia idêntica = mesmos registros).
- Resultados: samesegment 0/20/50 serviços passam (412 anúncios simultâneos); netem 300/900 ms passam; **2 s falha**
  (falso conflito, renomes) - limite conhecido; foreignaddr detecta o conflito real; saturação forçada (teto 8,
  build de teste): 2896 despejos → falsos conflitos, conflito real ainda detectado; pico 1024 assinaturas (20 KB) com
  50 serviços em 2 enlaces, liberadas depois. m68k +1560 texto, +24 bss, 0 em tempo de execução com 1 enlace.

### 10.3 Etapa 2: serviços por enlace e família
- `mdns_pub.c` ganhou a mecânica comum: `mdnsFamilyStep()` (sondas, anúncios, atualizações §8.4), `mdnsPubAnswers/
  Asked/Defer/Update` (reivindicação por enlace); host refatorado para usá-la.
- Cada serviço: `rs_Pubs` (AllocVec, dobra), só nos enlaces do seu escopo (`interface_index` da registração, antes
  ignorado); somem `rs_Step/NextTick/Multicast` e os arrays `rs_MulticastTick[32]`/`rs_TypeTick[32]`; limite de 1 s
  por (enlace, família) em `fp_Multicast`, PTR de tipo por enlace em `p_TypeTick`.
- Posse global: conflito em qualquer enlace → novo nome, todas as Pubs recomeçam; o cliente é avisado uma vez por
  nome (`rs_Told`).
- Coordenador `mdnsRegLinksChanged()`: FAMILY_UP → só (L, f) sonda (proxies também: conectividade nova);
  FAMILY_DOWN → (L, f) desliga; mudança só de endereço → nada; overflow → recomeça tudo.
- Serviço do host anda em L só onde o nome do host está estabelecido em L; proxy não depende do host; rename do host →
  2 anúncios de atualização só dos serviços não-proxy.
- Seleção de registros nas respostas, known-answer e respostas atrasadas: inalteradas (o serviço já respondia
  pergunta específica com o conjunto inteiro - decisão anterior, mantida).
- Hosted: `availability.sh CHANGE=family` (IPv4 chega ao eth1, perguntas no eth0): etapa 1+B60 → serviço 1,7 s sem
  resposta no eth0 e 6 sondas em cada enlace (IPv4+IPv6); etapa 2 → sem lacuna, 0 sondas no eth0, 3 sondas só IPv4 no
  eth1. Anúncios do serviço: exatamente 2 por (enlace, família) (antes 4 por IPv6). Regressão hosted toda limpa.
- Memória hosted, 50 serviços: 1 enlace 202 672 → 192 368 B; 2 enlaces 221 264 → 212 496 B.
  m68k: `MDNSRegisteredService` 2 444 → 2 188 B, + 32 B por enlace (AllocVec); texto +1516, bss +128 (`p_TypeTick`).
- Memória real m68k (68030, 1 enlace, AvailMem): 1 / 10 / 50 serviços = 16 216 / 56 184 / 181 416 B (B60: 16 432 /
  58 344 / 192 216): **−216 B por serviço**; mdnsd ocioso −1 976 B livres (código e tabelas). Regressão m68k limpa
  (ipv4only, dnssd 69/0, tools, hostname, follow, dnssd_gone, clockstep, resolver); `timing` = B77.
