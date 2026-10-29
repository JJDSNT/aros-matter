#!/usr/bin/env python3
"""RFC 4191 bench: the host is two routers on the tap; AROS reports its routes.

  tests/ipv6/rfc4191.py [--image DIR] [--arostcp FILE] [--out DIR]

The host adds fe80::4d54:a and fe80::4d54:b to aros0 and, once AROS says
"P:start", runs rasend.py (as root, for raw ICMPv6 with hop limit 255) on
the phase schedule. rtcheck on AROS prints the gateway it has for a set of
destinations in each phase; this script compares them with EXPECT.
"""
import argparse, os, re, socket, struct, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
CROSS = os.environ.get("AROS_CROSS",
    os.path.expanduser("~/aros-midihub/build-aros-linux/bin/linux-x86_64/tools/crosstools/x86_64-aros-gcc"))
IFACE, A, B = "aros0", "fe80::4d54:a", "fe80::4d54:b"
P = "2001:db8:4d54:"
D10, D12, D13, D99, D14, D15, D20, D21, DEF = (P + "10::1", P + "12::1", P + "13::1", P + "99::1",
                                              P + "14::1", P + "15::1", P + "20::1", P + "21::1",
                                              "2001:db8:ffff::1")
RELOAD = 14
# phase -> {destination: expected gateway or "none"}; destinations not listed are not checked
EXPECT = {
    0: {D10: A},
    1: {D10: "none"},
    2: {D12: B},
    3: {D12: A},
    4: {D12: "none", D13: B, D99: A},
    5: {D14: "none", D15: "none", D13: "none", D99: "none"},
    6: {DEF: B},
    7: {DEF: A},
    8: {DEF: "none"},
    9: {DEF: A},
    10: {DEF: "none"},
    11: {D20: A},
    12: {D20: "none"},
    13: {DEF: A, D21: A},
    14: {DEF: A, D21: A},
    15: {D21: "none"},
}
NAMES = {
    0: "RIO installs its route (router lifetime 0)", 1: "RIO lifetime 0 removes it",
    2: "more preferred of two routers wins", 3: "the other takes over when it withdraws",
    4: "longest prefix is used", 5: "reserved preference / bad length ignored",
    6: "more preferred default router wins", 7: "other default router takes over",
    8: "router lifetime 0 removes the default", 9: "::/0 RIO overrides router lifetime",
    10: "::/0 RIO lifetime 0 removes the default", 11: "short-lived RIO installed",
    12: "short-lived RIO expires", 13: "default and RIO route before reload",
    14: "default and RIO route learned again after an in-place reload", 15: "cleanup",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", default=os.path.expanduser("~/aros-build-ipv6-hosted/bin/linux-x86_64/AROS"))
    ap.add_argument("--arostcp")
    ap.add_argument("--out", default=os.path.join(HERE, "out", "rfc4191-" + time.strftime("%Y%m%d-%H%M%S")))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    exe = os.path.join(a.out, "rtcheck")
    subprocess.run([CROSS, "-std=gnu99", "-O2", "-Wall", "-Wno-pointer-sign", "-o", exe,
                    os.path.join(HERE, "rtcheck.c")], check=True)
    subprocess.run([os.path.join(ROOT, "tools", "tap-up.sh")], check=True, stdout=subprocess.DEVNULL)
    for addr in (A, B):
        subprocess.run(["sudo", "ip", "-6", "addr", "replace", addr + "/64", "dev", IFACE, "nodad"], check=True)

    # wait for P:start on the mDNS group, then start the routers
    idx = socket.if_nametoindex(IFACE)
    lst = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
    lst.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    lst.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    lst.bind(("::", 5353))
    lst.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_JOIN_GROUP,
                   socket.inet_pton(socket.AF_INET6, "ff02::fb") + struct.pack("@I", idx))
    script = os.path.join(a.out, "run.script")
    with open(script, "w") as f:
        f.write("Execute SYS:System/Network/AROSTCP/S/startnet\nWait 4\n")
        if os.environ.get("RTCHECK_DEBUG"):
            f.write("SetEnv RTCHECK_DEBUG 1\n")
        f.write("C:rtcheck eth0 %d %d >SYS:out/rtcheck.log\n" % (len(EXPECT), RELOAD))
    env = dict(os.environ, AROS_HOSTED_IMAGE=a.image, AROS_TAP_IP="192.168.166.2", AROS_RUN_TIMEOUT="140")
    if a.arostcp:
        env["AROS_AROSTCP"] = os.path.abspath(a.arostcp)
    boot = subprocess.Popen([os.path.join(ROOT, "tools", "hosted-run.sh"), os.path.join(a.out, "boot"), script, exe],
                            env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    sender = None
    deadline = time.time() + 60
    while time.time() < deadline and sender is None:
        lst.settimeout(1.0)
        try:
            data, _ = lst.recvfrom(256)
        except socket.timeout:
            continue
        if data == b"P:start":
            sender = subprocess.Popen(["sudo", sys.executable, os.path.join(HERE, "rasend.py"), IFACE, repr(time.time())])
    boot.wait()
    if sender:
        sender.wait()

    log = os.path.join(a.out, "boot", "out", "rtcheck.log")
    got = {}
    for line in open(log).read().splitlines() if os.path.exists(log) else []:
        m = re.match(r"phase (\d+) (\S+) (\S+)$", line)
        if m:
            got.setdefault(int(m.group(1)), {})[m.group(2)] = m.group(3)
    failed = 0
    with open(os.path.join(a.out, "report.txt"), "w") as rep:
        for p in sorted(EXPECT):
            bad = {d: (w, got.get(p, {}).get(d, "missing")) for d, w in EXPECT[p].items()
                   if got.get(p, {}).get(d, "missing") != w}
            line = "%s  phase %2d %s%s" % ("PASS" if not bad else "FAIL", p, NAMES[p],
                   "" if not bad else "  " + "; ".join("%s want %s got %s" % (d, w, g) for d, (w, g) in bad.items()))
            failed += bool(bad)
            print(line); rep.write(line + "\n")
        s = "arostcp=%s phases=%d failed=%d" % (a.arostcp or "(image)", len(EXPECT), failed)
        print(s); rep.write(s + "\n")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
