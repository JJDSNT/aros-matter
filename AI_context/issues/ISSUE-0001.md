---
id: ISSUE-0001
title: "Matriz de capacidades M0 com evidência"
status: doing
priority: high
type: audit
owner: jaime
milestone: M0
area: network
created_at: 2026-10-28
updated_at: 2026-10-30
tags: [m0, audit]
blockers: []
depends_on: [ISSUE-0007, ISSUE-0008]
upstream_refs: [AROS@cbca98214f, connectedhomeip@8fd0af0792]
related_files: [docs/architecture-and-research.md, AI_context/research/2026-10-28-initial-desk-audit.md]
---

# Por quê

O M0 exige que cada linha da matriz (§4 de `docs/architecture-and-research.md`) tenha resultado testado, limitação ou bloqueio explícito. Sem isso, o port do SDK vira aposta.

# O quê

Preencher a matriz em duas camadas: (a) leitura de código com SHA; (b) teste executado no AROS. Fica de fora qualquer código Matter.

# Passos de validação

- [x] Leitura de código: IPv6, multicast, Bonami, mbedTLS, entropy → `research/2026-10-28-initial-desk-audit.md`
- [x] IPv6 UDP unicast (loopback), `WaitSelect`, `if_nametoindex`, `SIOCGLIFADDR` → `research/2026-10-28-hosted-tests.md`
- [~] Multicast IPv6 com host Linux via tap: envio só com contorno, recepção falha → bugs no AROSTCP, ISSUE-0008
- [~] Dois sockets na 5353 com `SO_REUSEPORT`: o bind funciona; a entrega a ambos falha por código (bug C, ISSUE-0008)
- [ ] Entropy: `entropy.resource` no alvo escolhido (ISSUE-0002); caminho de falha
- [ ] Timers monotônicos e `WaitSelect()` com timeout/cancelamento → teste de estresse
- [ ] Persistência: escrita atômica (rename) no filesystem do alvo → teste de queda/restart
- [ ] SPAKE2+/CASE → delegado a ISSUE-0003

# Matriz (estado em 2026-10-30, AROSTCP master `be237767fa`, hosted x86-64 + tap)

Requisitos de rede do Matter (Core spec; endereços de grupo conferidos no SDK `8fd0af0792`, `PeerAddress::BuildMatterPerGroupMulticastAddress` e `TestPeerAddress.cpp`, e no roteiro TC_SC_5_3). Evidência = teste que passa no master; "antes" = AROSTCP `343de5cddf`, antes da série IPv6.

| Requisito | Estado | Evidência |
|---|---|---|
| IPv6: link-local, SLAAC, DAD, zonas (`%if`), `bind`/`connect`/`getsockname`/`getpeername` com zona | ✔ | `cunit-net-scope6`, `-addr6`, `-slaac6` (#1974, #1950, #1979) |
| Origem e interface: escolha por escopo (RFC 6724 2/3/7), `IPV6_PKTINFO`, `sin6_scope_id`, `IPV6_MULTICAST_IF` | ✔ | `cunit-net-srcaddr6`, `-sendto6`, `-cmsg` (#1970, #1973, #1975, #1947) |
| mDNS: `ff02::fb:5353` com vários sockets na porta, loopback, MLD da link-local | ✔ | bancada `link.*`, `mld.*`; `cunit-net-mcast6`, `-mld6` (#1924, #1945, #1970) |
| **Groupcast Matter:** UDP 5540 em `FF35:0040:FD<fabric>00:<group>` e `ff05::fa` (escopo de site) | ✔ (antes: 5/10 falhas) | bancada `matter.group-recv`, `matter.group-send` (10/10); antes: não recebe (#1945) e `EADDRNOTAVAIL` no envio (#1975). `research/logs/2026-10-30/matter-groupcast/` |
| Rota até a malha Thread pelo border router (RFC 4191 RIO) | ✔ | `cunit-net-rio6` (#1976) |
| Raw IPv6 / ICMPv6 (diagnóstico, ND) | ✔ | `cunit-net-raw6` (#1971) |
| Multicast de grupo **sem** interface indicada | limitação | sai pela primeira interface ativa (G18h); o SDK indica a interface por envio |
| Relógio (validação de certificados) | **lacuna** | sem SNTP na pilha (R7) |
| DNS em rede só IPv6 (RDNSS) | lacuna | R4; o Matter usa mDNS, então não bloqueia |
| `localhost` | lacuna | `hosts` padrão vazio (stackprobe S1) |
| TCP do Matter 1.3+ (opcional) | **a medir** | bancada TCP no fio (próximo) |
| DNS-SD (`minimal_mdns`) | aberto | ISSUE-0004 |
| Entropia / persistência / timers | aberto | ISSUE-0002, -0003; passos abaixo |

# Critério de sucesso / falha

- Sucesso se: todas as linhas da matriz têm "testado OK", "limitação documentada" ou "bloqueio com issue".
- Falha se: alguma linha permanece só com leitura de código ao iniciar o M1.

# Evidências

- Leitura de código: `research/2026-10-28-initial-desk-audit.md`.
- Testes no hosted: `research/2026-10-28-hosted-tests.md`, `research/logs/2026-10-28/`.

# Decisões tomadas

# Log

- 2026-10-28: criada; primeira rodada de leitura de código concluída.
- 2026-10-28: testes IPv6 no hosted; abertas as lacunas da pilha na ISSUE-0008.
- 2026-10-30: matriz atualizada com a série IPv6 (#1924–#1979); groupcast Matter testado com o host como par (10/10; antes da série 5/10).
