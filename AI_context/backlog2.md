# Backlog 2 — Modernização incremental do AROSTCP

**Status:** planejado, não ativado. **Data:** 2026-10-31.

> Documento de continuidade. Não é uma fila de execução nem autorização para alterar o backlog atual. O agente deve seguir `AI_context/current_state.md` e as issues ativas até que o mantenedor decida ativar uma frente.

## 1. Propósito e referências

Modernizar o AROSTCP upstream de forma incremental, portável e independente de Matter, Midihub, Prism ou Bellatrix: segurança, compatibilidade, PMTUD, recuperação de perdas, congestionamento, temporizadores e testes. Os marcos Matter M0–M6 continuam intactos.

Referências canônicas:
- [Estado operacional](current_state.md) e [regras de trabalho](README.md).
- [ISSUE-0008 — IPv6](issues/ISSUE-0008.md).
- [Desenho IPv6 e G18/G19](research/arostcp-ipv6-design.md).
- [Comparação Riptide × AROSTCP: R1–R11 e stackprobe](research/2026-10-30-riptide-comparison.md).
- [Arquitetura e marcos Matter](../docs/architecture-and-research.md).

**Licenças:** Riptide e stackprobe GPL são referências e ferramentas de bancada externas. Não copiar código GPL para AROS/APL nem versionar o porte local de stackprobe.

## 2. Convivência com o backlog atual

1. O backlog atual prevalece: não mudar status, prioridades, marcos, responsáveis ou ordem das issues ativas por causa deste documento.
2. Continuar as entregas já planejadas, conforme a decisão do mantenedor e evidências: G19b (MSS IPv6), G19e (T/TCP), G19h (close com dados não lidos), R1/G19g (portas efêmeras), G19i (anomalia de RTO), S1 (localhost), R4 (RDNSS/DNSSL), R7 (SNTP) e G18a–i. Esta lista **não impõe uma ordem**.
3. Não duplicar trabalho: R1 concluído no backlog atual satisfaz B2-A. G19b corrige MSS sem redesenhar PMTUD; G19i pode corrigir defeito reproduzido sem reformular os temporizadores globais.
4. G18a–i não são bloqueadores universais: itens não reproduzidos, decisões de API e pendências não críticas podem permanecer na trilha IPv6.
5. Bonami/mdnsd e o PR #1980 pertencem à sua frente existente; não absorvê-los neste backlog.
6. Antes de executar, reconferir upstream/master e PRs. Em 2026-10-31, #1979 e #1983 estavam mergeados; #1986 e #1980 abertos. Essa fotografia não substitui verificação atualizada.
7. Se um achado impactar uma issue em execução, registrá-lo primeiro na pesquisa/issue corrente. Este arquivo não é um canal paralelo de ordens.

## 3. Ponto de transição e ativação

**Condição sugerida, não obrigatória:** IPv6 funcional estabilizado na bancada hosted/TAP, G19b concluído ou encaminhado, regressões críticas controladas e ausência de conflitos relevantes com PRs sobrepostos. Não exigir fechamento de todo G18 nem conclusão do SDK Matter.

**A ativação depende de decisão do mantenedor.** Pode ser parcial, antecipada por bloqueio comprovado ou postergada por custo/risco. Ao ativar:
1. Conferir `current_state.md`, issues, upstream/master e PRs recentes.
2. Classificar cada candidato: concluído, em curso no backlog atual, pendente, precisa de pesquisa ou descartado.
3. Propor até 2–3 entregas pequenas e seus critérios de aceite.
4. Só após autorização criar issues necessárias no padrão `AI_context/issues/` e atualizar `current_state.md`.
5. Não renumerar ou reabrir issues antigas, nem reordenar M0–M6.

## 4. Frentes candidatas — prioridades iniciais revisáveis

### B2-A — Segurança e compatibilidade

- R1 / RFC 6056: somente se não resolvido pelo backlog atual.
- R2 / RFC 5961: challenge ACK e proteção contra RST/SYN cegos.
- R3: TCP_KEEPIDLE e TCP_USER_TIMEOUT; distinguir opções existentes TCP_KEEPINTVL/TCP_KEEPCNT.
- Stackprobe S2–S8: confirmar semântica, ABI e contrato Roadshow antes de alterar comportamento público. S1 pertence preferencialmente à trilha atual.
- **Antes de codificar:** auditar upstream, medir reprodução e discutir mudanças de ABI com Kal.
- **Saída:** testes negativos e de compatibilidade; PRs pequenos por contrato.

### B2-B — PMTUD e recuperação de perdas

- Auditar PMTUD IPv4/IPv6 existente: MSS, rotas, MTU cache, ICMP fragmentation-needed e ICMPv6 Packet Too Big.
- Separar PMTUD clássico de black-hole recovery e PLPMTUD (R11 / RFC 4821 e RFC 8899).
- Validar SACK/D-SACK e PRR existentes antes de propor mudança ou ativação.
- **Antes de codificar:** inspecionar `tcp_mss`, `tcp_output`, ICMP/ICMPv6 e rotas com revisão fixada.
- **Saída:** testes com MTUs diferentes, ICMP permitido/bloqueado, perda e retransmissão.

### B2-C — Temporizadores e congestionamento

- G19i/R10: investigar anomalia RTO, granularidade real de timers, backoff e RFC 6298.
- Verificar CUBIC/NewReno existentes e a negociação ECN; avaliar HyStart++ (R11) somente depois de compreender o caminho atual.
- **Antes de codificar:** medir tempos reais e efeitos em outros subsistemas; não alterar timers globais por suposição.
- **Saída:** testes de RTO/backoff, ECN com e sem suporte do par, congestionamento e ausência de regressão.

### B2-D — TCP avançado e robustez

- RACK-TLP, F-RTO e TCP Fast Open (R11), priorizados pelo benefício comprovado.
- Fuzzing de segmentos e fragmentos, observabilidade e testes de interoperabilidade.
- **Antes de codificar:** verificar pré-requisitos de timers, SACK scoreboard, contabilização de ACK/perda e riscos de segurança.
- **Saída:** testes de reordenação, duplicação, perda, timeout, recuperação e interoperabilidade.

## 5. Cuidados técnicos para evitar retrabalho

- **SACK/D-SACK, PRR e ECN têm implementações no AROSTCP.** A leitura de `netinet/tcp_subr.c` mostrou `tcp_do_sack=1`, `tcp_do_prr=0` e `tcp_do_ecn=0`. Implementado não significa habilitado, correto ou interoperável. Investigar os defaults antes de mudá-los.
- **CUBIC e NewReno existem.** HyStart++ é extensão, não substituição do controle de congestionamento.
- **PMTUD não deve ser declarado ausente em bloco.** Auditar primeiro o tratamento atual de MTU e ICMP.
- **RACK-TLP tem dependências reais.** Não iniciar refatoração grande sem plano de timers e testes A/B.
- **Fast Open é opcional para Matter**, cujo transporte operacional usa principalmente UDP/IPv6.
- RFC 6724 de seleção de origem no kernel, ordenação de `getaddrinfo` e Happy Eyeballs são trabalhos distintos.
- O stackprobe local registrou 173 pass, 14 fail, 21 unsupported e 5 skip em 2026-10-30; resultados dependem da correção do porte e de confirmar a API.

## 6. Autonomia do agente e limites

O agente pode **propor** antecipação, adiamento, divisão, descarte ou nova ordem com base na realidade do desenvolvimento. Para cada proposta registrar: revisão upstream e arquivos analisados; estado implementado/habilitado/testado/ausente/inconclusivo; evidência reproduzível; riscos em IPv4/IPv6/LP64/68k; dependências; custo relativo; e motivo da prioridade.

Dentro de uma frente **já autorizada**, pode ajustar a sequência de pequenas entregas, documentando a decisão. **Não pode**, sem aprovação do mantenedor, mudar prioridades das issues ativas, iniciar refatoração transversal, alterar ABI pública, ativar globalmente PRR/ECN ou alterar os marcos Matter.

## 7. Qualidade, upstream e encerramento

- Mudanças genéricas AROS, sem dependências específicas de Matter.
- Cada PR deve ter comportamento coeso, teste CUnit upstream que falha antes e passa depois, e validação hosted/TAP/peer Linux quando aplicável.
- Validar **as duas execuções** da suíte CUnit, conforme a lição do #1950.
- Atualizar `workbench/network/stacks/AROSTCP/bsdsocket/Readme.md` junto com mudanças de API/comportamento.
- Fixar revisão das fontes, registrar compatibilidade de licença e separar fatos medidos de hipóteses.
- Seguir diretriz existente: commits e PRs upstream sem assinatura de agentes.
- “Concluído” requer evidência e testes, não apenas build ou PR aberto.

**Primeira ação após ativação:** produzir matriz de reconciliação com o backlog vigente e o upstream, não começar imediatamente uma implementação. Evidências recentes prevalecem sobre a ordem sugerida neste documento.
