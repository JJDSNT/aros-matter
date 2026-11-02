#!/bin/sh
# tap-up.sh [N]: create the isolated host tap 'arosN' (default aros0) used by
# hosted AROS tests (no bridge to any physical interface), 192.168.(166+N).1/24
# on the host side. AROS's tap.device unit N attaches to it. Needs sudo.
# Undo: sudo ip link del arosN
set -eu
n=${1:-0}
tap=aros$n
net=192.168.$((166 + n))
ip link show $tap >/dev/null 2>&1 || sudo ip tuntap add dev $tap mode tap user "$(id -un)"
ip -4 addr show dev $tap | grep -q $net.1 || sudo ip addr add $net.1/24 dev $tap
sudo ip link set $tap up
# Linux gives a tap its IPv6 link-local only once it first has carrier, i.e.
# once AROS attaches; the benches need it before that, to tell AROS where the
# host is. Give a new tap one (nodad: nothing else is on this link yet).
ip -6 addr show dev $tap scope link | grep -q inet6 ||
    sudo ip -6 addr add fe80::1/64 dev $tap nodad
ip -br addr show $tap
