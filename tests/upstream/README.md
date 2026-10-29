# Upstream-style tests (for the AROS PRs)

Upstream so far: `cunit-net-mld6.c`, merged with the S1 changes in [AROS #1924](https://github.com/aros-development-team/AROS/pull/1924) (`42cb8e8f34`).

This directory mirrors paths in the AROS tree. Every file here is meant to go upstream with the PR that fixes what the file tests, in the format the stack's own tests already use: CUnit under `developer/debug/test/net/socket/`, with the `socktest.h` helpers and JUnit XML output (bsdsocket `Readme.md` §13). The larger harness in `../ipv6/` stays in aros-matter. It needs a peer on the host, and no upstream test does that.

## `cunit-net-mld6.c` (goes with S1, multicast membership lifecycle)

The program watches its own outgoing MLD with the bsdsocket BPF calls (`bpf_open`/`bpf_ioctl`/`bpf_read`, built with `__CONFIG_ROADSHOW__`), so it needs no peer, only a multicast-capable interface. On hosted AROS that is `tap.device` attached to a host tap. The tests are skipped when there is no such interface.

| Test | Upstream `4c2c268a53` | With S1 |
|---|---|---|
| join/leave send Report/Done (control) | passed | passed |
| closing a socket leaves its groups | **FAILED** | passed |
| rejoin after close is reported | **FAILED** | passed |
| added address joins solicited-node | **FAILED** | passed |
| deleted address leaves solicited-node | **FAILED** | passed |

Evidence: `AI_context/research/logs/2026-10-28/s1-ab/cunit-mld6-{upstream,s1}.log`. The existing socket/tcp/udp/inet6 CUnit suites pass unchanged with S1 (35 tests, 147 asserts): `.../s1-ab/cunit/`.

## Build and run here

```sh
tests/upstream/build.sh OUTDIR       # cross-compiles every cunit-*.c here
# run on hosted AROS with the tap (tools/tap-up.sh); see the script in ../ipv6/run.py or:
#   Execute SYS:System/Network/AROSTCP/S/startnet
#   Wait 4
#   cunit-net-mld6 eth0
```

## Open points for the PR

- **`<net/bpf.h>`**: on Kal's review, #1924 now makes it public (`workbench/network/common/include/net/bpf.h`, first commit of the series), and the test includes it normally. `build.sh` needs a build that has run `network-includes-copy` with that commit.
- **The BPF data link type does not match the data.** `BIOCGDLT` reports `DLT_EN10MB` on Ethernet, but the stack taps the IP packet before the SANA-II driver adds the link header (`net/if_sana.c`, `bpf_mtap()` in `sana_output()`), so a capture holds raw IP. The test accepts both. It should be raised separately.
- In #1924 the test is listed in `CUNITSOCKETTESTFILES` in `developer/debug/test/net/socket/mmakefile.src`.
