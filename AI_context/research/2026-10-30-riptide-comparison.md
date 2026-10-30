# Riptide × AROSTCP: o que ainda falta no AROS (2026-10-30)

Fonte: https://github.com/farsonic/Riptide (Riptide 0.24, GPL-2.0-only, pilha TCP/IP nova para AmigaOS 3.x, projeto hobby, 9 estrelas). Documentos lidos: `README.md`, `docs/COMPARISON.md` (compara só com MiamiDx e Roadshow), `docs/stackprobe/RESULTS.md`. Os números deles são medidos em emulador pelo próprio autor.

**Licença:** o Riptide é GPL-2.0; o AROS é APL. Nada do código dele entra no AROS. Serve como referência de desenho e de lista de funcionalidades; a implementação é nossa. O porte local do `stackprobe` (abaixo) fica fora de qualquer repositório.

Legenda: ✔ conferido no código do AROSTCP (master `1fef6c415e`+); ? a conferir.

## O que o AROSTCP já tem (para não reinventar)

- ✔ TCP: CUBIC (padrão) e NewReno, SACK e D-SACK (`tcp_sack_insert`, `t_dsack_blks`), PRR, ECN, timestamps/PAWS, IW10, SYN cache + SYN cookies, ISN com hash dos 4 campos + segredo (`tcp_secret_key`, estilo RFC 6528).
- ✔ DNS: ID aleatório (`res_randomid`) e porta de origem reaberta a cada consulta.
- ✔ IPv6 (desta série): ancillary data (#1947), raw IPv6 (#1971), zonas (#1974), RFC 4191 (#1976), RFC 4941 temporários, DHCPv6 (`dhclient6`).
- ✔ O que o Riptide não tem: filtro de pacotes (`ipfilter.c`), API BPF, encaminhamento IPv4, túnel 6in4 (`if_stf.c`), SMP-safe.

## Lacunas, por prioridade

### 1. Barato, segurança (bons PRs)
- **R1 — Portas efêmeras previsíveis.** ✔ Sequenciais em `IPPORT_RESERVED..IPPORT_USERRESERVED` (1024–5000) em `in_pcb.c` e `in6_pcballoclport()`: previsíveis e esgotam com ~4 mil conexões. Correto: RFC 6056 (aleatórias, 49152–65535).
- **R2 — RFC 5961.** ✔ Sem challenge ACK contra injeção cega de RST/SYN (nenhuma ocorrência de "challenge"/5961).
- **R3 — Keepalive por socket.** ✔ Existem `TCP_KEEPINTVL`/`TCP_KEEPCNT`; faltam `TCP_KEEPIDLE` e `TCP_USER_TIMEOUT`.

### 2. IPv6 de host (relevante para Matter)
- **R4 — RDNSS/DNSSL (RFC 8106).** ✔ `nd6_ra_input()` trata só SLLAO, PIO, MTU e RIO: numa rede só IPv6 o AROS fica sem DNS.
- **R5 — IID estável (RFC 7217).** ✔ Link-local e SLAAC usam EUI-64 (`in6_if_up()`, `nd6_prefix_slaac()`): expõe o MAC.
- **R6 — `getaddrinfo()` com RFC 6724 e Happy Eyeballs (RFC 8305).** ? Não conferido como o AROS ordena hoje.

### 3. Serviços
- **R7 — Cliente SNTP.** ? Nada na pilha; conferir se o AROS tem ferramenta à parte. **Importa para Matter:** o comissionamento valida certificados e precisa de relógio certo.
- **R8 — mDNS IPv6** (trabalho futuro do mantenedor no mdnsd; ISSUE-0005).
- R9 — VLAN 802.1Q, QoS/DSCP por regras, `sendmmsg`/`recvmmsg`: baixa prioridade.

### 4. TCP moderno (ganho grande, mudança grande)
- **R10 — Timers.** ✔ 200/500 ms (Readme §5.3), RTO mínimo ~1 s. Timers em ms com RFC 6298 (RTO mín. 200 ms) seria a mudança de maior efeito.
- R11 — RACK-TLP, F-RTO, HyStart++, PLPMTUD (RFC 4821/8899, rotas que filtram ICMP), TCP Fast Open: ✔ ausentes. O Matter usa principalmente UDP; por último.

## Metodologia a aproveitar
- **stackprobe** (~215 testes de comportamento da API `bsdsocket`, só pela interface pública, JSON/CSV): portar para o AROS hosted, **só para uso local** (GPL), e rodar contra o AROSTCP para uma lista objetiva de lacunas. Status: ver `current_state.md`.
- **Fuzzing de entrada** (segmentos e fragmentos aleatórios): o crash por fragmento IPv4 em 64 bits e o UAF da ISSUE-0009 são o tipo de defeito que ele acha antes.
