# AROS #1970: G16a, IPv6 source selection and MLD link-local source

Branch `review/arostcp-ipv6-linklocal-source` on master `6053248953`; commits `9a0a18dc28` (test), `2c3a43f06a` (`in6_ifawithifp()`, RFC 6724 rules 2/3/7), `e98c6c4685` (MLD from the link-local).

Hosted linux-x86_64 with the tap `aros0`. Each directory holds the logs of one AROSTCP build; every log has both CUnit runs (basic and automated).

| Dir | Stack | srcaddr6 |
|---|---|---|
| `master-1948/` | master | 3/4 fail (link-scope destination, MLD `ff12::`, MLD `ff15::`) |
| `aonly/` | master + `in6_ifawithifp()` only | 1/4 fail (MLD `ff15::`): the MLD commit is needed |
| `g16a/` | the branch | 4/4 pass; socket, tcp, udp, inet6, mld6, route6 and cmsg unchanged |
