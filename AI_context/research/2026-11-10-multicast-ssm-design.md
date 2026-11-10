# Grupo multicast dual-stack (SSM) — desenho (2026-11-10, em andamento)

## Decisões do usuário (2026-11-10)

- Ordem: **G11 (#2218) → multicast dual-stack (este) → G12 (mDNS/DNS-SD)**. Motivo: consolidar a pilha antes de
  integrar consumidores; o SSM muda a representação das inscrições multicast, que o G12 usa (inscrições em
  224.0.0.251 / ff02::fb por interface).
- RFC 1256 (ICMP Router Discovery): **backlog**, sem PR, até haver caso de uso (preferência de roteadores, validade,
  expiração, convivência com DHCP/rotas manuais seriam responsabilidade nova). Se feito: programa à parte (`rdisc`),
  não código na pilha.
- Separado do #2218 (branch próprio).
- Refinamentos aceitos (texto do ChatGPT trazido pelo usuário): não decidir de antemão um núcleo compartilhado entre as
  famílias — homogêneo no **modelo e na API**, compartilhar implementação só onde reduzir duplicação; não supor que tudo
  será reescrito; **regressão do multicast comum desde o início**; quinta investigação: **filtragem na entrega**.

## Escopo funcional

IGMPv3 host (RFC 3376), MLDv2 host completo (RFC 3810), API RFC 3678 nas duas famílias (protocol-independent
`MCAST_*` e as `IP_*_SOURCE_*`), SSM (RFC 4604/4607), estados INCLUDE/EXCLUDE, relatórios de mudança de estado,
compatibilidade com IGMPv1/v2 e MLDv1 (modo de compatibilidade por interface conforme o querier), limites explícitos de
memória, filtragem efetiva na entrega aos sockets.

## Estado atual do AROSTCP (apurado)

| Peça | IPv4 | IPv6 |
|---|---|---|
| Inscrição do host | `struct in_multi` (grupo, ifp, refcount, estado, timer), lista global | `struct in6_multi`, idem |
| Inscrição do socket | `ip_moptions.imo_membership[IP_MAX_MEMBERSHIPS=20]` (ponteiros para `in_multi`), sem estado de fonte | `ip6_moptions.im6o_membership[20]`, idem |
| Protocolo | IGMPv2 (aceita relatório v1), `igmp.c` 398 linhas | MLDv1 + relatório MLDv2 só MODE_IS_EXCLUDE{} (`mld6.c` 591 linhas) |
| API SSM | `IP_ADD_SOURCE_MEMBERSHIP` (25) e `MCAST_*` (46…) **declarados**, não implementados | idem (`MCAST_*`) |
| **Entrega UDP** | `udp_input()`: todo socket na porta (laddr/faddr batendo) recebe — **não confere a inscrição do socket** (4.4BSD) | `udp6_input()`: idem, comentário explícito "the sockets are not filtered by their own memberships" |

As duas famílias seguem o mesmo modelo clássico (4.4BSD/KAME), simétrico.

## Modelo: FreeBSD (verificado no código)

Só o FreeBSD tem SSM completo no kernel (Bruce Simpson, 2009): `sys/netinet/in_mcast.c` (78 KB),
`sys/netinet6/in6_mcast.c` (81 KB), IGMPv3 em `igmp.c`, MLDv2 em `mld6.c`. NetBSD e OpenBSD: IGMPv2/MLDv1 apenas.
O FreeBSD tem **o mesmo modelo nas duas famílias, em implementações paralelas** (`in_mfilter`/`ip_msource`/`in_msource`
e os `in6_*`), com um filtro por socket na entrega (`imo_multi_filter()` / `im6o_mc_filter()`), estado "t0/t1" para
calcular as mudanças a reportar, e um limite de fontes por inscrição (`net.inet.ip.mcast.maxsocksrc`, `maxgrpsrc`).

## Investigações (pendentes)

1. **Estado no AROS** (feito, acima) — falta: timers do IGMP/MLD, como o querier é tratado, `IN_LOOKUP_MULTI`,
   raw sockets (raw_ip/raw_ip6) na entrega multicast.
2. **FreeBSD em detalhe**: estruturas de filtro (árvore RB por fonte), cálculo de deltas t0→t1, compatibilidade de
   versão por interface, quanto disso é compartilhável sem abstração artificial.
3. **Limites de memória**: por socket, por grupo; valores do FreeBSD (`maxsocksrc` 128, `maxgrpsrc` 512) frente às
   máquinas pequenas do AROS; alocação do vetor de inscrições (hoje fixo em 20).
4. **Testes**: regressão do multicast comum (`cunit-net-cmsg` v4, `mcast6`, `mcast6if`, `mld6`) a cada commit;
   novos CUnit da API; bench com **querier IGMPv3/MLDv2 no host** (consultas gerais, por grupo e por grupo-e-fonte;
   verificação dos relatórios na captura) e fontes múltiplas na tap.
5. **Filtragem na entrega** (achado: hoje nenhuma, nas duas famílias): filtro por socket (grupo + interface + fonte)
   em `udp_input`/`udp6_input` e nos raw; avaliar a mudança de comportamento para sockets na porta que não se
   inscreveram (o FreeBSD passou a filtrá-los) — decidir com teste de regressão e nota no PR.
