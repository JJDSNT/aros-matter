#!/bin/sh
# hosted-run.sh WORKDIR SCRIPT [FILE...]
#
# Boots a private copy of a hosted (linux-x86_64) AROS image once, runs the
# AmigaDOS SCRIPT from S:User-Startup, then shuts down and copies the logs out.
# Each FILE is copied into C: of the copy. Output files the script writes to
# SYS:out/ are copied to WORKDIR/out/. Serial/debug output goes to
# WORKDIR/serial.log.
#
# Environment:
#   AROS_HOSTED_IMAGE  hosted AROS system directory
#                      (default: ~/aros-midihub/build-aros-linux/bin/linux-x86_64/AROS)
#   AROS_RUN_TIMEOUT   seconds before the boot is killed (default: 60)
#   AROS_AROSTCP       if set, this AROSTCP binary replaces the image's
#   AROS_TAP_MTU       if set, tap.device unit 0's MTU (576-9000; ENVARC:SYS/Net/tap/unit0/MTU);
#                      the host tap 'aros0' needs the same (ip link set aros0 mtu N)
#   AROS_TAP_IP        if set, adds AROSTCP interface eth0 on tap.device unit 0
#                      (host side: tap 'aros0', see tools/tap-up.sh) with this IPv4
set -eu
[ $# -ge 2 ] || { echo "usage: $0 WORKDIR SCRIPT [FILE...]" >&2; exit 2; }
img=${AROS_HOSTED_IMAGE:-$HOME/aros-midihub/build-aros-linux/bin/linux-x86_64/AROS}
tmo=${AROS_RUN_TIMEOUT:-60}
work=$(realpath -m "$1"); script=$(realpath "$2"); shift 2
[ -x "$img/boot/linux/AROSBootstrap" ] || { echo "no hosted image at $img" >&2; exit 2; }

rm -rf "$work"; mkdir -p "$work"; sys="$work/AROS"
cp -a --reflink=auto "$img" "$sys"
for f in "$@"; do cp "$f" "$sys/C/"; done
mkdir -p "$sys/out"
[ -n "${AROS_AROSTCP:-}" ] && cp "$AROS_AROSTCP" "$sys/System/Network/AROSTCP/C/AROSTCP"
if [ -n "${AROS_TAP_MTU:-}" ]; then
    mkdir -p "$sys/Prefs/Env-Archive/SYS/Net/tap/unit0"
    printf '%s' "$AROS_TAP_MTU" > "$sys/Prefs/Env-Archive/SYS/Net/tap/unit0/MTU"
fi
if [ -n "${AROS_TAP_IP:-}" ]; then
    echo "eth0 DEV=DEVS:Networks/tap.device UNIT=0 IP=$AROS_TAP_IP NETMASK=255.255.255.0 UP" \
        >> "$sys/System/Network/AROSTCP/db/interfaces"
fi
{ echo "FailAt 21"; cat "$script"; echo "Echo >SYS:out/done.log done"; echo "Shutdown"; } > "$sys/S/matter-run"
printf 'Run >NIL: Execute S:matter-run\n' > "$sys/S/User-Startup"

(cd "$sys" && timeout "$tmo" xvfb-run -a boot/linux/AROSBootstrap > "$work/serial.log" 2>&1) || true
cp -r "$sys/out" "$work/out"
rm -rf "$sys"
if [ -f "$work/out/done.log" ]; then echo "finished: $work/out"; else echo "did not finish (timeout or crash): see $work/serial.log"; exit 1; fi
