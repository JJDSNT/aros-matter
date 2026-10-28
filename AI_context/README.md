# AI_context — aros-matter

## Propósito

Memória operacional do projeto: o que está em andamento, **por quê**, **o quê** e **qual evidência** fecha cada item.

- `README.md` e `docs/` (raiz do repo) descrevem escopo, arquitetura e critérios dos marcos — o que é verdade **agora**.
- `AI_context/` rastreia o **trabalho em andamento**, as descobertas e o que foi validado ou descartado.

Ponto de partida de qualquer sessão: [`current_state.md`](current_state.md).

## Fluxo

```text
Pergunta / lacuna
 ↓
Issue (por quê, o quê, critério de sucesso definido ANTES)
 ↓
Investigação ou spike → evidências em research/ (com revisão upstream fixada)
 ↓
Revisão: critério atingido? bloqueado? refutado?
 ↓
Consolidação (consolidated/) + atualização de docs/ e current_state.md
```

> Uma hipótese refutada (ex.: "o toolchain X compila o SDK") também é resultado. Consolida-se com o motivo, não se apaga.

## Estrutura

- `current_state.md`: retrato curto do projeto, revisões fixadas, achados e próximos passos.
- `issues/`: trabalho ativo. Documentos vivos, editáveis por agentes.
- `research/`: notas de evidência (trechos de código, comandos, saídas) referenciadas pelas issues.
- `consolidated/`: conhecimento estabilizado. `consolidated/history/` guarda issues encerradas.
- `templates/`: modelos de issue e de documento consolidado.

## Status

`backlog`, `ready`, `doing`, `review`, `done`, `consolidated`, `blocked`

## Prioridades

`low`, `medium`, `high`, `critical`

## Tipos

| Tipo | Uso |
|---|---|
| `audit` | verificar uma capacidade da plataforma AROS com evidência (linha da matriz M0) |
| `research` | levantar informação ou tomar uma decisão de arquitetura |
| `spike` | experimento descartável de build/integração |
| `feature` | código deste repositório |
| `upstream` | mudança genérica no AROS (PR separado, sem acoplamento Matter) |
| `external` | dependência de trabalho fora deste repo (ex.: IPv6 no mdnsd) |
| `infra` | bancada de testes, toolchains, acessório de referência |
| `bug` | algo que não funciona como deveria |
| `docs` | documentação |

## Campos específicos

```yaml
milestone: M0          # M0..M6 (ver docs/architecture-and-research.md §6), ou "none"
area: crypto           # network | dnssd | crypto | build | storage | system | controller | testbed
upstream_refs: []      # commits/arquivos AROS ou connectedhomeip que embasam a issue
```

## Visão rápida do estado

```bash
for f in AI_context/issues/ISSUE-*.md; do
  head -16 "$f" | grep -E "^(id|title|status|priority|milestone):"; echo
done
```

Issues com bloqueio:

```bash
grep -L "^blockers: \[\]" AI_context/issues/ISSUE-*.md | xargs grep -A3 "^blockers:"
```

## Numeração

`ISSUE-0001`, `ISSUE-0002`… sequencial, nunca reutilizado.

```bash
ls AI_context/issues AI_context/consolidated/history | grep -o 'ISSUE-[0-9]*' | sort | tail -1
```

## Regras para agentes

- Nunca afirmar que algo funciona no AROS sem teste; leitura de código vira "suportado no código, não testado".
- Toda evidência de código cita a revisão upstream (SHA) e o caminho do arquivo.
- Não começar port amplo do SDK antes de fechar M0 e a escolha de toolchain/crypto (ISSUE-0002, ISSUE-0003).
- Bonami/mdnsd e IPv6 no mdnsd são do mantenedor (jaime); aqui se registram requisitos, não se implementa.
- **Upstream AROS sem assinatura do Claude Code:** commits e PRs contra `aros-development-team/AROS` não levam `Co-Authored-By: Claude…`, `Claude-Session:` nem "Generated with Claude Code". Vale para a branch `arostcp-ipv6` e qualquer outra branch destinada ao upstream.
- Antes de propor desenho para o AROSTCP, seguir as convenções já documentadas no próprio código (`workbench/network/stacks/AROSTCP/bsdsocket/Readme.md`) e atualizar esse Readme junto com a mudança.
- Implementações corretas e completas por área, baseadas em pesquisa (RFCs, pilhas de referência); nada de correção pontual de sintoma.
- Cada PR para o AROS leva junto um teste no padrão do upstream (CUnit em `developer/debug/test/...`, preparado em `tests/upstream/` com os mesmos caminhos), que falha antes da mudança e passa depois.
