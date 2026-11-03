The second half of group 6: TCP loss recovery with SACK, on both sides of a connection. Four commits, one per change; the revision bump is in the last one: 5.31, kernel v0.70.

## Scope

1. **An ACK that SACKs new data is a duplicate ACK** (RFC 6675 section 2). `tcp_input()` counted a duplicate ACK only if it offered the same window as the one before (RFC 5681). Linux grows its window as it reads and changes it in every ACK: no duplicate ACK was counted, fast retransmit never started, and every loss against a Linux receiver waited for the retransmission timer. An ACK with SACK blocks now counts if it SACKs data not SACKed before, whatever its window, and only then: one that only reports a duplicate (a D-SACK, RFC 2883) does not, as three of them started a spurious recovery. Without SACK blocks the window rule is as before.
2. **Loss recovery with SACK follows RFC 6675.** With SACK, recovery was still NewReno's: each partial ACK resent the first unacknowledged segment, likely on its way with reordering. With PRR on, the scoreboard chose, but without HighRxt every duplicate ACK resent the first hole again, and DeliveredData was one segment whatever the ACK delivered (a 1 MB transfer with 1 in 50 segments lost took 1928 segments instead of 715). The scoreboard now gives `IsLost()`, `SetPipe()` and `NextSeg()`; on each ACK in recovery `tcp_sack_recover()` sends lost holes, each once, then new data, then other holes, within cwnd - pipe, or what PRR allows from the data delivered. The scoreboard holds 32 ranges instead of 4 and drops the highest when full. Without SACK, recovery is NewReno as before.
3. **sysctl `net.inet.tcp.prr`.** PRR (RFC 6937) sat behind a variable nothing could set. It stays off: with the same binary, PRR on and off gave the same results on every loss scenario below.
4. **The SACK blocks a receiver sends** (RFC 2018 section 4). They were built lowest first, before `rcv_nxt` moved: the first block was not the one holding the segment that triggered the ACK, which it MUST be, and a segment that filled a hole was reported below the ACK that acknowledged it, which a sender takes for a D-SACK (Linux may then undo its window reduction). The blocks are now built once `rcv_nxt` has moved: the run holding the segment just queued first, then the blocks sent before, most recent first; none below `rcv_nxt`.

**Checked, nothing to change:** RFC 6582's "recover" check (no new fast retransmit for duplicate ACKs of data sent before the last recovery point). Without SACK no re-entry showed up; with SACK it would block a legitimate fast retransmit of a segment lost at the recovery point.

## Validation

linux-x86_64 hosted, tap.device with a Linux neighbour. A CUnit test cannot place losses or inject ACKs, so these are aros-matter benches on the wire, each checking that it did what it is for before its results count:

- `tests/tcp/loss_probe.py`: AROS sends 1 MB per scenario, the host's ACKs delayed 20 ms; it counts needless retransmissions (of data the host had acknowledged or SACKed 5 ms or more before) and segments sent 3+ times.

  | Scenario | master | this branch |
  |---|---|---|
  | 1 in 50 lost | 10-12 s, 6 timeouts | 0.32 s, none |
  | several holes in a window | 10 s, 6 timeouts, 5 needless | 0.32 s, none, 0 needless |
  | a lost retransmission | 1 timeout | 1 timeout (as expected without RACK) |
  | reordering, no loss | 186-216 spurious | 110-156 spurious (group 7: RACK, D-SACK undo) |
  | 1 in 50 lost, PRR on (before / after) | 1928 segments, 853 needless | 715 segments, 0 needless |

  Without SACK on the host (`--nosack`), recovery behaves as on master.
- `tests/tcp/dupack_probe.py`, deterministic: with data in flight, three duplicate ACKs are injected from the host's last real one. Three D-SACKs: master and commit 1 without its D-SACK part retransmit; this branch does not. Three ACKs SACKing new data, and three with no SACK and the same window: fast retransmit on all.
- `tests/tcp/rcvsack_probe.py`: the host sends 1 MB to AROS with four holes in a window. ACKs with 2+ blocks whose first block is not the newest: 52 of 52 on master, 0 here; ACKs whose first block lies below their own ACK: 44, then 0. The Linux sender's time is unchanged.
- **All suites:** all 49 `cunit-net-*` socket suites pass, in both runs, with two tap.device units; `cunit-net-sysctl` has the new knob.
- **Regression:** `tests/tcp/run_tcp.py` (SYN options, loss recovery, reset on close, RTO) as on master.
- **cppcheck** `--enable=warning,style`: no new findings in the changed files.
- **Bisect:** each commit builds on its own, stack and tests, without warnings.
