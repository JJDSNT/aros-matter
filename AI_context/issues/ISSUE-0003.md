---
id: ISSUE-0003
title: "Backend crypto: SDK × mbedTLS 3.6.7 do AROS"
status: ready
priority: high
type: research
owner: jaime
milestone: M1
area: crypto
created_at: 2026-10-28
updated_at: 2026-10-28
tags: [crypto, spake2p, mbedtls]
blockers: []
depends_on: [ISSUE-0002]
upstream_refs: [connectedhomeip src/crypto/CHIPCryptoPALmbedTLS.cpp, connectedhomeip src/crypto/CHIPCryptoPAL.h:1617, connectedhomeip third_party/mbedtls/repo@6a58fa8122, AROS workbench/libs/mbedtls]
related_files: []
---

# Por quê

PASE (M3) depende de SPAKE2+; CASE (M4), de ECDSA P-256, ECDH, HKDF, AES-CCM e X.509. No backend mbedTLS do SDK, o SPAKE2+ é montado sobre `mbedtls_ecp_*`/`mbedtls_mpi_*` (e não sobre PSA PAKE nem EC J-PAKE). O SDK fixa o mbedTLS 2.28, e o AROS embarca 3.6.7.

# O quê

Decidir entre: (a) `CHIPCryptoPALmbedTLS` contra o mbedTLS 3.6.7 do AROS; (b) `CHIPCryptoPALPSA` + `PSASpake2p`; (c) o mbedTLS do submódulo do SDK, linkado estaticamente. Fica de fora implementar qualquer primitiva.

# Passos de validação

- [ ] Listar as funções/macros `MBEDTLS_*` que o PAL exige → diff contra `mbedtls_aros_config.h`
- [ ] Verificar se o SDK compila o PAL mbedTLS contra a 3.6 (CI do SDK, guardas `MBEDTLS_VERSION_NUMBER`) → referência
- [ ] Compilar e rodar no host Linux os testes de crypto do SDK (`src/crypto/tests`, vetores SPAKE2+) contra a 3.6.7 → log
- [ ] Repetir no AROS (alvo de ISSUE-0002) → log
- [ ] Avaliar a configuração: usar a biblioteca do sistema exige mudar `mbedtls_aros_config.h` upstream? Isso é aceitável upstream?

# Critério de sucesso / falha

- Sucesso se: os vetores SPAKE2+, P-256, HKDF e AES-CCM do SDK passam no AROS com o backend escolhido.
- Falha se: a 3.6.7 exigir patch no PAL que não seja aceitável upstream; nesse caso, cair para (c) e documentar.

# Decisões tomadas

# Log

- 2026-10-28: criada.
