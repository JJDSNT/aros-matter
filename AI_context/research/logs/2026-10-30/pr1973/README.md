# AROS #1973: G17, sendto() pins the UDP/IPv6 source to the socket

Branch `review/arostcp-ipv6-udp-sendto` on master `343de5cddf`; commits `da152cf59f` (test), `09c682bb2e` (fix).

- `master-1950/sendto6.log`: 3/3 fail, both CUnit runs (also 3/3 with #1945 applied).
- `g17/`: sendto6 3/3 pass; socket, tcp, udp, inet6, mld6, route6, cmsg, addr6 unchanged.
- `bench-*.txt`: `tests/ipv6/run.py`, 53 checks. Master 14 failures, G17 12; the only change is `link.send-scopeid` (sendto `ff02::fb%eth0` from `[::]`: master `EADDRNOTAVAIL`, G17 the host receives it from the link-local).
