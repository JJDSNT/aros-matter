#!/bin/sh
# tap-up.sh: create the isolated host tap 'aros0' used by hosted AROS tests
# (no bridge to any physical interface). Needs sudo. Undo: sudo ip link del aros0
set -eu
ip link show aros0 >/dev/null 2>&1 || sudo ip tuntap add dev aros0 mode tap user "$(id -un)"
ip -4 addr show dev aros0 | grep -q 192.168.166.1 || sudo ip addr add 192.168.166.1/24 dev aros0
sudo ip link set aros0 up
ip -br addr show aros0
