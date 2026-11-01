# Backlog 3 — Requisitos de rede para W3C Open Screen no AROS

**Status:** planejado / auditoria de capacidades, ativação incremental delegada ao agente. **Data:** 2026-11-01.
**Escopo:** infraestrutura genérica AROS/AROSTCP e serviços compartilhados necessários para implementar o Open Screen Network Protocol no [AROS Prism](https://github.com/JJDSNT/aros-prism). **Não** implementar o protocolo Open Screen neste repositório.

## 1. Princípios e convivência

- Preservar as frentes ativas, [estado operacional](current_state.md), [Backlog 2](backlog2.md) e marcos Matter M0–M6; **nenhuma precedência global** entre B3, B2 e Matter. O agente pode ativar e repriorizar B3 autonomamente conforme dependências comprovadas, valor, risco e capacidade, documentando a decisão, sem interromper PRs em andamento.
- Auditar o upstream real, bibliotecas, contrib/ports, configurações de build e branches relevantes **antes** de classificar uma capacidade como ausente. Classificações: comprovada por teste, presente mas não validada, parcial, ausente, não aplicável.
- Priorizar testes e correções genéricas upstream; Open Screen (agentes, sessões, mensagens CBOR e aplicação) pertence ao Prism. Matter não depende de QUIC.
- Coordenar DNS-SD/mDNS com a frente Bonami do [aros-midihub](https://github.com/JJDSNT/aros-midihub), evitando duplicação e alterações concorrentes.
- SPAKE2 do Open Screen **não é automaticamente equivalente** a SPAKE2+ do Matter. Não criar primitivas criptográficas próprias.
- Todo trabalho funcional em AROSTCP segue a política de PRs do mantenedor (commits coerentes com testes; bump de revisão em `bsdsocket/version.h` quando aplicável). Validar ambas as passagens CUnit.

## 2. Matriz de requisitos e provas

| ID | Requisito | Responsável preferencial | Critério de aceitação / evidência |
|---|---|---|---|
| B3-01 | UDP IPv4 e IPv6, unicast bidirecional | AROSTCP | Cliente/servidor reais em hosted/TAP, IPv4/IPv6, datagramas >=1200 bytes, sem truncamento silencioso |
| B3-02 | Multicast IPv4/IPv6, escopo e interface | AROSTCP | Join/leave, seleção de interface, envio/recebimento mDNS em duas interfaces; IPv6 link-local com scope ID |
| B3-03 | Descoberta DNS-SD/mDNS de serviços UDP | Bonami/mdnsd e adaptadores compartilhados | Anúncio, browse, resolve e remoção de serviço de teste; PTR, SRV, TXT, A/AAAA; IPv4 e IPv6; verificar tipo de serviço e TXT exigidos pela versão normativa do Open Screen antes de fixá-los |
| B3-04 | Sockets não bloqueantes e event loop | AROSTCP + runtime | `fcntl`/equivalente, `select` e/ou `poll`, send/recv e cancelamento sob carga; ausência de busy loop |
| B3-05 | Temporização monotônica e precisão | Runtime compartilhado | Timers de retransmissão/pacing e timeouts QUIC testados, inclusive rollover e suspensão; documentar resolução |
| B3-06 | UDP MTU e sinalização de erros | AROSTCP + QUIC | PMTUD IPv4/IPv6, ICMP Fragmentation Needed / ICMPv6 PTB, erros de socket e tratamento de black holes; testar MTUs 1280/1500 e caminhos estreitos |
| B3-07 | Buffers UDP e desempenho | AROSTCP | Tamanhos de buffer, rajadas, perdas, truncamento, EWOULDBLOCK, múltiplas sessões e ausência de corrupção |
| B3-08 | Seleção de endereço e múltiplas interfaces | AROSTCP + descoberta | IPv4/IPv6, source address, scope ID, mudança de interface, resolução A/AAAA, reconexão após perda de rede |
| B3-09 | QUIC funcional sobre AROSTCP | Biblioteca compartilhada, consumida pelo Prism | Identificar implementação real (inclusive OpenSSL/contrib); verificar build, API, TLS 1.3, ALPN, handshake, streams, flow control, encerramento e interoperabilidade com peer de referência |
| B3-10 | TLS 1.3 e material criptográfico | Biblioteca crypto compartilhada | Validar backend efetivamente habilitado, entropia, certificados, validação de peer, falhas negativas e persistência segura; não inferir suporte QUIC apenas da presença de OpenSSL |
| B3-11 | SPAKE2 específico do Open Screen | Biblioteca crypto / Prism | Verificar implementação e perfil exato exigido pela especificação; vetores e interoperabilidade, sem reutilizar SPAKE2+ sem análise |
| B3-12 | Observabilidade e testes de regressão | AROSTCP + integração | CUnit + testes host/TAP, captura de pacotes, logs sem segredos, matriz por arquitetura e revisão upstream |
| B3-13 | QoS/DSCP e tuning (opcional) | AROSTCP | Investigar apenas após interoperabilidade básica; não bloquear o primeiro slice |

**Nota de escopo:** PLPMTUD (RFC 8899), congestion control, retransmissão e controle de fluxo QUIC pertencem principalmente à implementação QUIC; o AROSTCP deve fornecer sockets UDP e sinalização utilizáveis, não duplicar esses algoritmos. Modernizações TCP (CUBIC, SACK, PRR, RACK etc.) não são pré-requisitos do QUIC.

## 3. Auditoria inicial obrigatória

1. Fixar revisão de AROS upstream, contrib, aros-matter, aros-midihub e aros-prism; ler configuração real de mbedTLS/OpenSSL e qualquer biblioteca QUIC. Registrar arquivo, commit, opções de build e prova funcional. A presença de código ou de API não prova funcionamento.
2. Reconciliar B3-01/02/06/08 com ISSUE-0008, grupos IPv6 e B2-B, especialmente PRs já mergeados de multicast, PMTUD e ICMPv6; evitar novas issues para trabalho já concluído.
3. Reconciliar B3-03 com Bonami/mdnsd e seu roadmap IPv6. Caso o DNS-SD genérico ainda não esteja pronto, registrar alternativa provisória sem bifurcar o serviço.
4. Auditar QUIC com especial atenção ao port OpenSSL em `aros-development-team/contrib/development/libs/openssl` e verificar se QUIC está realmente habilitado, exportado e interoperável; procurar outras implementações antes de propor um port.
5. Confirmar a versão da especificação W3C, tipo de serviço DNS-SD, requisitos de segurança e handshake; documentar divergências entre versões.

## 4. Fatias incrementais sugeridas (ordem revisável)

- **B3-A — Evidências:** matriz de capacidades com links para código, configuração e testes; sem patches por presunção.
- **B3-B — Descoberta:** serviço UDP de teste anunciado/resolvido via DNS-SD/mDNS com IPv4/IPv6, múltiplas interfaces e remoção.
- **B3-C — Transporte:** aplicação QUIC mínima sobre AROSTCP, handshake TLS 1.3, ALPN e stream de eco com peer interoperável; validar perda, MTU e timeouts.
- **B3-D — Segurança:** avaliar SPAKE2, certificados, entropia e armazenamento conforme perfil normativo do Open Screen; provas negativas.
- **B3-E — Handoff ao Prism:** relatório de interfaces, APIs, dependências, limitações e testes reproduzíveis; implementação do Open Screen fica no Prism.

## 5. Ativação e governança do agente

O agente está autorizado a ativar autonomamente itens B3 quando houver oportunidade técnica justificada, sem exigir a conclusão integral de B2 ou Matter. Antes de ativar, conferir estado operacional, upstream e PRs; reconciliar itens sobrepostos; selecionar no máximo 2–3 entregas pequenas; registrar justificativa, dependências, critérios de aceite e evidências em issues de `AI_context/issues/` e atualizar `current_state.md`. Não alterar M0–M6, não renumerar issues, não duplicar frentes Bonami e não impor prioridade fixa ao Prism sobre Matter. Mudanças de ABI ou de arquitetura com alto risco requerem decisão do mantenedor.

## 6. Definição de pronto

Uma aplicação de referência no AROS consegue: (a) anunciar e descobrir serviço UDP com DNS-SD em rede local, (b) resolver endereço/porta IPv4/IPv6, (c) estabelecer QUIC/TLS 1.3 com peer externo, (d) trocar streams sob perda/MTU reduzida e (e) demonstrar a autenticação exigida pelo perfil Open Screen. Todas as capacidades têm testes reproduzíveis e limites documentados. **Isso habilita a infraestrutura; não equivale à implementação completa do Open Screen.**

## Referências

- [W3C Open Screen Network Protocol](https://www.w3.org/TR/openscreen-network/)
- [AROS upstream](https://github.com/aros-development-team/AROS)
- [AROS contrib](https://github.com/aros-development-team/contrib)
- [AROS Prism](https://github.com/JJDSNT/aros-prism)
- [Backlog 2](backlog2.md)
- [Estado operacional](current_state.md)
