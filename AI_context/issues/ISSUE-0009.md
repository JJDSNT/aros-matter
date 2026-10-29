---
id: ISSUE-0009
title: "AROSTCP: rotas não seguram referência ao endereço (ifa_refcnt sem uso) — uso após liberação intermitente"
status: backlog
priority: high
type: upstream
owner: jaime
milestone: M0
area: network
created_at: 2026-10-28
updated_at: 2026-10-28
tags: [upstream, arostcp, route, ifaddr, use-after-free, ipv4, ipv6]
blockers: []
depends_on: []
upstream_refs: [AROS@4c2c268a53 common/include/net/if.h:424 ifa_refcnt, net/route.c rtrequest/rtfree, net/if_sana.c:194-240 sana_if_deconfigure, netinet6/in6.c in6_purgeaddr]
related_files: [AI_context/research/logs/2026-10-28/s1-ab/crash-gdb.txt, tests/ipv6/ipv6test.c]
---

# Por quê

Durante a validação da S1 (ISSUE-0008), uma rodada travou com SIGSEGV em `rtrequest()` no caminho `RTM_DELETE`, chamado por `rt_purgeif()` no reload que remove a interface. A chamada indireta `rt->rt_ifa->ifa_rtrequest(RTM_DELETE, …)` (deslocamento `0x28` de `struct ifaddr`, `edi=2`) usou um `ifa` já liberado, cujo conteúdo eram os bytes do IID do link-local. Isso aconteceu depois de um endereço IPv6 ser adicionado e removido por `SIOCDIFADDR_IN6`.

Causa provável: `struct ifaddr` tem `ifa_refcnt` (`common/include/net/if.h:424`), mas nada o usa. No 4.4BSD-Lite, `rtrequest(RTM_ADD)` faz `ifa->ifa_refcnt++` e `rtfree()` faz `IFAFREE(rt->rt_ifa)`; o endereço só é liberado quando a última rota solta. No AROSTCP, `in6_purgeaddr()` libera o mbuf direto. O comentário de `sana_if_deconfigure()` (`if_sana.c`) já registra que `in6_ifscrub()` "não apagava de forma confiável" a rota de prefixo clonável, e por isso faz `rt_purgeif()` antes. O caminho por ioctl não tem esse cuidado. O IPv4 provavelmente compartilha a mesma lacuna (`in_control` com `SIOCDIFADDR`).

# O que se sabe (evidência)

- 1 travamento com o binário S1, sob gdb, sequência `mld.addr-owned` → `mld.ifdetach` (versão anterior do teste): `research/logs/2026-10-28/s1-ab/crash-gdb.txt`. O símbolo foi obtido casando os bytes do PC com o `.text` do AROSTCP: `rtrequest`.
- 5 rodadas seguintes com a S1 (`addr.delete-then-reload` 2x, sequência original 3x): sem trap. **Intermitente**: depende de a memória liberada ser reaproveitada.
- Upstream, `addr.delete-then-reload`: trap em toda rodada (2/2), em outro ponto (salto para endereço de dados), coerente com a associação solicited-node que nunca era deixada (corrigido pela S1).

# O quê

Implementar o tempo de vida do `ifaddr` como no 4.4BSD-Lite: rotas seguram referência (`ifa_refcnt`), `rtfree()` solta, `in_purgeaddr`/`in6_purgeaddr` soltam a referência da lista em vez de liberar direto. Vale para as duas famílias. Antes, confirmar com o Kal se há motivo histórico (AmiTCP) para a contagem não ser usada.

# Passos de validação

- [ ] Reprodução determinística: envenenar a memória liberada (preencher o mbuf antes do `m_free`) e repetir `addr.delete-then-reload`
- [ ] Inventário: quem guarda `rt_ifa`/`ifa` sem referência (rotas, ND, ARP, `ifnet_addrs`)
- [ ] Desenho com o Kal; implementação; o teste passa com envenenamento ativo

# Critério de sucesso / falha

- Sucesso se: com envenenamento ativo, `addr.delete-then-reload` e `mld.ifdetach` passam em 10 de 10 rodadas, em IPv4 e IPv6.

# Log

- 2026-10-29: **causa provável encontrada (G15d):** `SIOCAIFADDR_IN6` sobrescreve `ifa_flags` com os flags do pedido e apaga `IFA_ROUTE`, então `in6_ifscrub()` não remove a rota do prefixo; medido que `fd00:4d54:77::/64` sobrevive ao `SIOCDIFADDR_IN6` (`research/logs/2026-10-29/g15/`). O reload depois disso percorre uma rota cujo `rt_ifa` foi liberado. Não depende do `ifa_refcnt`: a rota não deveria sobreviver.

- 2026-10-28: criada a partir do travamento observado durante a S1.
