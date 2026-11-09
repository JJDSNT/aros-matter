# Grupo 11 — auditoria de paridade IPv4 (2026-11-09)

Pergunta: o que o IPv6 do AROSTCP ganhou (grupos 1–7, G10c) e o IPv4 não tem? Fonte: código na ponta da
pilha (`review/arostcp-ipv6-fixes`), Readme §6–7. Cada item "lacuna" precisa de um teste que falhe no
master antes de virar commit; "ok" não muda nada.

## Resultado

| # | Área | IPv6 | IPv4 | Veredito |
|---|---|---|---|---|
| P1 | Interface de chegada e origem por datagrama | `IPV6_PKTINFO` (recebe interface + destino; envia origem + interface), `IPV6_RECVPKTINFO` | só `IP_RECVDSTADDR` (destino); nada da interface; nada para escolher origem/interface por datagrama | **lacuna** — FreeBSD: `IP_RECVIF` (sockaddr_dl) e `IP_SENDSRCADDR`; Linux/macOS: `IP_PKTINFO` |
| P2 | Interface de multicast por índice | `IPV6_MULTICAST_IF` e `ipv6_mreq` por índice | `IP_MULTICAST_IF`/`IP_ADD_MEMBERSHIP` só por endereço (`in_addr`); sem `struct ip_mreqn` | **lacuna** — FreeBSD e Linux aceitam `ip_mreqn` (`imr_ifindex`) |
| P3 | Conflito de endereço | DAD (RFC 4862) com estado `IN6_IFF_TENTATIVE/DUPLICATED`, `SIOCGIFAFLAG_IN6` e sinal ao fim do DAD | só no IPv4 link-local automático (autoip, RFC 3927); endereço estático/DHCP: só log "duplicate IP address", sem sonda, sem defesa, sem estado para aplicações; o `dhclient` delega o ARPCHECK a script (no-op) | **lacuna** — RFC 5227 (ACD): sonda antes de usar, defesa, estado e sinal |
| P4 | Alcançabilidade do vizinho | NUD (RFC 4861 §7.3): REACHABLE/STALE/PROBE, sonda unicast | ARP: entrada completa vive 20 min (`ARPT_KILLC`) sem confirmação; MAC trocado fica errado até expirar ou chegar ARP | **lacuna (média)** — RFC 1122 §2.3.2.1 só exige expirar; Linux faz NUD também para ARP |
| P5 | Roteador padrão por alcançabilidade | G18a (round robin, sonda RFC 4191 §3.5) | um gateway padrão; sem detecção de gateway morto (RFC 1122 §3.3.1.4) | **lacuna (baixa)** — raro ter vários gateways IPv4 no AROS |
| P6 | Validação de Redirect | G18b | `rtredirect()`: só do gateway atual, novo gateway no link (RFC 1122 §3.2.2.2) | ok |
| P7 | Path MTU, black hole, DF | grupos 1–3 | grupos 2–3 (#2006, #2011) | ok |
| P8 | Ancilares de recepção | `IPV6_RECVHOPLIMIT`, `IPV6_RECVTCLASS` | `IP_RECVTTL`, `IP_RECVTOS` | ok |
| P9 | `SO_BINDTODEVICE`, socket de interface removida | 5b | 5b (as duas famílias) | ok |
| P10 | Sinal de mudança de endereço | 5b | 5b (testado para v4 e v6) | ok |
| P11 | Endereço link-local | automático (SLAAC) | autoip (RFC 3927) existe | ok (avaliar zonas com duas interfaces, RFC 3927 §3.2) |

**Fora da paridade (lacuna nas duas famílias):** multicast com filtro de fonte (SSM). `IP_ADD_SOURCE_MEMBERSHIP`,
`MCAST_JOIN_SOURCE_GROUP` estão declarados em `<netinet/in.h>` e não implementados; não há IGMPv3 (RFC 3376); o
MLDv2 é parcial (só relatórios MODE_IS_EXCLUDE). Item próprio, grande.

## Proposta do grupo 11 (ordem)

1. **P1 + P2** — API de interface IPv4, no estilo FreeBSD (os números do `in.h` do AROS já seguem o FreeBSD:
   `IP_RECVDSTADDR` 7, `IP_RECVTTL` 65, `IP_DONTFRAG` 67, `IP_RECVTOS` 68): `IP_RECVIF` (sockaddr_dl com índice e
   nome), `IP_SENDSRCADDR` (origem por datagrama), `struct ip_mreqn` em `IP_MULTICAST_IF`/`IP_ADD_MEMBERSHIP`.
   Avaliar também `IP_PKTINFO` (Linux/macOS; o mDNSResponder usa um ou outro). Interessa ao grupo 12 (mdnsd).
   Testes CUnit no loopback e na tap.
2. **P3** — ACD (RFC 5227) para endereços configurados: estado tentativo/duplicado por endereço IPv4 (como o
   FreeBSD `IN_IFF_TENTATIVE/DUPLICATED`), sonda, defesa, sinal; bench com um "intruso" na tap.
3. **P4** — confirmação de alcançabilidade no ARP (como o NUD), se o bench mostrar MAC velho sendo usado.
4. **P5** — só com caso real.

## Andamento

- **P1 + P2 feitos (2026-11-09)**, branch `review/arostcp-ipv4-iface` (sobre o master, independente da pilha TCP):
  `87a84247ad` `IP_RECVIF` (20) + `IP_SENDSRCADDR` (= `IP_RECVDSTADDR`), `c23fc39edb` `struct ip_mreqn` em
  `IP_MULTICAST_IF`/`IP_ADD_MEMBERSHIP`/`IP_DROP_MEMBERSHIP`. Testes no `cunit-net-cmsg` (15/15; master falha os 3
  novos: sem `IP_RECVIF`, origem 127.0.0.1, `ip_mreqn` recusado). 51 suítes ok com duas taps. `IP_PKTINFO` (Linux)
  não feito: o `in.h` segue o FreeBSD; o mDNSResponder aceita `IP_RECVIF`+`IP_RECVDSTADDR`.
- Próximo: P3 (ACD, RFC 5227).
