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

## stackprobe contra o AROSTCP (2026-10-30, master `be237767fa`, hosted x86-64)

Porte local em `~/aros-local/stackprobe` (fora de qualquer repositório, GPL). O porte exigiu: chamadas pelo número do vetor (`AROS_LCn`), layouts de 64 bits (tag lists em `IPTR`, `iovec`, `netent`, `addrinfo`), constantes do AROS e **ordem de bytes** (o stackprobe supõe host big-endian). Os primeiros resultados (trap, 36 FAILs) eram artefatos do porte, não do AROS: o resultado só vale depois de conferido.

**Resultado:** 173 passaram, 14 falharam, 21 "não suportado", 5 pulados (precisam de par na rede).

| Item | Classificação | Evidência |
|---|---|---|
| **S1 — `localhost` não resolve** (`gethostbyname`, `gethostbyaddr(127.0.0.1)`, `gethostbyname2(AF_INET6)`, `getaddrinfo("localhost")`) | ✔ real (configuração) | `Env/db/hosts` padrão só tem comentários. Correção: `localhost` para `127.0.0.1`/`::1` no `hosts`, ou nome especial no resolvedor (RFC 6761 §6.3) |
| **S2 — `servent.s_port` na ordem do host** | ✔ real (portabilidade em LE) | `amiga_netdb.c` guarda o número lido; `getservbyport()` compara direto. BSD/POSIX: ordem da rede. Mudar pode quebrar programas AROS que já compensam: decisão de compatibilidade (Kal) |
| S3 — `MSG_DONTWAIT` bloqueia | ? a conferir | ausente dos headers públicos; ver se o kernel trata 0x80 |
| S4 — fechar com dados não lidos não manda RST | ? a conferir | RFC 2525 §2.17 recomenda RST; ver `tcp_usrreq` PRU_DETACH/soclose |
| S5 — `getnetbyaddr(127)` não acha | ? a conferir | `networks` tem `loop 127 loopback`; ver formato esperado do argumento |
| S6 — Roadshow `ObtainInterfaceList`/`QueryInterfaceTagList`/`GetRouteInfo` com `ECONNREFUSED` | ? a conferir | pode ser assinatura/semântica diferente da que o stackprobe supõe |
| S7 — `In_CanForward()` devolve 1 para 8.8.8.8 e 127.0.0.1 | ? a conferir | semântica a definir pela documentação, não pelo stackprobe |
| S8 — `ObtainRoadshowData`/`GetNetworkStatistics` `ENOSYS`; tags `SBTC_HAVE_*` do Roadshow ausentes | ✔ não implementado | stubs (Readme §11) |

**ABI (achados ao portar, a conferir contra o SDK oficial do Roadshow, que não estava acessível — espelho 403):**
- **A1 — família `getaddrinfo` do Roadshow um slot depois:** AROS `freeaddrinfo` 135, `getaddrinfo` 136, `gai_strerror` 137, `getnameinfo` 138 (`ipf_set_interrupt_mask` em 134); stackprobe/Riptide: 134/135/…/137. No porte segui o AROS.
- **A2 — `mbuf_*` trocados aos pares** em relação ao SDK do netstack do MorphOS (Aminet `comm/tcp/MOSNet-SDK`): `mbuf_copydata`/`mbuf_copyback` (105/106) e `mbuf_adj`/`mbuf_cat` (112/113). 90 outras funções casam.
- **A3 — `struct addrinfo` com campos `long` e `ai_addrlen` `size_t`** (POSIX: `int`/`socklen_t`). Não é defeito para programas AROS; registrar como diferença de ABI em 64 bits.
- **A4 — constantes:** `FIO*`/`SIOCATMARK` codificam tamanho 8 em x86-64; `SO_REUSEPORT`, `TCP_MAXSEG`, `MSG_DONTWAIT`, `SO_USELOOPBACK`, `SBTC_COMPAT43` ausentes dos headers públicos; `IPV6_V6ONLY` 26 (G13).
