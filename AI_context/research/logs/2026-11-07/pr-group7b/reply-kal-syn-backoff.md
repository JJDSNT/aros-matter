Thanks, you are right - I had the seeding in the design and left it out of `tcp_newtcpcb()`. Fixed in the RTT/RTO commit (force-pushed): `t_rttvar = (tcp_rttdflt * 1000 << TCP_RTTVAR_SHIFT) / 4`, and `t_rxtcur` now comes from `TCP_REXMTVAL()` too. A SYN-ACK resent from SYN-RECEIVED outside the syncache gets the same, as its tcpcb comes from `tcp_newtcpcb()`.

On the wire, the first four copies of each SYN dropped:

    before: SYN resent after 1.0, 0.24, 0.24, 0.42 s
    after:  SYN resent after 1.0, 2.04, 4.02, 8.04 s

and `cunit-net-tcpinfo` now has the test you suggested: a non-blocking connect() to a link-local neighbour that does not exist reads the RTO from TCP_INFO after one and after two timeouts - 400 ms / 1.6 s before (fails), 2 s / 4 s after. The bench now reports every interval, not only the first (`rto_probe.py --syn --syn-drops N` in aros-matter). All 51 suites pass in both runs.
