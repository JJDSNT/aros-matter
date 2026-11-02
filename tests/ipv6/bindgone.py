#!/usr/bin/env python3
"""Interface gone under bound sockets: tests/ipv6/bindgone.py [--image DIR] [--arostcp FILE] [--out DIR]

AROS runs with two interfaces (eth0 on aros0, eth1 on aros1). bindgone.c
binds sockets to eth1 - UDP/IPv4 and UDP/IPv6 with SO_BINDTODEVICE, UDP/IPv6
connected in eth1's zone, a TCP/IPv6 connection over eth1's link-local - and
then removes eth1 by an in-place reload without its db/interfaces line.
Expected: the reload removes it, every one of those sockets then gets
ENXIO (6), and the UDP/IPv6 socket works again once bound to lo0.
"""
import argparse, os, re, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
CROSS = os.environ.get("AROS_CROSS",
    os.path.expanduser("~/aros-midihub/build-aros-linux/bin/linux-x86_64/tools/crosstools/x86_64-aros-gcc"))
ENXIO = 6
EXPECT = [("before u4", "rc=1"), ("gone", "1"), ("after u4", ENXIO), ("after u6", ENXIO),
          ("after z6", ENXIO), ("after t", ENXIO), ("rebind u6", "rc=0"), ("again u6", "rc=1")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", default=os.path.expanduser("~/aros-build-ipv6-hosted-claude/bin/linux-x86_64/AROS"))
    ap.add_argument("--arostcp")
    ap.add_argument("--out", default=os.path.join(HERE, "out", "bindgone-" + time.strftime("%Y%m%d-%H%M%S")))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    exe = os.path.join(a.out, "bindgone")
    subprocess.run([CROSS, "-std=gnu99", "-O2", "-Wall", "-Wno-pointer-sign", "-o", exe,
                    os.path.join(HERE, "bindgone.c")], check=True)
    for n in ("0", "1"):
        subprocess.run([os.path.join(ROOT, "tools", "tap-up.sh"), n], check=True, stdout=subprocess.DEVNULL)
    script = os.path.join(a.out, "run.script")
    with open(script, "w") as f:
        f.write("Execute SYS:System/Network/AROSTCP/S/startnet\nWait 6\nC:bindgone eth1 >SYS:out/bindgone.log\n")
    env = dict(os.environ, AROS_HOSTED_IMAGE=a.image, AROS_TAP_IP="192.168.166.2",
               AROS_TAP2_IP="192.168.167.2", AROS_RUN_TIMEOUT="120")
    if a.arostcp:
        env["AROS_AROSTCP"] = os.path.abspath(a.arostcp)
    subprocess.run([os.path.join(ROOT, "tools", "hosted-run.sh"), os.path.join(a.out, "boot"), script, exe],
                   env=env, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    log = os.path.join(a.out, "boot", "out", "bindgone.log")
    text = open(log).read() if os.path.exists(log) else ""
    got = {}
    for line in text.splitlines():
        m = re.match(r"(\w+ \w+|gone) (.*)$", line)
        if m:
            got[m.group(1)] = m.group(2)
    failed = 0
    with open(os.path.join(a.out, "report.txt"), "w") as rep:
        for key, want in EXPECT:
            g = got.get(key, "missing")
            ok = (g == "rc=-1 errno=%d" % want if isinstance(want, int)
                  else g == want or g.startswith(want + " "))
            failed += not ok
            line = "%s  %-10s want %s got %s" % ("PASS" if ok else "FAIL", key,
                   "errno %d" % want if isinstance(want, int) else want, g)
            print(line); rep.write(line + "\n")
        s = "arostcp=%s checks=%d failed=%d" % (a.arostcp or "(image)", len(EXPECT), failed)
        print(s); rep.write(s + "\n")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
