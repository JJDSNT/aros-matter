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

## 5. Custo estimado (m68k) - a medir

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
