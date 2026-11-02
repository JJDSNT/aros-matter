#!/usr/bin/env python3
"""An interface going away while an application holds the dynamic database:
tests/dns/dnsgone.py [--image DIR] [--arostcp FILE] [--out DIR]

eth0 and eth1 (tap.device units 0 and 1) are configured with DNS=192.168.166.53
and DNS=192.168.167.53.
dnsgone.c holds the database with ClearDynDomain(), removes eth1 by an
in-place reload, and releases it. Expected: the reload finishes while the
database is held (the stack does not wait for it), and once released eth1's
server is no longer in the list while eth0's, set again by the reload, is.
"""
import argparse, os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
CROSS = os.environ.get("AROS_CROSS",
    os.path.expanduser("~/aros-midihub/build-aros-linux/bin/linux-x86_64/tools/crosstools/x86_64-aros-gcc"))
SERVER, KEPT = "192.168.167.53", "192.168.166.53"
EXPECT = ["before 1", "reload done", "reload replied", "after 0", "kept 1"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", default=os.path.expanduser("~/aros-build-ipv6-hosted-claude/bin/linux-x86_64/AROS"))
    ap.add_argument("--arostcp")
    ap.add_argument("--out", default=os.path.join(HERE, "out", "dnsgone-" + time.strftime("%Y%m%d-%H%M%S")))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    exe = os.path.join(a.out, "dnsgone")
    subprocess.run([CROSS, "-std=gnu99", "-O2", "-Wall", "-Wno-pointer-sign", "-o", exe,
                    os.path.join(HERE, "dnsgone.c")], check=True)
    for n in ("0", "1"):
        subprocess.run([os.path.join(ROOT, "tools", "tap-up.sh"), n], check=True, stdout=subprocess.DEVNULL)
    script = os.path.join(a.out, "run.script")
    with open(script, "w") as f:
        for n, ip, dns in ((0, "192.168.166.2", KEPT), (1, "192.168.167.2", SERVER)):
            f.write('Echo >>SYS:System/Network/AROSTCP/db/interfaces "eth%d DEV=DEVS:Networks/tap.device UNIT=%d '
                    'IP=%s NETMASK=255.255.255.0 DNS=%s UP"\n' % (n, n, ip, dns))
        f.write("Execute SYS:System/Network/AROSTCP/S/startnet\nWait 6\n")
        f.write("C:dnsgone eth1 %s %s >SYS:out/dnsgone.log\n" % (SERVER, KEPT))
    env = dict(os.environ, AROS_HOSTED_IMAGE=a.image, AROS_RUN_TIMEOUT="120")
    if a.arostcp:
        env["AROS_AROSTCP"] = os.path.abspath(a.arostcp)
    subprocess.run([os.path.join(ROOT, "tools", "hosted-run.sh"), os.path.join(a.out, "boot"), script, exe],
                   env=env, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    log = os.path.join(a.out, "boot", "out", "dnsgone.log")
    got = open(log).read().split("\n") if os.path.exists(log) else []
    got = [l for l in got if l]
    failed = 0
    with open(os.path.join(a.out, "report.txt"), "w") as rep:
        for i, want in enumerate(EXPECT):
            g = got[i] if i < len(got) else "missing"
            ok = g == want
            failed += not ok
            line = "%s  want %-15s got %s" % ("PASS" if ok else "FAIL", want, g)
            print(line); rep.write(line + "\n")
        s = "arostcp=%s checks=%d failed=%d" % (a.arostcp or "(image)", len(EXPECT), failed)
        print(s); rep.write(s + "\n")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
