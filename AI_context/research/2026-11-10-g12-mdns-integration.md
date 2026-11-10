# Grupo 12 — integração AROSTCP ↔ mDNS/DNS-SD — levantamento (2026-11-10)

Objetivo (do usuário, 2026-11-09): "uma boa integração entre o arostcp e o mdns/dns-sd, para termos e utilizarmos
adequadamente as integrações". Leitura: a pilha oferece contratos dual-stack (estado de endereço, sinal de mudança,
inscrição multicast por interface, interface de chegada/origem por datagrama); o mDNS os consome; as aplicações
resolvem `.local` e publicam/descobrem serviços por uma API comum.

Dono do código: **mdnsd/bonami.library são do usuário** (todos os commits; já dual-stack: núcleo IPv6 #1980, ciclo de
vida dos endereços IPv6 #2111). Mudanças ali: propor, o usuário decide. `devs/ipp/dnssd.c` é de outro colaborador
(terminills, spooler de 2026-11-09): só propor.

## O que o mdnsd já usa da pilha

Sinal `SBTC_SIG_ADDRESS_CHANGE_MASK` (+ varredura de 3 s como reserva); `SIOCGIFAFLAG_IN6` (não usa endereço IPv6
tentativo/duplicado/destacado/deprecado); um socket IPv6 em `ff02::fb` em todos os enlaces com `IPV6_RECVPKTINFO`;
um socket IPv4 por interface com `SO_BINDTODEVICE` + `IP_ADD_MEMBERSHIP` (por endereço) + `IP_MULTICAST_IF`.

## Lacunas encontradas

| # | Lado | Lacuna | Base |
|---|---|---|---|
| S1 | **pilha** | O resolver (`api/gethostnamadr.c`: `gethostbyname`/`2`, `gethostbyaddr`; `getaddrinfo` na API miami/roadshow) manda **todo nome ao DNS** (`res_search()`): `ping outro.local` não resolve por mDNS | RFC 6762 §3 (nomes `.local` por mDNS), §4 (reverso de 169.254/16 e fe80::/10), §5.1 (consulta one-shot), zona do link-local no resultado AAAA |
| M1 | mdnsd | Endereços IPv4 tentativos/duplicados (ACD do #2218) seriam anunciados: o mdnsd só consulta `SIOCGIFAFLAG_IN6` | simetria com #2111; `SIOCGIFAFLAG_IN` |
| M2 | mdnsd | IPv4 com um socket por interface (`SO_BINDTODEVICE`) e inscrição por endereço, enquanto o IPv6 usa um socket só + PKTINFO | `IP_RECVIF` + `ip_mreqn` por índice (#2218) permitem o mesmo desenho no IPv4 (opcional) |
| M3 | mdnsd | Varredura de 3 s como reserva | com o sinal também ao fim da ACD IPv4 (#2218), avaliar se ainda é necessária |
| M4 | bonami | Eventos de descoberta só IPv4 (`de_Address`) | DISCOVERY.md; dual-stack na API pública |
| ~~M5~~ | bonami | **Errado:** `LookupHostA()` já existe (#1836, com `QueryRecordA()`); o README só diz que é chamada separada | — |
| C1 | terceiro | IPP (`devs/ipp/dnssd.c`) tem cliente mDNS próprio (one-shot), não usa o bonami | consolidar descoberta de impressoras |
| C2 | servidores | Só o `netmidid` publica serviço pelo bonami; o `sshd` do tree poderia publicar `_ssh._tcp`/`_sftp-ssh._tcp` | RFC 6763 |

## Questões a decidir (com o usuário)

- S1: one-shot na própria pilha (funciona sem mdnsd, como o `dnssd.c`) e/ou delegar ao mdnsd quando ele roda (cache,
  conhecimento de conflitos) — depende de M5. Modelo de referência: nss-mdns (glibc) fala com o daemon (Avahi);
  macOS/mDNSResponder também.
- Quais itens M* o usuário quer que eu faça no código dele, e quais ele faz.

## Fontes do usuário (aros-midihub/docs, lidas 2026-11-10)

- `mdns-arostcp.md` — **princípio de arquitetura do usuário: o mDNS fica acima da pilha**; a `bsdsocket.library` só
  oferece mecanismos (sockets, reuse, `SO_BINDTODEVICE`, opções multicast, `SIOCGIFCONF`/`FLAGS`, `gethostname()`);
  política (registros, sondagem, renome, cache, browse) é do mdnsd, para não amarrá-lo ao AROSTCP. mdnsd é serviço
  gerenciado (`db/services.d/mdns`, `netservices.library`), um por host; clientes falam com ele pela porta "BonAmi".
- `mdns-backlog.md` — pendências do mdnsd já acompanhadas pelo usuário: MD01 (hook do cliente roda no processo do
  mdnsd, P0), MD03 (cliente não sabe do renome), MD05/06 (m68k, interop Bonjour/Windows), MD13 (≤ 8 interfaces),
  MD14 ("IPv4 only" — desatualizado desde #1980). **Nada sobre o resolver da pilha (`.local` em
  `gethostbyname`/`getaddrinfo`)**: S1 não está planejado em lugar nenhum.

## Consequência para S1 (resolver `.local`)

A opção "a pilha faz a consulta mDNS sozinha" contraria o princípio acima. Opções coerentes com ele:
- (b) o resolver da `bsdsocket.library` vira **cliente** do mdnsd: para nomes `.local` (e o reverso de 169.254/16,
  fe80::/10) abre o `bonami.library` sob demanda e chama `LookupHostA()` com prazo; sem mdnsd, falha como hoje
  (como o nss-mdns da glibc fala com o Avahi). Dependência opcional, em tempo de execução.
- (c) a resolução `.local` fica fora da pilha (cada programa usa o bonami) — documentar; `ping x.local` continua sem
  funcionar.
Decisão do usuário.

## Trabalho do Codex (achado 2026-11-10)

`~/aros-midihub-mdns-codex`, branch `review/mdns-modernization-plan` (16 commits sobre o main do midihub, último
2026-11-09; não mesclado no main do midihub, sem PR upstream). Documento central:
`docs/dnssd-native-architecture-decision.md` (ADR "accepted", 2026-11-09), mais roadmap, auditorias de reuso/núcleo/
proveniência, validação, um protótipo de coordenador (`prototypes/dnssd/`) e o patch do núcleo IPv6.

**ADR:** um serviço DNS-SD nativo do AROS: `dnssd.library` (fachada fina, API nova, assíncrona, por message port) →
`mdnsd` (dono de sockets, cache, sondagem, conflitos, registros, interfaces; pode ser redesenhado por inteiro) →
`bsdsocket.library`. **Substitui o `bonami.library`**, sem compatibilidade de API/ABI nem adaptador (proveniência e
licenças preservadas). Eventos dual-stack com interface/escopo (resolve o M4 e o MD01). "AROSTCP dependency rule":
capacidade genérica que falte à pilha é corrigida na pilha, numa proposta própria, e consumida depois; polling só como
proteção contra notificação perdida.

**Alinhamento com a proposta de três camadas:** igual no limite mdnsd/pilha e na regra de dependência (casa com o G11).
Falta no ADR: (1) o **resolver do sistema** como cliente (`.local` em `gethostbyname`/`getaddrinfo`) — não aparece;
(2) o contrato da pilha está genérico e não lista o que o G11 trouxe (estado de endereço IPv4 `SIOCGIFAFLAG_IN`,
`IP_RECVIF`/`ip_mreqn`) — falta separar contrato funcional e binding AROSTCP; (3) snapshot + eventos + reconciliação
está implícito (polling como proteção), não definido.

## Decisões do usuário (2026-11-10)

1. Base do G12: o ADR do Codex (`dnssd.library` substitui o `bonami.library`; mdnsd redesenhável).
2. Divisão: **Codex** = mdnsd + `dnssd.library` + migração de consumidores; **eu** = pilha (contrato/binding, o que
   faltar) + resolver do sistema. Ninguém mexe na área do outro.
3. Resolver `.local` como **cliente da `dnssd.library`**, aberta sob demanda (precedente: `miami.library` abre a
   `usergroup.library` só quando precisa); sem dependência de build/link; sem mdnsd, `.local` falha e nada mais muda.
   `localhost` continua resolvido pela própria pilha (RFC 6761, #2023). Sem ciclo: o mdnsd nunca resolve `.local` pelo
   resolver. Requisito para a `dnssd.library`: consulta de endereço síncrona de qualquer task, com prazo e cancelamento,
   IPv4+IPv6 com índice de interface.
4. Acordos escritos "em todo lugar relevante", por área com dono: **`aros-midihub/docs/mdns-integration-agreements.md`**
   (main, `56fde52c5e`, lido pelo Codex) — contrato funcional F1–F10 e binding AROSTCP, modelo snapshot/eventos/
   reconciliação, contrato do resolver; o `mdns-arostcp.md` ganhou aviso apontando para ele.

Pendências da minha área: o contrato F1–F10 já existe no AROSTCP quando o #2218 entrar; o resolver depende da API da
`dnssd.library` (nomes/ABI ainda abertos no ADR) — implementar quando ela existir.
