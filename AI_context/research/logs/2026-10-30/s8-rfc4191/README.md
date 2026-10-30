# S8: RFC 4191 router preferences and Route Information Options

Branch `review/arostcp-ipv6-rfc4191-v2` (pushed to the fork), on `review/arostcp-ipv6-zones` (#1974): commits `1bbfe34df8` (test), `04bf024bee` (RFC 4191), `93cc92132b` (purge on interface down). The test's RAs go to the interface's own link-local, so it needs #1974's loopback fix. PR to open once #1974 is merged: rebase onto master, fill `<MASTER>` in `pr-body.md`, rerun master vs branch.

- `s6-m2/`: base (master + #1974): rio6 5/7 fail (default-router preference passes by list order).
- `s8/`: rio6 7/7 pass; all 13 other suites unchanged, both runs.
- `rio6-wire.txt`: tap capture during rio6: RS and DAD NS only, no Router Advertisement on the wire.

**Opened as AROS #1976** after #1974 merged: branch `review/arostcp-ipv6-rfc4191-v3` on master `d50355747a` (`867f4f784f`, `0b06e9b8cb`, `a004c49906`; stack code identical to v2). `master-1974/`: rio6 5/7 fail; `s8v3/`: 7/7; other 13 suites unchanged. No conflict with #1975.
