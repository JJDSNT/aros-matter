#!/usr/bin/env python3
"""A static IPv6 nameserver: tests/dns/nameserver6.py [--image DIR] [--arostcp FILE] [--out DIR]

The NetDB gets a "NAMESERVER ::1" line before the stack starts; the DNS
server of the resolver's cunit tests (cunit-net-resolver --serve, from
dnstest.h) answers on ::1 for one.rdnss.test (192.0.2.77). dnslook must get
that answer through the resolver; with the line refused (IPv4-only parser)
the name is not found.
"""
import argparse, os, re, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
CROSS = os.environ.get("AROS_CROSS",
    os.path.expanduser("~/aros-midihub/build-aros-linux/bin/linux-x86_64/tools/crosstools/x86_64-aros-gcc"))
SERVER = "SYS:Developer/Debug/Tests/cunit/net/socket/cunit-net-resolver"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", default=os.path.expanduser("~/aros-build-ipv6-hosted-claude/bin/linux-x86_64/AROS"))
    ap.add_argument("--arostcp")
    ap.add_argument("--out", default=os.path.join(HERE, "out", "ns6-" + time.strftime("%Y%m%d-%H%M%S")))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    exe = os.path.join(a.out, "dnslook")
    subprocess.run([CROSS, "-std=gnu99", "-O2", "-Wall", "-Wno-pointer-sign", "-o", exe,
                    os.path.join(HERE, "dnslook.c")], check=True)
    subprocess.run([os.path.join(ROOT, "tools", "tap-up.sh")], check=True, stdout=subprocess.DEVNULL)
    script = os.path.join(a.out, "run.script")
    with open(script, "w") as f:
        f.write('Echo >>SYS:System/Network/AROSTCP/db/netdb-myhost "NAMESERVER ::1"\n')
        f.write("Execute SYS:System/Network/AROSTCP/S/startnet\nWait 6\n")
        f.write("Run >NIL: %s --serve\nWait 2\n" % SERVER)
        f.write("C:dnslook one.rdnss.test >SYS:out/dnslook.log\n")
    env = dict(os.environ, AROS_HOSTED_IMAGE=a.image, AROS_TAP_IP="192.168.166.2", AROS_RUN_TIMEOUT="120")
    if a.arostcp:
        env["AROS_AROSTCP"] = os.path.abspath(a.arostcp)
    subprocess.run([os.path.join(ROOT, "tools", "hosted-run.sh"), os.path.join(a.out, "boot"), script, exe],
                   env=env, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    log = os.path.join(a.out, "boot", "out", "dnslook.log")
    got = open(log).read().replace("dnslook\n", "", 1).strip() if os.path.exists(log) else "missing"
    ok = got == "one.rdnss.test 192.0.2.77"
    line = "%s  the static IPv6 NAMESERVER answers: %s" % ("PASS" if ok else "FAIL", got)
    print(line)
    open(os.path.join(a.out, "report.txt"), "w").write(line + "\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
