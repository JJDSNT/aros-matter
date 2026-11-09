`tap.device` reported 10 Mbit/s in `S2_DEVICEQUERY`. A stack sizes its read requests by it: AROSTCP (`sana_speed_reqno()`) posts 16 per protocol up to 10 Mbit/s and 128 from 100 Mbit/s. A host tap delivers as fast as the host does, so a burst of more frames than there were requests pending found none, and `tap_receive()` dropped them as orphans. It now reports 1 Gbit/s.

## Validation

Linux host, AROS receiving 20 MB over IPv4 from the host, with a netem delay on the host's side (`ack_probe.py` in aros-matter):

| RTT | before | after |
|---|---|---|
| 20 ms | 8.4 Mbit/s, 139 segments resent by the host | 44.7 Mbit/s, none |
| 100 ms | 1.8 Mbit/s | 10.0 Mbit/s, none |

The same as with `IPREQ=128` on the interface's line, so it is the request count: the receive window (128 KB / RTT) is now the limit, as it is for sending. All 51 network socket suites pass with it.

Not changed here: with a stack that posts fewer requests than a burst, frames are still dropped; holding them in the host's queue until a read request comes (not reading the descriptor meanwhile) would be the complete answer.
