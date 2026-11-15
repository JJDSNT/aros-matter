# B35 — m68k memory corruption while addresses change (investigation, paused)

**Status (2026-11-15): confirmed, unresolved, deferred** (paused by the user's instruction, until
after the mDNS work). No AROS change was made for it; nothing published.

Code under test: AROS master `eb6ffb328a` (modular AROSTCP + #2218's ACD) built for amiga-m68k
in `~/AROS-hist` / `~/aros-build-hist-m68k` (with the ifconfig/ip commands of #2277/#2284, which
do not matter here), on Amiberry, A3000 / 68030, 8 MB Fast RAM, A2065 on tap `aros0`.

## 1. Evidence (observed, reproducible)

| # | What | How it was seen |
|---|---|---|
| E1 | Adding and removing addresses while the stack's services run kills the Amiga most of the time | §4 tables |
| E2 | The deaths take several forms: an alert in a task, an Amiga reset, the emulator exiting, a hang after the work is done | serial + emulator log |
| E3 | Alerts appear in **different tasks**: `mdns`, `bsdsocket.library`, `CLI`, `dnssdlinkarostest` | serial (`AMIGA_SERIAL`) |
| E4 | Alert PCs: `0x00000008` (illegal instruction), `0xFFFFFF4C` and `0xFFFFFDF8` (bus/address error), `0x07CA093C` (privilege violation, in RAM) | serial |
| E5 | **Exec itself detected heap corruption**: the "reset" variant is `validateChunk` (exec's allocator) → `Exec_UserAlert` with `0x8100000C` (`AN_MemoryInsane`) → `ExtAlert` → `ShutdownA` → `ColdReboot` | Amiberry debugger catch (run `b35-catch21`), addresses mapped with the ROM's `aros-amiga-m68k.elf` symbols |
| E6 | With exec's checks: `0x81000005 Corrupt memory list detected` in `FreeMem` (task `mdns`), **a free MemChunk with next 0, size 0** at `0x07b9d0f8` - zeros written over a free chunk's header | serial, Mungwall ROM run `b35-mw2` |
| E7 | That chunk lay in memory `netconfig.atcp`'s code had occupied before it was unloaded (offset 0xFEC of its `.text`), i.e. freed and reused memory - not a netconfig object | module map line (debug patch) + `netconfig/.map` |
| E8 | Not on-demand module loading: with `MODULES=RESOLVER,NETCONFIG` (no load/unload) 3 of 3 runs failed | §4 |
| E9 | Not timesyncd alone, not mdnsd alone: without timesync 3/3 failed; without mdns 3/4 died, 1 hung | §4 |
| E10 | **Both families trigger it**: a loop of 10 × add/remove of one IPv4 alias - 3 of 5 died; the same with one IPv6 address - 3 of 5 died | §4 |
| E11 | **No services, no corruption**: the same IPv4 loop with `services.d` emptied - 5 of 5 finished | §4 |

## 2. Hypotheses (not yet shown)

| # | Hypothesis | For | Against / unknown |
|---|---|---|---|
| H1 | A **use after free**: a stale pointer to memory freed when an address goes, written to (zeros) afterwards | E5, E6, E7 (zeros over a free chunk), E3/E4 as consequences (overlapping allocations, zeroed library bases) | which object, which writer |
| H2 | The writer is on the path **a service takes when it reacts to an address change** - a stack call that hands out or keeps a pointer to something freed with the address (interface/address lists, routing-socket messages, `GetRouteInfo()`/`ObtainInterfaceList()`/`QueryInterfaceTagList()`, the address-change signal) | E11 vs E10 | which service: each of mdns, timesync alone is not needed (E9); dhcpd ran in every failing variant and was not isolated |
| H3 | The PC 0x8 / −180 / −520 alerts are library calls through a base pointer that was zeroed by the corruption | A6 = 0 in the PC 0x8 context; `JSR -n(A6)` arithmetic | the zeroed base's owner not identified |
| H4 | The original 2026-11-12 symptom (guru in `timesync`, PC in `resolver.atcp`'s `.bss`) is the same corruption | same scenario, predates ACD | not re-observed on current master |

What is **ruled out**: our mdnsd as the cause (E9), ACD (the 2026-11-12 build predates it), on-demand
module loading (E8), the family-specific code paths alone (E10).

## 3. Reproduction

All with `tools/amiga-run.sh` (m68k image `~/aros-build-hist-m68k/bin/amiga-m68k/AROS`),
`AMIGA_TAP_IP=192.168.166.2`, `AMIGA_SERIAL=<file>` for AROS's serial output.

- **Original**: `tests/stack/repro/resolver-guru-m68k.script` (the dnssd model/link tests, then
  `startnet` with every service, then `dnssdlinkarostest`, which adds/removes an IPv4 and an IPv6
  address). Append `Wait 10` and `Echo >SYS:out/alive ok`: no `alive` = it died.
- **Minimal**: `startnet` with the services, then 10 × `ifconfig eth0 192.0.2.211 netmask 255.255.255.0 alias` /
  `ifconfig eth0 192.0.2.211 -alias` with `Wait 1` between (IPv6: `ifconfig eth0 inet6
  2001:db8:4d54:35::1 prefixlen 64 alias` / `-alias`). ~3 in 5 die.
- **Control**: the same with `Delete SYS:System/Network/AROSTCP/db/services.d/#?` first: 5 in 5 finish.

A run takes ~5 min. Do one run at a time (one tap, one IPC socket, one Xvfb).

## 4. Results (run directories under `tests/stack/out/`)

| Variant | Runs | Finished | Died | Hung | Dirs |
|---|---|---|---|---|---|
| original, with mdns | 5 | 1 | 2 | 2 | `b35-recheck1..5-*` |
| original, without mdns | 4 | 0 | 3 | 1 | `b35-nomdns1..4-*` |
| original + serial | 4 | 1 | 3 | 0 | `b35-ser1..4-*` |
| `MODULES=RESOLVER,NETCONFIG` | 3 | 0 | 2 | 1 | `b35-modules1..3-*` |
| without timesync | 3 | 0 | 3 | 0 | `b35-notimesync1..3-*` |
| Mungwall ROM | 2 | 1 | 1 (E6) | 0 | `b35-mw1..2-*` |
| IPv4 loop, services | 5 | 2 | 3 | 0 | `b35-v4-1..5-*` |
| IPv6 loop, services | 5 | 2 | 3 | 0 | `b35-v6-1..5-*` |
| **IPv4 loop, no services** | 5 | **5** | 0 | 0 | `b35-v4nosvc-1..5-*` |
| debugger catch | - | - | E5 | - | `b35-catch21-*/catch.txt` |

Key logs: `b35-ser1-*/serial.txt` (alert in `mdns`, PC 0x8), `b35-ser2-*/serial.txt`
(`bsdsocket.library`), `b35-modules2/3-*`, `b35-notimesync1-*` (PC −180, −520, RAM), `b35-mw2-*/serial.txt`
(E6), `b35-catch21-*/catch.txt` (E5).

Note on runs `b35-v4-2`, `b35-v6-2`, `b35-v4/v6-3..5` first read as "inconclusive": they were real
deaths, hidden by a bug in `amiga-run.sh` (fixed in `fcda9b0`).

## 5. Tools (in aros-matter)

- `tools/amiga-run.sh AMIGA_SERIAL=FILE` - the Amiga's serial port (AROS debug output, alerts)
  through Amiberry's TCP serial (`serial_port=TCP://127.0.0.1:PORT`) and `tools/ptylog.py`.
  (A pty does not work: Amiberry only opens ports it enumerates.)
- `tools/amiga-catch.py OUTFILE SERIALFILE` - Amiberry's debugger over its IPC socket
  (`/run/user/UID/amiberry.sock`: `DEBUG_ACTIVATE`, `SET_BREAKPOINT addr`, `DEBUG_STATUS`,
  `GET_CPU_REGS` with USP/ISP, `READ_MEM addr width` in decimal). Waits for AROS to boot, puts a
  breakpoint on the bus/address/illegal handler (`0x00FE4AA0`, vector table at 0), saves registers,
  the exception frame, the task stack and, for each return-address candidate, whether a JSR/BSR
  precedes it. **Not on the privilege-violation handler**: AROS takes it hundreds of times on its
  normal path (`0x00FE46D0`), which slowed the Amiga and changed the timing.
- `tests/stack/repro/b35-debug.patch` (local only, never upstream): `DEFKRN_CMDLINE="mungwall"`
  in `arch/m68k-amiga/boot/mmakefile.src` (a ROM rebuild: `make kernel-link-amiga-m68k`), and a
  log line in `netmodule_load()` with each module's base, descriptor and first jump-table target,
  to map addresses with `modules/<name>/<name>/.map`.
- ROM symbols: `m68k-aros-nm -n bin/amiga-m68k/gen/boot/aros-amiga-m68k.elf`.
- Bellatrix has an m68k `KrnBacktraceFromFrame()` (`aros/arch/m68k-emu68/kernel/backtracefromframe.c`)
  - upstream m68k has only the stub; useful in general (needs frame pointers), not for B35 (A6 = 0).

## 6. Recommended next steps (when resumed)

1. **Which service**: the minimal IPv4 loop with one service at a time (dhcpd alone, mdnsd alone,
   timesyncd alone). dhcpd is the one not yet isolated.
2. **Which call**: with that service, find the stack call it makes on the address-change signal
   (code review of the service and of the API it calls), and what that call keeps or returns that
   belongs to a deleted address.
3. **Who writes**: a write watchpoint on the corrupted chunk needs Amiberry's internal debugger
   (`w` command), which the IPC does not expose - or a targeted check in the suspected free path
   (fill the freed object with a pattern, `kprintf` on the next write).
4. Then the fix, with the minimal loop as the test (before ~3/5 die, after 5/5 finish) and the
   cunit suite.
