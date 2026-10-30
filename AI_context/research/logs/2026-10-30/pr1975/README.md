# AROS #1975: IPV6_MULTICAST_IF picks the source of a UDP6 group datagram (rest of S7)

Branch `review/arostcp-ipv6-mcast-if` on master `b145f05fb3`.
- sendto6 (now 4 tests): master 1/4 fail (the new case), branch 4/4; all other suites unchanged, both runs.
- Bench (`tests/ipv6/run.py`, 57 checks): master 7 failures, #1975 1 (`link.recv-scopeid`, fixed by #1974), #1974 + #1975 merged together **0**.
