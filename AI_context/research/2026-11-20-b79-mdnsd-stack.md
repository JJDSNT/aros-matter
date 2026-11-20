# B79 — pilha do mdnsd no m68k: análise (2026-11-20)

Só análise; a implementação espera o merge do #2307 (decisão do usuário). Árvore medida: ramo do #2307
(`review/mdnsd-publication` `7b9fc0d541`); os frames são iguais no master. m68k-aros-gcc 6.5, `-Os -march=68000`,
`-fstack-usage`; chamadas lidas do `objdump -dr` dos objetos (`tests`/scripts: scratchpad `b79/stackchain.py`).

## 1. Profundidade das cadeias

Só chamadas diretas. Não entram: as chamadas ao sistema (`jsr -N(a6)`: exec, dos, bsdsocket, timer) e as chamadas
por ponteiro (`jsr (aN)`), que somam por cima.

Com o inlining do build (como o binário é):

| frame | função |
|---|---|
| 292 | `main` |
| 1964 | `dnssdServerMessage` (com `start_register` em linha) |
| 1516 | `mdnsRegUpdateRef` |
| 584 | `mdnsReflectPacket` |
| 344 | `mdnsCacheRecord` |
| 24 + 40 | `drop`, `tell` |
| **4764** | total |

**As duas funções estão na mesma cadeia** (atualização de registro: `dnssdServerMessage` → `mdnsRegUpdateRef`).
Sem inlining (`-fno-inline`) a mesma cadeia dá **3040 B**: o frame próprio do `dnssdServerMessage` é 264 B; os
1964 vêm do `start_register()` (1932 B) posto em linha, cujo `reg` ocupa o frame também no caminho da atualização,
onde não é usado.

Pilha do mdnsd: 16 KB (sem `NP_StackSize`, nota do Kal no #2264). 4764 B diretos cabem; falta medir o uso real
com as chamadas ao sistema e por ponteiro.

## 2. O que ocupa os frames

`struct dnssd_reg` = **1358 B** no m68k (`dnssd_reg.h`: `instance`, `type[255]`, `domain[255]`, `subtypes[N][63]`,
`host`, 8 endereços...).

| função | frame | conteúdo |
|---|---|---|
| `start_register` (`dnssd_server.c`) | 1932 | `struct dnssd_reg reg` 1358 + `UBYTE type[256]` + 8 `dnssd_model_wire_address` (192) + `dnssd_reg_parts` (54) |
| `mdnsRegUpdateRef` (`mdns_reg.c`) | 1476 | `struct dnssd_reg check` 1358 (cópia para validar a atualização) + `dnssd_reg_parts` |

No caminho da atualização, com o inlining, ficam duas `dnssd_reg` na pilha ao mesmo tempo (`reg` sem uso e `check`).

## 3. Reduções possíveis, sem `static`

1. `start_register()` fora de linha (`__attribute__((noinline))`, ou separar o caminho do registro): −1724 B na
   cadeia da atualização; sem BSS, sem questão de reentrância; o registro em si continua com 1932 B, mas fora da
   cadeia da atualização.
2. `mdnsRegUpdateRef()` validar sem a cópia inteira da `dnssd_reg` (conferir as partes que mudam contra
   `rs->rs_Reg`, ou montar a nova direto no armazenamento do registro depois de validada): −~1358 B.
3. `start_register()`: `type[256]` e os endereços podem ir direto para a `reg` (hoje são cópias intermediárias).

`static` fica fora (usuário): ciclo de vida e chamadas aninhadas do daemon. As três acima não mudam ciclo de vida.

## 4. Falta (no PR)

- Medir o uso real no m68k: encher a pilha da task do mdnsd com um padrão no início, rodar a carga (registro,
  atualização, browse, conflito) e ler a marca d'água; antes e depois.
- Conferir as cadeias que passam por chamadas por ponteiro (`ptr` > 0: `dnssdServerMessage` 14, `main` 5).
