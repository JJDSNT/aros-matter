# Auditoria inicial por leitura de código — 2026-10-28

Leitura de código apenas. Nada aqui foi executado no AROS; todo item é "no código, não testado".

## Revisões examinadas

| Repositório | Revisão | Data |
|---|---|---|
| aros-development-team/AROS | `cbca98214fd4fd3a87917cda14ff597f4134e328` | 2026-10-28 |
| project-chip/connectedhomeip | `8fd0af079246c6bfddcedcafc12a74f5f8f8cbab` | 2026-10-28 |

Reproduzir (clone esparso, sem submódulos):

```bash
git clone --depth 1 --filter=blob:none --sparse https://github.com/aros-development-team/AROS aros
git -C aros sparse-checkout set workbench/network workbench/libs/mbedtls rom/entropy
git clone --depth 1 --filter=blob:none --sparse https://github.com/project-chip/connectedhomeip chip
git -C chip sparse-checkout set --no-cone src/platform/ src/crypto/ src/inet/ src/system/ src/lib/dnssd/ src/protocols/secure_channel/ build/config/compiler/
```

## AROS

### IPv6 no AROSTCP — presente upstream
- `workbench/network/stacks/AROSTCP/bsdsocket/netinet6/`: `ip6_input/output`, `udp6_usrreq.c`, `mld6.c`, `nd6*.c`, `icmp6.c`.
- `netinet6/in6_proto.c`: `IPV6_V6ONLY`, `IPV6_RECVPKTINFO`, `IPV6_MULTICAST_IF`, `IPV6_JOIN_GROUP`.
- `udp6_usrreq.c`: ancillary `IPV6_PKTINFO` (RFC 3542) no envio e na recepção.
- `api/getifaddrs.c` existe (enumeração de interfaces).
- Histórico relevante (no AROS-net local): dual-stack com endereços IPv4-mapped (`210688707b`), separação de sockets v4/v6 (`01d871b12d`), correção de crash com RA IPv6 (`603a3755e4`).
- `kern/uipc_socket.c`, `netinet6/in6_pcb.c`: `SO_REUSEPORT` / `SO_REUSEADDR` tratados.

### mdnsd / bonami.library (mantenedor: jaime)
- `workbench/network/mdns/README.md` §Limits: **"IPv4 only: no AAAA record, and nothing is sent to ff02::fb"**.
- `DISCOVERY.md`: browse IPv4 com resolução automática de instâncias, `ResolveService`, `LookupHostA()` (IPv4), `QueryRecordA()` genérico, fila de eventos. Hooks/callbacks deliberadamente indisponíveis.
- Bonami v41.3, IPC privado v4. Nome de instância ≤63 bytes, TXT ≤256 caracteres.
- `mdns_net.c:103-106`: `SO_REUSEADDR` + `SO_REUSEPORT` na 5353.
- Subtipos DNS-SD (`_L1234._sub._matterc._udp`): nenhuma menção encontrada no código; a confirmar.

### mbedTLS
- `workbench/libs/mbedtls`: mbedTLS **3.6.7** (ver `docs/architecture-and-research.md` §3).

## connectedhomeip

### Crypto
- Backends PAL: `CHIPCryptoPALmbedTLS.cpp`, `CHIPCryptoPALPSA.cpp` (+ `PSASpake2p.cpp`), `CHIPCryptoPALOpenSSL.cpp`.
- SPAKE2+: `class Spake2p_P256_SHA256_HKDF_HMAC` (`CHIPCryptoPAL.h:1617`). No backend mbedTLS a aritmética é feita sobre `mbedtls_ecp_*`/`mbedtls_mpi_*` (127 ocorrências). **Não usa PSA PAKE nem EC J-PAKE.**
- Submódulo `third_party/mbedtls/repo` → `6a58fa8122c9…`, commit "Merge pull request #1331 … mbedtls-2.28.10_mergeback" (linha 2.28 LTS).
- O código já tem guardas `MBEDTLS_VERSION_NUMBER >= 0x04000000`, ou seja, compila contra mais de uma versão principal. A 3.6 precisa de verificação.

### Toolchain
- `build/config/compiler/compiler.gni:47-49`: `cpp_standard = gnu++20` ou `gnu++17`. **C++17 é o mínimo.**

### Sistema / rede / descoberta
- `src/system/SystemLayerImplSelect.cpp`: event loop baseado em `select()`, que é o candidato natural sobre bsdsocket `WaitSelect()`.
- `src/inet`: `INET_CONFIG_ENABLE_IPV4` é configurável; `UDPEndPointImplSockets.cpp:199-203` usa `SO_REUSEADDR` + `SO_REUSEPORT`.
- `src/lib/dnssd/`: `minimal_mdns/` (implementação própria do SDK sobre UDP) **ou** `Discovery_ImplPlatform.cpp` (delegação a um DNS-SD da plataforma).
- Plataformas existentes que servem de molde: `Linux`, `NuttX`, `Zephyr`, `FreeRTOS`, `fake`.

## Toolchains AROS locais
- `~/AROS/config/gcc_def`: **6.5.0** (padrão). `arch/x86_64-all/gcc_def`: **10.5.0**. `arch/riscv*-all/gcc_def`: 16.2.0.
- `~/aros-build-emu68-m68k/.../m68k-aros-g++ -dumpversion`: 6.5.0.
- GCC 6.5 não cobre C++17 nem a libstdc++ correspondente (`<optional>`, `<variant>` completos chegam no GCC 7). Na prática, o primeiro alvo viável é **x86_64 (GCC 10.5)**.
