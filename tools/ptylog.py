#!/usr/bin/env python3
"""ptylog.py OUTFILE PORT - the Amiga's serial port, which Amiberry serves on
TCP (serial_port=TCP://127.0.0.1:PORT, tools/amiga-run.sh AMIGA_SERIAL):
connect (retrying while the emulator starts) and append everything that
comes to OUTFILE until the connection ends or this is killed."""
import socket, sys, time

out, port = sys.argv[1], int(sys.argv[2])
for _ in range(600):
    try:
        s = socket.create_connection(("127.0.0.1", port), timeout=1)
        break
    except OSError:
        time.sleep(0.2)
else:
    sys.exit(1)
s.settimeout(None)
with open(out, "ab", buffering=0) as f:
    while True:
        data = s.recv(4096)
        if not data:
            break
        f.write(data)
