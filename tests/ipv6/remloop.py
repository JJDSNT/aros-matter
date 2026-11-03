#!/usr/bin/env python3
"""Interface removal under load: tests/ipv6/remloop.py [--image DIR] [--arostcp FILE] [--runs N] [--out DIR]

AROS runs with two interfaces (eth0 on aros0, eth1 on aros1); remloop.c takes
eth1 out of db/interfaces and reloads, puts it back and reloads, 15 times per
boot. A run passes if every reload answers rc=0, the loop gets to "done", and
the serial log has no trap and no TLSF corruption report. Before the
sana_connect() fix about one boot in two crashed (a freed request linked on
the SANA-II reply port, or the heap's free lists overwritten).
"""
import argparse, os, re, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
CROSS = os.environ.get("AROS_CROSS",
    os.path.expanduser("~/aros-midihub/build-aros-linux/bin/linux-x86_64/tools/crosstools/x86_64-aros-gcc"))
ITER = 15


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", default=os.path.expanduser("~/aros-build-ipv6-hosted-claude/bin/linux-x86_64/AROS"))
    ap.add_argument("--arostcp")
    ap.add_argument("--runs", type=int, default=4)
    ap.add_argument("--out", default=os.path.join(HERE, "out", "remloop-" + time.strftime("%Y%m%d-%H%M%S")))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    exe = os.path.join(a.out, "remloop")
    subprocess.run([CROSS, "-std=gnu99", "-O2", "-Wall", "-Wno-pointer-sign", "-o", exe,
                    os.path.join(HERE, "remloop.c")], check=True)
    for n in ("0", "1"):
        subprocess.run([os.path.join(ROOT, "tools", "tap-up.sh"), n], check=True, stdout=subprocess.DEVNULL)
    script = os.path.join(a.out, "run.script")
    with open(script, "w") as f:
        f.write("Execute SYS:System/Network/AROSTCP/S/startnet\nWait 6\n")
        f.write("C:remloop eth1 %d >SYS:out/remloop.log\n" % ITER)
    env = dict(os.environ, AROS_HOSTED_IMAGE=a.image, AROS_TAP_IP="192.168.166.2",
               AROS_TAP2_IP="192.168.167.2", AROS_RUN_TIMEOUT="300")
    if a.arostcp:
        env["AROS_AROSTCP"] = os.path.abspath(a.arostcp)
    failed = 0
    with open(os.path.join(a.out, "report.txt"), "w") as rep:
        for r in range(a.runs):
            work = os.path.join(a.out, "boot%d" % r)
            subprocess.run([os.path.join(ROOT, "tools", "hosted-run.sh"), work, script, exe],
                           env=env, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
            log = os.path.join(work, "out", "remloop.log")
            lines = open(log).read().splitlines() if os.path.exists(log) else []
            serial = open(os.path.join(work, "serial.log"), errors="replace").read()
            rcs = re.findall(r"^iter \d+ (?:removed|added) rc=(-?\d+)$", "\n".join(lines), re.M)
            crash = "Trap signal" in serial or "[Kernel:TLSF]" in serial
            ok = (not crash and len(rcs) == 2 * ITER and all(c == "0" for c in rcs) and
                  lines[-1:] == ["done"])
            failed += not ok
            line = "%s  boot %d: %d reloads, %s%s" % ("PASS" if ok else "FAIL", r, len(rcs),
                   "crash" if crash else "no crash", "" if lines[-1:] == ["done"] else ", did not finish")
            print(line); rep.write(line + "\n")
        s = "arostcp=%s boots=%d failed=%d" % (a.arostcp or "(image)", a.runs, failed)
        print(s); rep.write(s + "\n")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
