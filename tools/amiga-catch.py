#!/usr/bin/env python3
"""
amiga-catch.py OUTFILE [SERIALFILE] - stop the Amiga (Amiberry, run by tools/amiga-run.sh)
when the CPU enters the handler of a bus error, address error, illegal
instruction or privilege violation (B35), and write, before anything else
runs:

  - the CPU registers (with USP: the faulting task's stack, and ISP);
  - the exception frame on the supervisor stack: SR, the faulting PC, the
    frame format and vector (68030), and the words after it;
  - 48 longwords from USP, and for each that could be a return address the
    8 words before it, marked when they end in a JSR or BSR that would have
    pushed it - in particular JSR -n(A6), a library call: then n, and the
    library it is in A6's place for.

The vectors are read from the table at 0 (VBR is 0 on this ROM) once AROS
has set it up - with SERIALFILE (amiga-run.sh AMIGA_SERIAL), when the stack
has loaded its first module; a breakpoint goes on each handler. Amiberry's IPC socket
(/run/user/UID/amiberry.sock) carries the commands; the CPU is left stopped,
and the run then times out. Run in the background next to amiga-run.sh.
"""
import os, re, socket, sys, time

SOCK = "/run/user/%d/amiberry.sock" % os.getuid()
KNOWN = {(0x00fe46d0, 0x020)}       # (faulting PC, vector) AROS raises on purpose
# Bus error, address error and illegal instruction share one handler on this
# ROM. The privilege violation's handler is left out: AROS takes it hundreds
# of times on its normal path (0x00fe46d0), and stopping there each time
# slowed the Amiga enough to change what it does (2026-11-15).
VECTORS = {0x08: "bus error", 0x0C: "address error", 0x10: "illegal instruction"}


def cmd(*args, timeout=5):
    for attempt in range(50):              # the socket may not be served yet
        s = socket.socket(socket.AF_UNIX)
        s.settimeout(timeout)
        try:
            s.connect(SOCK)
            break
        except (ConnectionRefusedError, FileNotFoundError):
            s.close()
            if attempt == 49:
                raise
            time.sleep(0.2)
    s.sendall(("\t".join(str(a) for a in args) + "\n").encode())
    out = b""
    try:
        while not out.endswith(b"\n"):
            d = s.recv(65536)
            if not d:
                break
            out += d
    except socket.timeout:
        pass
    s.close()
    return out.decode(errors="replace").strip()


def fields(reply):
    """'OK\\tA=1\\tB=2' -> {'A': '1', 'B': '2'}"""
    return dict(p.split("=", 1) for p in reply.split("\t")[1:] if "=" in p)


def mem(addr, width):
    r = cmd("READ_MEM", "0x%08x" % (addr & 0xffffffff), width).split("\t")
    try:
        return int(r[1]) if r[0] == "OK" else None
    except (IndexError, ValueError):
        return None


def call_before(ret):
    """The words before a candidate return address, and the call that would
    have pushed it, if one ends exactly there."""
    words = [mem(ret - 2 * j, 2) for j in range(8, 0, -1)]
    n = len(words)
    for i in range(n - 1, -1, -1):
        w, left = words[i], n - i
        if w is None:
            continue
        if (w & 0xffc0) == 0x4e80:                       # JSR <ea>
            mode, reg = (w >> 3) & 7, w & 7
            ext = {2: 0, 5: 1, 6: 1}.get(mode)
            if mode == 7:
                ext = {0: 1, 1: 2, 2: 1, 3: 1}.get(reg)
            if ext is not None and left == 1 + ext:
                what = "jsr"
                if mode == 5:                            # d16(An)
                    d = words[i + 1]
                    d = d - 0x10000 if d is not None and d & 0x8000 else d
                    what = "jsr %d(a%d)" % (d, reg)
                return words, (ret - 2 * left, what)
        if (w & 0xff00) == 0x6100:                       # BSR
            d = w & 0xff
            ext = 0 if d not in (0, 0xff) else (1 if d == 0 else 2)
            if left == 1 + ext:
                return words, (ret - 2 * left, "bsr")
    return words, None


def main():
    out = sys.argv[1]
    for _ in range(600):                                 # the emulator starting
        try:
            if cmd("DEBUG_STATUS", timeout=2).startswith("OK"):
                break
        except OSError:
            pass
        time.sleep(0.5)
    if len(sys.argv) > 2:                                # AROS up: the stack loading
        for _ in range(600):
            try:
                if b"module netconfig loaded" in open(sys.argv[2], "rb").read():
                    break
            except OSError:
                pass
            time.sleep(0.5)
    handlers = {v: mem(v, 4) for v in VECTORS}
    log = ["handlers: " + ", ".join("%s 0x%08x" % (VECTORS[v], h or 0) for v, h in handlers.items()),
           cmd("DEBUG_ACTIVATE")]
    for slot, (v, h) in enumerate(handlers.items()):
        if h:
            log.append(cmd("SET_BREAKPOINT", "0x%08x" % h, slot))
    log.append(cmd("LIST_BREAKPOINTS"))
    log.append(cmd("DEBUG_CONTINUE"))
    with open(out, "w") as f:
        f.write("\n".join(log) + "\n")
    skipped = {}
    while True:
        try:
            st = fields(cmd("DEBUG_STATUS", timeout=2))
        except OSError:
            return 1                                     # the emulator went away
        if st.get("stopped") != "1":
            time.sleep(0.2)
            continue
        # AROS raises one of these on purpose: a privilege violation at
        # 0x00fe46d0 in its ROM, a privileged instruction run from user mode
        # (seen on the first catch). Only that signature is let through;
        # anything else stops, in ROM or not.
        regs = fields(cmd("GET_CPU_REGS"))
        ssp = int(regs.get("A7", "0"), 16)
        fpc, fvec = mem(ssp + 2, 4) or 0, (mem(ssp + 6, 2) or 0) & 0xfff
        if (fpc, fvec) in KNOWN:
            skipped[(fpc, fvec)] = skipped.get((fpc, fvec), 0) + 1
            cmd("DEBUG_CONTINUE")
            time.sleep(0.05)
            continue
        break
    with open(out, "a") as f:
        f.write("let through (known): %s\n" % (", ".join("PC 0x%08x vector 0x%03x x%d" % (k[0], k[1], n)
                                                     for k, n in skipped.items()) or "none"))
    pc = int(regs.get("PC", "0"), 16)
    usp = int(regs.get("USP", "0"), 16)
    ssp = int(regs.get("A7", "0"), 16)                   # in the handler: supervisor
    which = [VECTORS[v] for v, h in handlers.items() if h == pc]
    with open(out, "a") as f:
        f.write("\nstopped: %s at PC 0x%08x (%s)\nregisters: %s\n" % (
            st, pc, ", ".join(which) or "?", " ".join("%s=%s" % kv for kv in regs.items())))
        sr, fpc, fv = mem(ssp, 2), mem(ssp + 2, 4), mem(ssp + 6, 2)
        f.write("\nexception frame at SSP 0x%08x: SR %04x  PC 0x%08x  format %x vector 0x%03x\n" % (
            ssp, sr or 0, fpc or 0, (fv or 0) >> 12, (fv or 0) & 0xfff))
        f.write("  frame words: %s\n" % " ".join("%04x" % (mem(ssp + 2 * k, 2) or 0) for k in range(0, 46)))
        f.write("\ntask stack from USP 0x%08x:\n" % usp)
        for k in range(48):
            a = usp + 4 * k
            v = mem(a, 4)
            note = ""
            if v and not v & 1 and 0x400 <= v < 0x10000000:
                words, call = call_before(v)
                note = "  before: %s%s" % (" ".join("%04x" % w if w is not None else "????" for w in words),
                                            "  <- %s at 0x%08x" % (call[1], call[0]) if call else "")
            f.write("  0x%08x: %s%s\n" % (a, "%08x" % v if v is not None else "?", note))
    return 0


if __name__ == "__main__":
    sys.exit(main())
