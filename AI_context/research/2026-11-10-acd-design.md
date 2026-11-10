# Grupo 11 P3 — detecção de IPv4 duplicado (RFC 5227) — desenho (2026-11-10)

## Decisão do usuário

**RFC estrita** (2026-11-10): um endereço IPv4 configurado (estático ou DHCP) fica tentativo até a sonda
terminar (≈3–7 s com as constantes da RFC), como o IPv6 com DAD. Conflito → `IN_IFF_DUPLICATED`, não usado,
log + sinal. Sysctl para desligar.

## Modelo: NetBSD (não FreeBSD)

A auditoria (2026-11-09-ipv4-parity-audit.md, P3) dizia "como o FreeBSD `IN_IFF_TENTATIVE/DUPLICATED`": **errado**.
O FreeBSD só manda ARP gratuito ao configurar (`garp_rexmit`) e loga "is using my IP address". Quem tem
RFC 5227 no kernel é o **NetBSD** (desde o 7): `sys/netinet/if_arp.c` `arp_dad_*`, `in_var.h`
`IN_IFF_TENTATIVE 0x01 / DUPLICATED 0x02 / DETACHED 0x04 / TRYTENTATIVE 0x08`, `IN_IFF_NOTREADY`,
`SIOCGIFAFLAG_IN _IOWR('i', 39, struct ifreq)` (`ifru_addrflags`), sysctl `net.inet.ip.dad_count`
(padrão `PROBE_NUM` = 3; 0 desliga). Seguimos o NetBSD como o IPv6 seguiu o KAME. Cópia do código lido em
scratchpad (não versionado).

## Peças (AROS)

1. **Estado por endereço:** `ia4_flags` e `ia_dad_defended` em `struct in_ifaddr`; `IN_IFF_*` em
   `<netinet/in_var.h>` com os valores do NetBSD.
2. **Início:** ao configurar um endereço (`in_ifinit()`, `SIOCAIFADDR`/`SIOCSIFADDR`) numa interface com ARP
   (`sana_softc` com tabela ARP; não loopback, não ponto a ponto) e `ip_dad_count > 0`: `TENTATIVE` e
   `arp_dad_start()`. O endereço do autoip (169.254, já sondado pela RFC 3927) não repete.
3. **Máquina (port do NetBSD):** espera aleatória < `PROBE_WAIT` (1 s); `dad_count` sondas (remetente
   0.0.0.0) espaçadas `PROBE_MIN`..`PROBE_MAX` (1–2 s); `ANNOUNCE_WAIT` (2 s); tira `TENTATIVE`, `RTM_NEWADDR` +
   `SBTC_SIG_ADDRESS_CHANGE_MASK` (como `nd6_dad_announce()`); `ANNOUNCE_NUM` (2) anúncios a
   `ANNOUNCE_INTERVAL` (2 s). Relógio: timeout próprio de 100 ms em `amiga_time.c` (as esperas são frações
   de segundo).
4. **Conflito (`in_arpinput()`):** remetente = nosso endereço (de outro MAC) → duplicado; alvo = nosso
   endereço com remetente 0.0.0.0, broadcast, e o nosso tentativo/duplicado → duplicado (sonda simultânea).
   Tentativo → `DUPLICATED`. Já em uso → defesa uma vez por `DEFEND_INTERVAL` (10 s, anúncio); segunda em
   10 s → `DUPLICATED` (RFC 5227 §2.4 b). Log com o MAC; `RTM_NEWADDR` + sinal.
5. **Não usar o que não está pronto (`IN_IFF_NOTREADY`):** escolha de origem (`in_pcbconnect`/`ip_output`)
   pula; `bind()` a duplicado → `EADDRNOTAVAIL` (NetBSD `in_pcb.c`); a entrada não aceita para tentativo
   (NetBSD `ip_input`); ARP não responde por tentativo/duplicado.
6. **Consulta:** `SIOCGIFAFLAG_IN` (`ifru_addrflags`); `ifconfig` mostra `tentative`/`duplicated`.
7. **Sysctl:** `net.inet.ip.dad_count` (`IPCTL_DAD_COUNT` 5; 0 = desligado, comportamento antigo).
8. **Readme** §6.x e teste.

## Também (mesmo grupo)

- **B16 (autoip, RFC 3927 §2.5):** no estado `AUTOIP_DEFEND`, um segundo conflito é ignorado (só `BOUND`
  reage) → o endereço nunca é abandonado. Commit próprio.
- Fora do escopo (anotar): `dhclient` deveria mandar DHCPDECLINE para um endereço duplicado (RFC 2131 §3.1.5;
  o ARPCHECK do script é no-op); DAD de novo quando o link volta (NetBSD `DETACHED`).

## Testes

- `cunit-net-acd` (tap): endereço livre fica `TENTATIVE` na hora e pronto em ≤ 8 s; `bind()`/origem
  enquanto tentativo; o endereço do host (192.168.166.1, que o Linux defende respondendo à sonda) vira
  `DUPLICATED`; `dad_count` 0 = sem sonda; `SIOCGIFAFLAG_IN` de endereço inexistente → `EADDRNOTAVAIL`.
- Bench `tests/ipv4/acd_probe.py`: um "intruso" (raw socket no host) usa o endereço já em uso → defesa uma
  vez, segunda em 10 s → duplicado; e o autoip (B16).
