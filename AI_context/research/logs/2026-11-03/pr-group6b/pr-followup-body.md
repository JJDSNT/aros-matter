Kal's two points on #2085.

1. **`tcp_sack_rcvblocks()` walks the reassembly queue linearly.** It called `tcp_sack_run()` for every queued segment, each walk starting from the head: with the queue at its cap of 100 segments, about 10,000 steps per out-of-order segment. The other runs are now found in one walk, run by run, stopping once `MAX_SACK_BLKS` blocks are found: at most one walk per block plus one, whatever the queue's length. The blocks and their order (RFC 2018 section 4: the block of the segment just received first, then the ones sent before, most recent first) are unchanged.
2. **The scoreboard's cost is noted** at `TCP_SACK_BOARD`: 8 bytes a range, 224 bytes more in each `tcpcb` than the 4 ranges before.

Two commits; the bump is in the last one: bsdsocket.library 5.32, kernel v0.71.

## Validation

linux-x86_64 hosted, tap.device with a Linux neighbour:

- `tests/tcp/rcvsack_probe.py` (aros-matter; the host sends 1 MB to AROS with four holes in a window): no block below the ACK, every out-of-order segment SACKed, the Linux sender's time unchanged. In two ACKs the first block is not the highest one: in both the segment received last before the ACK is in that first block - Linux sent a lower segment last - which is what RFC 2018 asks for.
- **All suites:** all 49 `cunit-net-*` socket suites pass, in both runs, with two tap.device units.
- The stack builds without warnings.
