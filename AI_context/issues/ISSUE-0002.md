---
id: ISSUE-0002
title: "Toolchain C++17 e primeiro alvo AROS"
status: done
priority: critical
type: research
owner: jaime
milestone: M1
area: build
created_at: 2026-10-28
updated_at: 2026-10-28
tags: [toolchain, cxx17]
blockers: []
depends_on: []
upstream_refs: [connectedhomeip build/config/compiler/compiler.gni:47-49, AROS config/gcc_def, AROS arch/x86_64-all/gcc_def]
related_files: []
---

# Por quê

O connectedhomeip usa `gnu++17`/`gnu++20`. O GCC padrão do AROS é 6.5.0, que não cobre C++17 nem a libstdc++ correspondente. Sem toolchain adequada não existe M1.

# O quê

Escolher o primeiro alvo e confirmar que ele compila C++17 com a libstdc++ do AROS. Candidatos:

- x86_64 (GCC 10.5.0): hosted (Linux) ou nativo pc-x86_64 em QEMU.
- riscv (GCC 16.2.0): moderno, mas sem uso prático.
- m68k/aarch64 com GCC 6.5: só se a toolchain for atualizada (fora do escopo).

Fica de fora: atualizar o GCC de outras arquiteturas.

# Passos de validação

- [x] Toolchain x86_64-aros GCC 10.5.0 já existente em `~/aros-midihub/build-aros-linux` (hosted linux-x86_64)
- [x] Compilar um teste C++17 (`<optional>`, `<variant>`, `std::string_view`, `if constexpr`, structured bindings) → binário rodando no AROS
- [x] Verificar `-fno-exceptions -fno-rtti` e `<atomic>`/`<mutex>`/`std::thread`/pthread na libstdc++ AROS
- [ ] (movido para ISSUE-0006) Verificar que o GN do SDK aceita uma toolchain custom (`build/toolchain/`) apontando para o cross-compiler

# Critério de sucesso / falha

- Sucesso se: um programa C++17 que usa os recursos acima roda no AROS x86_64.
- Falha se: a libstdc++ não tiver os headers/símbolos necessários; nesse caso, abrir issue de toolchain upstream.

# Evidências

- `research/2026-10-28-hosted-tests.md` §C++; `research/logs/2026-10-28/cxx17.log`, `mutex-pthread.log`.

# Decisões tomadas

- 2026-10-28: **primeiro alvo = AROS hosted linux-x86_64** (decisão do mantenedor). Critério de sucesso atingido: C++17/20, mutex, pthread e std::thread rodam.

# Log

- 2026-10-28: criada a partir de `research/2026-10-28-initial-desk-audit.md`.
- 2026-10-28: concluída.
