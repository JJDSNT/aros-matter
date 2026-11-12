#!/bin/sh
# amiga-run.sh WORKDIR SCRIPT [FILE...]
#
# Boots AROS m68k once on an emulated Amiga (Amiberry), runs the AmigaDOS
# SCRIPT from S:User-Startup, then stops the emulator and keeps the logs: the
# m68k counterpart of hosted-run.sh. The system is a private copy of an
# amiga-m68k build's AROS directory, mounted as the boot volume (a UAE
# directory filesystem); each FILE is copied into its C:. Output the script
# writes to SYS:out/ is in WORKDIR/out/, the emulator's log in WORKDIR/amiberry.log,
# and when the script does not finish, the screen at that moment in WORKDIR/screen.png.
#
# The machine: an A3000 (ECS, 68030, 2 MB chip RAM) with Fast RAM and an
# A2065 Ethernet board on the host tap 'aros0' (tools/tap-up.sh), driven by
# a SANA-II a2065.device.
#
# Environment:
#   AMIGA_SYSTEM      amiga-m68k AROS directory (default ~/aros-build-hist-m68k/bin/amiga-m68k/AROS)
#   AMIGA_ROM         main ROM (default AMIGA_SYSTEM/../gen/boot/aros-amiga-m68k-rom.bin)
#   AMIGA_EXTROM      extended ROM (default .../aros-amiga-m68k-ext.bin)
#   AMIBERRY          the amiberry binary (default ~/emu/amiberry-dl/squashfs-root/AppRun)
#   AMIGA_A2065_DEV   the SANA-II driver (default ~/emu/drivers/SANA/SANA/dev/devs/networks/a2065.device)
#   AMIGA_FAST_MB     Fast RAM in MB (default 8; Zorro III above 8)
#   AMIGA_CPU         68000/68020/68030/68040 (default 68030)
#   AMIGA_TAP_IP      if set, eth0 on the A2065 with this IPv4
#   AMIGA_AROSTCP     if set, this AROSTCP binary replaces the system's
#   AMIGA_RUN_TIMEOUT seconds before the emulator is stopped (default 300)
set -eu
[ $# -ge 2 ] || { echo "usage: $0 WORKDIR SCRIPT [FILE...]" >&2; exit 2; }
sysdir=${AMIGA_SYSTEM:-$HOME/aros-build-hist-m68k/bin/amiga-m68k/AROS}
rom=${AMIGA_ROM:-$sysdir/../gen/boot/aros-amiga-m68k-rom.bin}
ext=${AMIGA_EXTROM:-$sysdir/../gen/boot/aros-amiga-m68k-ext.bin}
amiberry=${AMIBERRY:-$HOME/emu/amiberry-dl/squashfs-root/AppRun}
drv=${AMIGA_A2065_DEV:-$HOME/emu/drivers/SANA/SANA/dev/devs/networks/a2065.device}
fast=${AMIGA_FAST_MB:-8}
cpu=${AMIGA_CPU:-68030}
tmo=${AMIGA_RUN_TIMEOUT:-300}
work=$(realpath -m "$1"); script=$(realpath "$2"); shift 2
[ -f "$rom" ] || { echo "no AROS m68k ROM (aros-rom.bin) near $sysdir" >&2; exit 2; }

rm -rf "$work"; mkdir -p "$work"; sys="$work/AROS"
cp -a --reflink=auto "$sysdir" "$sys"
for f in "$@"; do cp "$f" "$sys/C/"; done
mkdir -p "$sys/out" "$sys/Devs/Networks"
cp "$drv" "$sys/Devs/Networks/a2065.device"
[ -n "${AMIGA_AROSTCP:-}" ] && cp "$AMIGA_AROSTCP" "$sys/System/Network/AROSTCP/C/AROSTCP"
if [ -n "${AMIGA_TAP_IP:-}" ]; then
    echo "eth0 DEV=DEVS:Networks/a2065.device UNIT=0 IP=$AMIGA_TAP_IP NETMASK=255.255.255.0 UP" \
        >> "$sys/System/Network/AROSTCP/db/interfaces"
fi
{ echo "FailAt 21"; cat "$script"; echo "Echo >SYS:out/done.log done"; } > "$sys/S/matter-run"
printf 'Run >NIL: Execute S:matter-run\n' > "$sys/S/User-Startup"

# Zorro II Fast RAM up to 8 MB; more as Zorro III
if [ "$fast" -le 8 ]; then mem="-s fastmem_size=$fast"; else mem="-s z3mem_size=$fast"; fi
set -- --log -G -r "$rom" ${ext:+-K "$ext"} --model A3000 \
    -s cpu_type="$cpu" -s cpu_model="$cpu" -s cpu_speed=max -s cpu_compatible=false \
    -s chipmem_size=4 $mem \
    -s a2065=aros0 -s sound_output=none \
    -s filesystem2="rw,DH0:System:$sys,10"
setsid timeout "$((tmo + 30))" xvfb-run -a "$amiberry" "$@" > "$work/amiberry.log" 2>&1 &
pid=$!
t=0
while [ $t -lt "$tmo" ] && [ ! -f "$sys/out/done.log" ] && kill -0 $pid 2>/dev/null; do sleep 1; t=$((t + 1)); done
# not finished: a picture of the screen (Amiberry's IPC socket), for what stopped it
if [ ! -f "$sys/out/done.log" ] && kill -0 $pid 2>/dev/null; then
    python3 -c "import socket,sys; s=socket.socket(socket.AF_UNIX); s.connect('/run/user/%d/amiberry.sock' % __import__('os').getuid()); s.sendall(('SCREENSHOT\t' + sys.argv[1] + '\n').encode()); s.settimeout(5); s.recv(200)" "$work/screen.png" 2>/dev/null || true
fi
sleep 1
# everything setsid started (timeout, xvfb-run, Xvfb, amiberry) is in one
# session: stop it by the session's id ($pid need not lead a process group,
# and Amiberry does not stop on SIGTERM)
sid=$(ps -o sid= -p $pid 2>/dev/null | tr -d ' ')
if [ -n "$sid" ]; then
    pkill -TERM -s "$sid" 2>/dev/null || true
    t=0
    while kill -0 $pid 2>/dev/null && [ $t -lt 3 ]; do sleep 1; t=$((t + 1)); done
    pkill -KILL -s "$sid" 2>/dev/null || true
fi
wait $pid 2>/dev/null || true
cp -r "$sys/out" "$work/out"
rm -rf "$sys"
if [ -f "$work/out/done.log" ]; then echo "finished: $work/out"; else echo "did not finish (timeout or crash): see $work/amiberry.log" >&2; exit 1; fi
