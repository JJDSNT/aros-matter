---
id: ISSUE-0003
title: "Backend crypto: SDK × mbedTLS 3.6.7 do AROS"
status: in-progress
priority: high
type: research
owner: jaime
milestone: M1
area: crypto
created_at: 2026-10-28
updated_at: 2026-10-31
tags: [crypto, spake2p, mbedtls]
blockers: []
depends_on: [ISSUE-0002]
upstream_refs: [connectedhomeip src/crypto/CHIPCryptoPALmbedTLS.cpp, connectedhomeip src/crypto/CHIPCryptoPAL.h:1617, connectedhomeip third_party/mbedtls/repo@6a58fa8122, AROS workbench/libs/mbedtls]
related_files: [tests/crypto-host/]
---

# Por quê

PASE (M3) depende de SPAKE2+; CASE (M4), de ECDSA P-256, ECDH, HKDF, AES-CCM e X.509. No backend mbedTLS do SDK, o SPAKE2+ é montado sobre `mbedtls_ecp_*`/`mbedtls_mpi_*` (e não sobre PSA PAKE nem EC J-PAKE). O SDK fixa o mbedTLS 2.28, e o AROS embarca 3.6.7.

# O quê

Decidir entre: (a) `CHIPCryptoPALmbedTLS` contra o mbedTLS 3.6.7 do AROS; (b) `CHIPCryptoPALPSA` + `PSASpake2p`; (c) o mbedTLS do submódulo do SDK, linkado estaticamente. Fica de fora implementar qualquer primitiva.

# Passos de validação

- [x] Listar as funções/macros `MBEDTLS_*` que o PAL exige → diff contra `mbedtls_aros_config.h`: faltam `MBEDTLS_PKCS5_C` (PBKDF2 do verificador SPAKE2+), `MBEDTLS_X509_CSR_PARSE_C`, `MBEDTLS_X509_CSR_WRITE_C` (+ `MBEDTLS_X509_CREATE_C`). O resto (ECP/ECDSA/ECDH, CCM, SHA-256, HKDF, CTR-DRBG, entropy, X.509 parse) já está.
- [x] Verificar se o SDK compila o PAL mbedTLS contra a 3.6 → sim, **sem patch**: o PAL usa `MBEDTLS_PRIVATE` e tem guardas para 3.0/3.1/3.3/4.0; compila contra a 3.6.7 com a config do AROS.
- [x] Compilar e rodar no host Linux os testes de crypto do SDK contra a 3.6.7 → `TestChipCryptoPAL` (71 testes, inclui SPAKE2+ RFC, P-256, ECDH, HKDF, PBKDF2, AES-CCM, X.509/CSR): config do AROS como está **não linka** (PKCS5); +PKCS5 = 70/71 (CSR); +PKCS5+CSR = **71/71**. Harness em `tests/crypto-host/`, logs em `research/logs/2026-10-31/issue-0003-crypto-host/`.
- [ ] Repetir no AROS (alvo de ISSUE-0002) → log
- [ ] Avaliar a configuração: usar a biblioteca do sistema exige mudar `mbedtls_aros_config.h` upstream? Isso é aceitável upstream?

# Critério de sucesso / falha

- Sucesso se: os vetores SPAKE2+, P-256, HKDF e AES-CCM do SDK passam no AROS com o backend escolhido.
- Falha se: a 3.6.7 exigir patch no PAL que não seja aceitável upstream; nesse caso, cair para (c) e documentar.

# Decisões tomadas

- 2026-10-31: pin do SDK = **última stable, v1.6.1.0** (`3bcdd56ba5`), decisão do mantenedor.
- 2026-10-31 (provisória, até o passo no AROS): **opção (a)**, `CHIPCryptoPALmbedTLS` contra o mbedTLS 3.6.7 do AROS, com 4 opções a mais na config do AROS (PR upstream, genérico: PBKDF2 e CSR servem a qualquer cliente X.509). Custo ~16 KB. (b) PSA não é preciso; (c) mbedTLS 2.28 do SDK fica descartada.

# Log

- 2026-10-28: criada.
- 2026-10-31: passos 1–3 no host Linux. Duas habilidades do backend mbedTLS do SDK pulam (`ECDSA_sign_msg_det`, `InitializeFromBitsOrReject`: só OpenSSL/PSA implementam); fora dos testes só a Network Identity usa, não PASE/CASE.
