# resolver-guru-m68k (B35)

`tools/amiga-run.sh` with `AMIGA_TAP_IP=192.168.166.2` and `resolver-guru-m68k.script`
(the dnssd model and link tests, then `startnet` with every service, then the AROSTCP
link collector test, which adds and removes IPv4/IPv6 aliases): 5 runs out of 5 stop at
a Software Failure in task `timesync` - CHK instruction error, PC in `resolver.atcp`
segment 8 `.bss` (`resolver-guru-m68k.png`). AROS m68k built from 64d00bf2da (+ the
mdnsd canonical-model commits, which do not touch the stack), A3000/68030 on Amiberry.
Not reproduced: timesyncd alone, all services but timesyncd, three concurrent DNS
lookups right after startnet, the same script with startnet first.
