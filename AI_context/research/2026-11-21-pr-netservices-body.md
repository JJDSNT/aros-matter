# PR draft — NetServices + catalogued mDNS tools (CX1)

Branch: `review/mdns-commodity` (worktree `~/AROS-b61`), commits `73f4f61bef`, `852fd73a46` on top of #2330 (`898f18a539`).
Open after #2330 is merged, rebased on master. No Claude attribution.

Title: **mdns: NetServices, a commodity on dnssd.library; the tools in the user's language**

---

## Scope

Two commits.

**1. mdns tools: in the user's language, one catalog for all of them**

dnssd, Nearby, Share and Handshake said everything in built-in English. Their words now come from one catalog, `DNSSD.catalog` (`LOCALE:Catalogs/<language>/System/C`), as `Commodities.catalog` serves the commodities: the tools share the words of `sd_common`/`sd_types` (the kinds of service, what an error means), and so does the commodity of the second commit. `catalogs/` holds `DNSSD.cd`, `catalog_version.h` and the makefile; as with the other new catalogs (Accounts), the translations are picked up when they are added — Portuguese (Portugal) and Portuguese (Brazil) are ready for the translation repository.

- Each tool opens the catalog before reading its arguments, so that its argument errors are translated too.
- `SDMsg(MSG_NAME)` takes the English from `strings.h` at the call, not from a table of every message: a tool carries only the text it uses. m68k text (-Os): dnssd 18972 → 19932, Nearby 14164 → 15138, Share 13712 → 14708, Handshake 13624 → 14542.
- dnssd translates what it says to people (notes, errors, usage, progress) and keeps what it reports as it was, in the manner of dns-sd, for scripts: ADD/UPDATE/REMOVE/TYPE, RESOLVED, Registered, the records of -Z and -q. Nearby, Share and Handshake are translated whole. In English the output is unchanged.
- dnssd, Nearby, Share, Handshake: 42.2.

**2. NetServices: a commodity to find, reach and share services on the network**

What Nearby, Handshake and Share do in the shell, in one GadTools window in Tools/Commodities. It comes from amigazen's Bonami commodity, rewritten on dnssd.library:

- One session of its own; mdnsd signals the session's port and the main loop reads the events in the commodity's task (no hook in another task, no polling). The browse is the tools' finder: with Handshake's resolve and Share's registration, 23 operations, within the 24 a session is promised (`#error`).
- Layout in the screen's font and the user's language; side by side, or stacked, or stacked and compact (fits 640 × 256), topaz 8 last.
- Hot key, Exchange (Show, Hide, Remove), CX_PRIORITY/CX_POPKEY/CX_POPUP from the shell or as tool types. Gorilla icon (Computers/Networked_Amiga artwork).
- m68k: 26064 bytes of text; largest frame 560 bytes.

## Validation

- Build: hosted (linux-x86_64) targets `workbench-network-mdns-catalogs`, `-tools`, `-commodity`, Gorilla icons: no warnings. m68k: the five programs with the build's flags and `-Werror`: no warnings.
- `tests`-style run of the tools against Avahi on the host (38 checks: dnssd -R/-P/-L/-G/-q/-Z/-B, Nearby, Share, Handshake): hosted 0 failed (twice), emulated A3000/68030 0 failed. English output identical to before.
- The tools under Portuguese and Portuguese (Brazil) locales: usage, argument errors, Nearby, Handshake, Share, dnssd -L.
- NetServices, hosted (English, Portuguese, Portuguese-Brazil) and emulated A3000 (PAL 640×256): kinds → a kind → a service → Handshake (host, IPv4 and IPv6 link-local addresses, port, TXT); Share seen by `avahi-browse` on the host with its TXT, withdrawn by Stop and by Exchange's Remove; hot key; hide/show keeps the share; started from Workbench with its tool types.
- cppcheck 2.22: no new findings.

(Screenshots in `AI_context/research/2026-11-21-netservices/`: English, Portuguese, Portuguese-Brazil, A3000 — attach to the PR.)
