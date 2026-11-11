# Custo da modernização do AROSTCP no Amiga clássico (m68k) — medição e plano (2026-11-11)

Pedido do usuário: medir quanto a modernização custa em relação à pilha anterior (`.text`, `.data`, `.bss`,
memória dinâmica em repouso e sob carga, recursos opcionais por perfil) e decidir se o m68k precisa de build
próprio. Preocupação central: o Amiga clássico.

## Pontos comparados

| | commit | versão |
|---|---|---|
| **Inicial** (antes do nosso primeiro commit, `61d60f50aa`) | `7f2f06384e` | 5.11 (09.10.2026) |
| **Atual** | master `994fc8c9df` | 5.44 |
| Deltas pendentes | B5 `11df4517ea`, G11 `ad99a0e13d` | — |

O total inclui commits do Kal intercalados com os nossos depois de 11/10 (não separados por autor). O AROSTCP
clássico 4.59 (`704127a130`) fica só como referência opcional (decisão do usuário: legado = antes das nossas
modernizações).

## Resultado

**Binário (m68k, `m68k-aros-size`):**

| | inicial | atual | diferença |
|---|---|---|---|
| `.text` | 232.472 | 268.906 | +36.434 (+16%) |
| `.data` | 3.580 | 3.796 | +216 |
| `.bss` | 50.660 | 89.300 | +38.640 (+76%) |
| total | 286.712 | 362.002 | +75.290 (+26%) |

- **Metade é memória morta (B27):** o array `tcp_debug[100]` (cópia do `tcpcb` por entrada; nunca usado sem
  `TCPDEBUG`) foi de 34.200 a 72.000 bytes. Com ele sob `TCPDEBUG`, o atual dá 289.762 (+3.050 sobre o inicial,
  que ainda tem os seus 34.200 mortos). Crescimento real, os dois corrigidos: ~+37 KB, quase todo código.
- Por subsistema (texto+dados+bss): netinet +51 KB (TCP +13,5 KB de código; resto é o `tcp_debug`), netinet6
  +13 KB, api +4 KB, kern +4 KB, net +2 KB.
- Por conexão TCP: `tcpcb` 288 → 666 bytes (+378); `socket` e `inpcb` iguais.
- Deltas pendentes: B5 +1.420, G11 +3.316.
- Perfil `INET6=0` (atual): −57.726 (−49.602 código, −7.628 bss) — maior que todo o crescimento real. Hoje não
  compila (B28).

**Memória (Amiga emulado: Amiberry 8.5, A3000, 68030, 2 MB chip + 16 MB fast, A2065 com o `a2065.device` da
Commodore na tap `aros0`; `tests/stack/memcost.py --amiga`; carga: 4 conexões TCP de 1 MB recebendo):**

| | inicial | atual | diferença |
|---|---|---|---|
| repouso (binário + o que a pilha aloca) | 637 KB | 716 KB | +79 KB |
| pico sob carga | 1.144 KB | 1.225–1.229 KB | +81–85 KB |
| depois da carga (pool de mbufs retido) | 775 KB | 862 KB | +87 KB |

Quase tudo é o binário (+73,5 KB); a memória que a pilha aloca cresceu só ~5–14 KB. Atual: 2 execuções iguais;
inicial: 1 execução (repetições em andamento quando isto foi escrito). Só TCP (o UDP não abre no m68k, B31) e só
memória (o emulador roda a CPU em velocidade máxima).

## Conclusão

**Sem build próprio do m68k nem modularização agora.** Com o B27 corrigido o impacto é aceitável (~+37 KB de
código, <2% de uma máquina de 2 MB de fast). O risco que se repete não é tamanho, é **padrão dimensionado para
máquina grande sem nada que o ligue ao que a máquina oferece**: `tcp_debug` (B27), `udp_recvspace` (B31), os tetos
do autosizing antes de ligados a `AvailMem()` (#2194).

## Plano

1. **B27 — `tcp_debug` sob `TCPDEBUG`.** Maior ganho (72 KB no m68k), menor esforço. PR próprio quando chegar a
   vez (um PR do AROSTCP por vez).
2. **B28 — perfil `INET6=0` compilando.** Guardar `in6p_v6only` em `in_pcb.c` (2 lugares) e o uso de
   `inet6_aton()` em `amiga_netdb.c`. `INET6` fica opção de compilação que funciona (padrão: ligado), não build
   separado do m68k. Junto com o B27 ou logo depois.
3. **Regra: padrões ligados à máquina.** Todo tamanho de buffer, pool ou tabela respeita o que a máquina pode dar
   (`SB_MAX`/`sbreserve`, `AvailMem()`), em vez de constante para máquina grande. **Auditoria** dos valores fixos
   da pilha com essa regra (sockbufs por protocolo, filas de entrada, tabelas de hash e caches, pools,
   `nd6_maxnbrs`, `maxnipq`, mbufs), cada achado medido no m68k.
4. **B31 — UDP no m68k (`udp_recvspace`).** O Kal está corrigindo. **Se ele não levar ao upstream**, fazer a
   correção desenhada aqui: auxiliar em `uipc_socket2.c` com o maior buffer que `sbreserve()` concede sob um limite
   (o `sb_max_adj` do FreeBSD), e o `PRU_ATTACH` do UDP4 e do UDP6 reservando `MIN(udp_recvspace, esse limite)`.
   x86_64 inalterado (266 KB cabem em 512 KB); m68k ~58 KB (~56 datagramas de 1 KB, mais que os 40 do 4.4BSD);
   `SO_RCVBUF` acima do limite continua recusado. Teste: `udpdiag` no Amiga emulado (UDP4/UDP6/TCP4/TCP6 abrem),
   DNS e DHCP no emulador, `cunit-net-udp`/`udpio` no hosted. Acompanhar o PR/commit do Kal antes.
5. **B30 — dependência de build:** o alvo `workbench-network-stacks-arostcp` não depende da `fd.library`
   (`proto/fd.h`); de um build limpo falha até `workbench-libs-fd`. Corrigir no mmakefile (pequeno, da nossa área).
6. **Medir sempre.** Linha de base registrada (acima); cada PR do AROSTCP anota o delta no m68k
   (`tools/stack-size-hist.sh` + `tools/stack-size-report.py`) e, quando mexer em estruturas por conexão ou pools,
   o `memcost --amiga`.
7. **Opcional (se o usuário quiser):** custo de CPU num 68000/68030 (Amiberry em modo exato de ciclos); medir os
   outros recursos opcionais (BPF, filtro de pacotes, sysctl, gerente de serviços, API Roadshow) antes de propor
   perfis para eles — pelos tamanhos dos módulos, poucos KB cada.

## Observações do ambiente m68k (não da pilha)

- Não há driver SANA-II de placa Amiga na árvore da AROS (só PCI); o `a2065.device` da Commodore (Aminet
  `dev/misc/SANA`) funciona na AROS m68k.
- O build completo do m68k para na `egl.library` e não faz as bibliotecas seguintes (`locale.library`): construir
  alvos individuais.
- O carregador ELF da AROS recusa símbolos COMMON ("file is not executable"); o GCC 6.5 do m68k os gera por
  padrão — benches m68k com `-fno-common`.
- Headers gerados ausentes em build paralelo (`-j8`), sumiram ao repetir, causa não investigada:
  `proto/security.h` (`rom/dos/dos_intern.h`), `interface/Hidd.h` (`hidd/hidd.h`), `partition_support.h`
  (`arch/m68k-amiga/partition`).
- Hosted x86_64 com o perfil de mbuf do m68k trava na partida (B29), não investigado.

## Ferramentas (aros-matter)

- `tools/amiga-run.sh` — AROS m68k no Amiberry (A3000/68030, A2065 em `aros0`, disco = diretório do host,
  captura de tela se não terminar). Sistema: `~/aros-build-hist-m68k` (worktree `~/AROS-hist`, master; submódulos
  inicializados). Emulador: `~/emu/amiberry-dl` (AppImage 8.5.0 extraída); drivers: `~/emu/drivers`.
- `tools/stack-size-hist.sh` — AROSTCP m68k de cada commit (diretório `workbench/network` limpo antes do checkout;
  headers da versão no SDK; `net/bpf.h` público escondido para versões que não o tinham).
- `tools/stack-size-report.py` — seções, subsistemas, objetos e símbolos que mais cresceram entre dois builds.
- `tests/stack/memcost.py` (`--amiga`), `tests/stack/memsnap.c`.
- Resultados: `tests/stack/out/hist/` (binários e objetos por commit), `tests/stack/out/cmp-*` (memória).
