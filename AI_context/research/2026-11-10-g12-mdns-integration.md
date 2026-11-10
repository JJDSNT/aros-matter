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
| M5 | bonami | Sem consulta genérica de host (README: "Generic host lookup ... remain separate") | interface natural para S1 usar o daemon quando ele roda |
| C1 | terceiro | IPP (`devs/ipp/dnssd.c`) tem cliente mDNS próprio (one-shot), não usa o bonami | consolidar descoberta de impressoras |
| C2 | servidores | Só o `netmidid` publica serviço pelo bonami; o `sshd` do tree poderia publicar `_ssh._tcp`/`_sftp-ssh._tcp` | RFC 6763 |

## Questões a decidir (com o usuário)

- S1: one-shot na própria pilha (funciona sem mdnsd, como o `dnssd.c`) e/ou delegar ao mdnsd quando ele roda (cache,
  conhecimento de conflitos) — depende de M5. Modelo de referência: nss-mdns (glibc) fala com o daemon (Avahi);
  macOS/mDNSResponder também.
- Quais itens M* o usuário quer que eu faça no código dele, e quais ele faz.
