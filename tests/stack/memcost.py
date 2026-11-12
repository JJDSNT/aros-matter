#!/usr/bin/env python3
"""
memcost.py - what the stack takes of AROS's memory, at rest and under load
(hosted AROS, x86_64).

AROS records its free memory (C:memsnap, AvailMem(MEMF_ANY)):
  boot   before the stack starts;
  idle   10 s after startnet (eth0 up; with IPv6, its link-local, DAD, MLD);
  load   the least free while the host sends BYTES on CONNS TCP connections at
         once to AROS (C:tcpserve, one process each), with netem DELAY ms;
  after  3 s after the connections have closed (the mbuf pool is never given
         back, so this is its peak).
The figures are differences from "boot": rest = boot - idle (the stack's
binary, as loaded, and what it allocates to start), load = boot - min, after
= boot - after. The tcpserve processes are in "load" alike for every binary.

The network services (db/services.d: dhcp, mdns, sshd, ...) are removed from
the image's copy, so that only the stack is measured; --services keeps them.
--profile m68k sets the mbuf pool as the m68k build has it by default
(MBUF_CONF INITIAL=2, CHUNK=64, CLCHUNK=4, MAXMEM=1024); "default" leaves the
binary's own (larger on 64-bit since 2026).

    memcost.py [--arostcp FILE] [--image DIR] [--profile m68k|default]
               [--conns 8] [--bytes 2000000] [--delay 20] [--services] [--out DIR]
Needs sudo -n for tc.
"""
import argparse, json, os, socket, subprocess, sys, threading, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tests", "tcp"))
import run_tcp

PORT = 7600
SYSROOT = os.path.expanduser("~/aros-build-ipv6-hosted-claude/bin/linux-x86_64/AROS/Developer")
# one variable per item: "MBUF_CONF INITIAL=2", "MBUF_CONF CHUNK=64", ...
M68K_MBUF = ("MBUF_CONF INITIAL=2", "MBUF_CONF CHUNK=64", "MBUF_CONF CLCHUNK=4", "MBUF_CONF MAXMEM=1024")


M68K_CC = os.path.expanduser("~/aros-build-emu68-m68k/bin/linux-x86_64/tools/crosstools/m68k-aros-gcc")
M68K_SYSROOT = os.path.expanduser("~/aros-build-hist-m68k/bin/amiga-m68k/AROS/Developer")


def build(out, name, src, amiga=False):
    exe = os.path.join(out, name)
    cc, sysroot = (M68K_CC, M68K_SYSROOT) if amiga else (run_tcp.CROSS, SYSROOT)
    # -fno-common: AROS's ELF loader takes no COMMON symbols (an uninitialised
    # global such as SocketBase is one by default with the m68k GCC 6)
    subprocess.run([cc, "--sysroot", sysroot, "-std=gnu99", "-O2", "-Wall", "-Wno-pointer-sign",
                    "-Wno-volatile-register-var", "-fno-common", "-o", exe, src], check=True)
    return exe


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", default=os.path.expanduser("~/aros-build-ipv6-hosted-claude/bin/linux-x86_64/AROS"))
    ap.add_argument("--arostcp")
    ap.add_argument("--profile", choices=("m68k", "default"), default="m68k")
    ap.add_argument("--conns", type=int, default=8)
    ap.add_argument("--bytes", type=int, default=2000000)
    ap.add_argument("--delay", type=int, default=20)
    ap.add_argument("--services", action="store_true")
    ap.add_argument("--config", action="append", default=[],
                    help="a line for db/general.config (repeatable), e.g. PROTOCOLS=INET")
    ap.add_argument("--amiga", action="store_true",
                    help="AROS m68k on an emulated Amiga (tools/amiga-run.sh: A3000, 68030, A2065 on aros0), "
                         "the m68k build's own mbuf defaults (--profile is ignored); --arostcp is an m68k binary")
    ap.add_argument("--out", default=os.path.join(HERE, "out", "mem-" + time.strftime("%Y%m%d-%H%M%S")))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    if a.amiga:
        a.profile = "default"
    snap = build(a.out, "memsnap", os.path.join(HERE, "memsnap.c"), a.amiga)
    serve = build(a.out, "tcpserve", os.path.join(ROOT, "tests", "tcp", "tcpserve.c"), a.amiga)
    subprocess.run([os.path.join(ROOT, "tools", "tap-up.sh")], check=True, stdout=subprocess.DEVNULL)
    run_tcp.kill_strays()
    run_tcp.tc_clear()
    run_tcp.tc_delay(a.delay)
    db = "SYS:System/Network/AROSTCP/db"
    script = os.path.join(a.out, "mem.script")
    with open(script, "w") as f:
        f.write("Wait 3\nC:memsnap boot >SYS:out/mem.log\n")
        if not a.services:
            f.write("Delete >NIL: %s/services.d/#? QUIET\n" % db)
        for line in a.config:
            f.write("Echo \"%s\" >>%s/general.config\n" % (line, db))
        if a.profile == "m68k":
            for line in M68K_MBUF:
                f.write("Echo \"%s\" >>%s/general.config\n" % (line, db))
        f.write("Execute SYS:System/Network/AROSTCP/S/startnet\nWait 10\n")
        f.write("C:memsnap idle >>SYS:out/mem.log\n")
        f.write("Run >NIL: C:memsnap load 900 SYS:out/stop >SYS:out/load.log\n")
        # each server in a script of its own that marks its end: AROS itself
        # writes the marks (a file the host puts in the emulated Amiga's
        # directory volume is not seen while the volume caches the directory)
        for i in range(a.conns):
            f.write("Echo >T:serve%d \"C:tcpserve 4 %d recv 0 >SYS:out/serve%d.log\"\n" % (i, PORT + i, i))
            f.write("Echo >>T:serve%d \"Echo >SYS:out/done%d ok\"\n" % (i, i))
            f.write("Run >NIL: Execute T:serve%d\n" % i)
        for i in range(a.conns):
            f.write("Lab wait%d\nIf NOT EXISTS SYS:out/done%d\n  Wait 1\n  Skip wait%d BACK\nEndIf\n" % (i, i, i))
        f.write("Echo >SYS:out/stop stop\n")
        f.write("Wait 3\nC:memsnap after >>SYS:out/mem.log\nWait 2\n")
    if a.amiga:
        env = dict(os.environ, AMIGA_TAP_IP=run_tcp.AROS_IP, AMIGA_RUN_TIMEOUT="900")
        if a.arostcp:
            env["AMIGA_AROSTCP"] = os.path.abspath(a.arostcp)
        runner = "amiga-run.sh"
    else:
        env = dict(os.environ, AROS_HOSTED_IMAGE=a.image, AROS_TAP_IP=run_tcp.AROS_IP, AROS_RUN_TIMEOUT="600")
        if a.arostcp:
            env["AROS_AROSTCP"] = os.path.abspath(a.arostcp)
        runner = "hosted-run.sh"
    boot = subprocess.Popen([os.path.join(ROOT, "tools", runner), os.path.join(a.out, "aros"), script,
                             snap, serve], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    socks, err = [], None
    deadline = time.time() + (240 if a.amiga else 120)
    for i in range(a.conns):
        while True:
            try:
                c = socket.create_connection((run_tcp.AROS_IP, PORT + i), timeout=2)
                c.settimeout(120)       # a window kept shut a while is not an error
                socks.append(c)
                break
            except OSError:
                if time.time() > deadline:
                    err = "no connection to port %d" % (PORT + i)
                    break
                time.sleep(0.5)
        if err:
            break
    done = [False] * len(socks)
    why = [None] * len(socks)
    took = [None] * len(socks)

    def send(i, c):
        chunk, sent, t0 = b"m" * 65536, 0, time.monotonic()
        try:
            while sent < a.bytes:
                c.sendall(chunk)
                sent += len(chunk)
            c.shutdown(socket.SHUT_WR)
            c.settimeout(120)
            while c.recv(4096):
                pass
            done[i] = True
            took[i] = round(time.monotonic() - t0, 1)
        except OSError as e:
            why[i] = "%s after %d bytes, %.1f s" % (e, sent, time.monotonic() - t0)
        c.close()

    threads = [threading.Thread(target=send, args=(i, c)) for i, c in enumerate(socks)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    out_text = boot.communicate()[0]
    run_tcp.tc_clear()
    vals = {}
    for name in ("mem.log", "load.log"):
        try:
            for line in open(os.path.join(a.out, "aros", "out", name)):
                p = line.split()
                if len(p) >= 3:
                    vals[p[0]] = [int(x) for x in p[1:]]
        except OSError:
            pass
    res = {"arostcp": a.arostcp or "(image)", "machine": "amiga-m68k" if a.amiga else "hosted-x86_64",
           "profile": a.profile, "services": a.services, "config": a.config,
           "conns": a.conns, "bytes_each": a.bytes, "error": err, "all_done": all(done) and bool(done),
           "conn_seconds": took, "conn_errors": [w for w in why if w],
           "raw": vals, "boot": "ok" if "finished" in out_text else "did not finish"}
    if "boot" in vals and "idle" in vals:
        b = vals["boot"][0]
        res["rest_kb"] = round((b - vals["idle"][0]) / 1024, 1)
        if "load" in vals and len(vals["load"]) >= 3:
            res["load_kb"] = round((b - vals["load"][2]) / 1024, 1)
        if "after" in vals:
            res["after_kb"] = round((b - vals["after"][0]) / 1024, 1)
    # the bench's own checks: the snapshots were taken and every connection finished
    res["ok"] = err is None and res["all_done"] and all(k in res for k in ("rest_kb", "load_kb", "after_kb"))
    json.dump(res, open(os.path.join(a.out, "result.json"), "w"), indent=1)
    print(json.dumps({k: v for k, v in res.items() if k != "raw"}, indent=1))


if __name__ == "__main__":
    main()
