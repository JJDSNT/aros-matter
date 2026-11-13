# Responder, discovery and query fixtures (Codex's)

Copied from aros-midihub `review/mdns-modernization-plan` `tests/review/` (Codex, 2026-11-09): host builds of
the AROS mdnsd sources with an Exec stub, checked against RFC 6762/6763 cases. Run with
`tools/review-mdns-responder.py --aros-tree ~/AROS-ipv6 --worktree [--discovery|--query]`.

aros-matter changes, each marked in the source:
- `aros_host.h`/`mdns_exec_mock.h`: `MinNode`/`MinList`, `AllocVec`/`FreeVec`, `IsListEmpty`, `MEMF_ANY`
  (what the canonical daemon uses);
- `mdns_responder_rfc.c` `reject-instance`: an instance label with a dot is accepted (RFC 6763 section 4.3); the old
  expectation was a rule of the text names.

Baseline 2026-11-12 on `review/mdnsd-canonical-links` (`77276cbd38`): 44/44, 45/45, 16/16 (Codex's tip: the same).
