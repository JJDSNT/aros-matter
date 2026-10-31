#!/bin/sh
# tap-up.sh: create the isolated host tap 'aros0' used by hosted AROS tests
# (no bridge to any physical interface). Needs sudo. Undo: sudo ip link del aros0
set -eu
ip link show aros0 >/dev/null 2>&1 || sudo ip tuntap add dev aros0 mode tap user "$(id -un)"
ip -4 addr show dev aros0 | grep -q 192.168.166.1 || sudo ip addr add 192.168.166.1/24 dev aros0
sudo ip link set aros0 up
# Linux gives a tap its IPv6 link-local only once it first has carrier, i.e.
# once AROS attaches; the benches need it before that, to tell AROS where the
# host is. Give a new tap one (nodad: nothing else is on this link yet).
ip -6 addr show dev aros0 scope link | grep -q inet6 ||
    sudo ip -6 addr add fe80::1/64 dev aros0 nodad
ip -br addr show aros0
