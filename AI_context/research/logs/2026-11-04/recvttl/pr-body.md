IPv4's `IP_RECVTTL`: a UDP socket can learn the TTL a datagram arrived with, as IPv6 has `IPV6_RECVHOPLIMIT`. An mDNS responder checks it is 255 (RFC 6762 section 11). One commit; bsdsocket.library 5.33, kernel v0.72.

## The option and its message

- `IP_RECVTTL` = 65, FreeBSD's number (Linux's 12 is `IP_ADD_MEMBERSHIP` here). A bool in an int, like `IP_RECVTOS`; another size gives `EINVAL`.
- `recvmsg()` then carries a message of level `IPPROTO_IP`, type `IP_RECVTTL`, with the TTL in one byte - FreeBSD's convention, which `IP_RECVTOS` already follows here, not Linux's `IP_TTL` and int.
- It is built by `sbcreatecontrol()` with the same `CMSG_*` macros applications use: `cmsg_len` = `CMSG_LEN(1)` (17 on x86_64, 13 on m68k), the data at `CMSG_DATA()`, `CMSG_SPACE(1)` (32, 16) in the buffer. A buffer too small for it reports `MSG_CTRUNC`, as any control message.
- The TTL is the one in the header as the datagram arrived: `udp_input()` keeps the header before the checksum overlays the TTL byte, and reassembly keeps each fragment's header intact.
- UDP only, as `IP_RECVTOS`: TCP has no TTL per message, and raw IPv4 sockets carry no ancillary data yet.

Files: `netinet/in.h`, `netinet/in_pcb.h` (`INP_RECVTTL`, in `INP_CONTROLOPTS`), `ip_ctloutput()` (set and get), `udp_savecontrol()`, the Readme.

## Validation

linux-x86_64 hosted:

- `cunit-net-cmsg`, four new tests: the option (off by default, on and off, an int only); the value - the sender's TTL (37, then 200), not the receiving socket's own `IP_TTL` (99) - with `cmsg_len`, the data's offset and `msg_controllen` checked, and no message once it is off; a 4000-byte datagram reassembled from fragments over the loopback; two short control buffers (`MSG_CTRUNC`). The multicast test also checks the TTL is its `IP_MULTICAST_TTL`. On 5.32, 5 of the 12 tests fail; here all pass, 125 asserts, in both the basic and the automated runs.
- **All suites:** all 49 `cunit-net-*` socket suites pass, in both runs, with two tap.device units.
- **cppcheck** `--enable=warning,style`: no new findings in the changed files. The stack builds without warnings.
