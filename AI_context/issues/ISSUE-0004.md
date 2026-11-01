---
id: ISSUE-0004
title: "Estratégia de descoberta: minimal_mdns do SDK × Bonami"
status: ready
priority: high
type: research
owner: jaime
milestone: M2
area: dnssd
created_at: 2026-10-28
updated_at: 2026-11-01
tags: [dnssd, mdns, bonami]
blockers: []
depends_on: [ISSUE-0001, ISSUE-0008]
upstream_refs: [connectedhomeip src/lib/dnssd/minimal_mdns, connectedhomeip src/lib/dnssd/Discovery_ImplPlatform.cpp, AROS workbench/network/mdns/README.md §Limits, AROS workbench/network/mdns/DISCOVERY.md]
related_files: []
---

# Por quê

A descoberta Matter precisa de: browse de `_matterc._udp` (comissionáveis) e `_matter._tcp` (operacionais), subtipos (`_L<disc>`, `_S<disc>`, `_CM`, `_I<compressed-fabric-id>`), TXT e **AAAA**. A Bonami hoje é só IPv4 (AAAA/`ff02::fb` ausentes), e IPv6 no mdnsd é trabalho futuro do mantenedor (ISSUE-0005).

# O quê

Opção A — `minimal_mdns` do SDK sobre bsdsocket: independe da Bonami, mas abre um segundo socket na 5353 ao lado do mdnsd.
Opção B — `Discovery_ImplPlatform` delegando à Bonami: integração "nativa", mas depende de ISSUE-0005 e de subtipos.

Recomendação inicial: **A no M2**, B como meta quando o mdnsd tiver IPv6, mantendo a interface do SDK (`ChipDnssd*`) para trocar sem tocar no controlador.

# Passos de validação

- [ ] Teste de coexistência na 5353 (ISSUE-0001) → os dois processos recebem o multicast
- [ ] Mapear a API `ChipDnssdBrowse/Resolve` contra Bonami `BrowseServiceTypeA`/`ResolveService`/`QueryRecordA` → tabela de lacunas (subtipos, AAAA, interface id)
- [ ] Rodar `minimal_mdns` em spike (após ISSUE-0006) contra um acessório de referência → anúncio real com endereço IPv6

# Critério de sucesso / falha

- Sucesso se: um caminho escolhido e justificado, com a tabela de lacunas da Bonami entregue ao mantenedor.
- Falha se: os dois caminhos estiverem bloqueados (ex.: sem multicast compartilhado na 5353 e sem IPv6 na Bonami).

# Decisões tomadas

- 2026-10-28: os dois caminhos dependem da ISSUE-0008 (multicast IPv6 no AROSTCP). A opção A também esbarra no bug C se o mdnsd ganhar IPv6 na mesma porta.

# Log

- 2026-10-28: criada.
- 2026-11-01: inclinação para a opção B (Bonami), registrada em research/2026-11-01-network-roadmap-integration.md §2.3: o núcleo IPv6 do mdnsd entrou (#1980), `QueryRecordA()` já resolve SRV/AAAA/TXT; faltam o evento estendido e subtipos (ISSUE-0005). A opção A fica só como ferramenta de teste, para não haver dois respondedores na 5353. Decisão final quando a trilha Matter voltar.
