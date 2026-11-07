Lifetimes and timeouts on the monotonic clock, as asked on #2031: Neighbour Discovery, route expiry and the resolver's cache kept their times on `GetSysTime()`, so setting the system time ended them early or kept them too long. They are now on timer.device's `GetUpTime()` (posixc's `CLOCK_MONOTONIC`), as FreeBSD keeps them on `time_uptime`. Three commits, one per area, each with its test; bsdsocket.library 5.37, kernel v0.76.

## What moved

1. **Neighbour Discovery:** neighbour states, default routers, prefixes, routes from Route Information Options, SLAAC and temporary addresses, the DAD and Router Solicitation timers, and the servers and domains of RA options (RFC 8106). None of them is shown to applications as a time of day; `<netinet/in_var.h>` already called the address lifetimes "seconds since boot". Before, a clock set a day forward took every SLAAC address, RIO route and RDNSS server away at the next tick, and one set back kept them a day longer.
2. **Route expiry** (`rmx_expire`, the 10 minutes a lowered path MTU is kept, RFC 8201 section 4). Applications still see and give it as in BSD, as a time of day: seconds since 1970 in UTC, what `time()` returns. `rt_expire_out()` and `rt_expire_in()` convert at the routing socket (`RTM_GET`, `NET_RT_DUMP`, `RTV_EXPIRE`) and in `GetRouteInfo()`, as FreeBSD's rtsock does. Before, they gave `GetSysTime()`'s seconds since 1978 in local time, and `ip -d route` printed that number as the seconds left; it now prints what is left (`expires 579s`).
3. **The resolver's cache:** answers are kept for their TTL on the same clock.

`netstat -r` reads the routes from the stack's memory (kvm), so it sees the expiry on the stack's clock; it now compares it with `CLOCK_MONOTONIC`, as FreeBSD's netstat does with `CLOCK_UPTIME`. Before, set against `time()`, it was always in the past, and the line went without its interface and expiry; now `2001:db8:4d54:54::1 ... UGHD 1 0 eth0 521`, as `ip -d route` shows `expires 521s`.

Left as they are: what is a time of day (ICMP timestamps, BPF and `if_lastchange`, log lines, `SO_TIMESTAMP` realtime), and ARP's one-request-a-second pacing, which a step does not break (an unsigned difference; a step back does not hold requests).

## Validation

linux-x86_64 hosted. The new suite `cunit-net-clockstep` sets the system time with `TR_SETSYSTIME` and puts it back after each case. Its first case checks the test itself: the step moves `GetSysTime()` by a day and `GetUpTime()` not at all.

| case | 5.36 | + ND | + routes | + cache |
|---|---|---|---|---|
| SLAAC address outlives a step forward (600 s) | fail | pass | pass | pass |
| SLAAC address ends on time after a step back (4 s) | fail | pass | pass | pass |
| RIO route outlives a step forward | fail | pass | pass | pass |
| RIO route ends on time after a step back | fail | pass | pass | pass |
| RDNSS server outlives a step forward | fail | pass | pass | pass |
| lowered path MTU outlives a step forward | | fail | pass | pass |
| a route's expiry reads back as given | | pass | pass | pass |
| cached answer outlives a step forward, its server gone | | | fail | pass |
| cached answer (TTL 3) ends on time after a step back | | | fail | pass |

`cunit-net-pmtu4` and `cunit-net-pmtu6` now compare the expiry with `time()` (they had followed `DateStamp()`). The test DNS server (`dnstest.h`) answers two new names with a TTL, for the cache cases; the others keep TTL 0.

- **All suites:** all 50 `cunit-net-*` socket suites pass, in both the basic and the automated runs. On 5.36 only the new and changed cases fail (`clockstep` 8 of 10, `pmtu4` and `pmtu6` one each, the expiry compared with `time()`).
- **cppcheck** `--enable=warning,style`: no new findings in the changed files. Each commit builds on its own without warnings.
