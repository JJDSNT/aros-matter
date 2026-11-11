#!/usr/bin/env python3
"""
acd_reprobe_probe.py - an address left duplicated comes back once its
owner is gone (RFC 5227 conflict detection, probed again once a minute).

The host holds 192.168.166.60 on its tap; AROS (aflagwatch) adds it as an
alias of eth0 and records its state: duplicated after its probes. After
--release s the host gives the address up; AROS should probe it again
within a minute and have it ready. Before the change it stayed duplicated.

    acd_reprobe_probe.py [--arostcp FILE] [--image DIR] [--release 20] [--secs 110] [--out DIR]
Needs sudo -n (ip addr).
"""
import argparse, json, os, re, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tests", "tcp"))
import run_tcp

TAP, AROS, ADDR = "aros0", "192.168.166.2", "192.168.166.60"


def sh(*a):
    return subprocess.run(["sudo", "-n"] + list(a), capture_output=True, text=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", default=os.environ.get("AROS_HOSTED_IMAGE",
        os.path.expanduser("~/aros-build-ipv6-hosted-claude/bin/linux-x86_64/AROS")))
    ap.add_argument("--arostcp")
    ap.add_argument("--release", type=int, default=20, help="s after AROS answers pings")
    ap.add_argument("--secs", type=int, default=110, help="how long aflagwatch watches")
    ap.add_argument("--out", default=os.path.join(HERE, "out", "reprobe-" + time.strftime("%Y%m%d-%H%M%S")))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    exe = os.path.join(a.out, "aflagwatch")
    # SIOCGIFAFLAG_IN is in this tree's headers: compile against its build
    sysroot = os.path.join(os.path.dirname(a.image.rstrip("/")), "AROS", "Developer")
    subprocess.run([run_tcp.CROSS, "--sysroot", sysroot, "-std=gnu99", "-O2", "-Wall", "-Wno-pointer-sign",
                    "-o", exe, os.path.join(HERE, "aflagwatch.c")], check=True, capture_output=True)
    subprocess.run([os.path.join(ROOT, "tools", "tap-up.sh")], check=True, stdout=subprocess.DEVNULL)
    sh("ip", "addr", "add", ADDR + "/32", "dev", TAP)
    script = os.path.join(a.out, "reprobe.script")
    with open(script, "w") as f:
        f.write("Execute SYS:System/Network/AROSTCP/S/startnet\nWait 10\n")
        f.write("C:aflagwatch eth0 %s %d >SYS:out/watch.log\n" % (ADDR, a.secs))
    env = dict(os.environ, AROS_HOSTED_IMAGE=a.image, AROS_TAP_IP=AROS, AROS_RUN_TIMEOUT=str(a.secs + 90))
    if a.arostcp:
        env["AROS_AROSTCP"] = os.path.abspath(a.arostcp)
    released = None
    try:
        aros = subprocess.Popen([os.path.join(ROOT, "tools", "hosted-run.sh"), os.path.join(a.out, "aros"), script, exe],
                                env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        t0 = time.monotonic()
        while time.monotonic() - t0 < 90 and subprocess.run(["ping", "-c", "1", "-W", "1", AROS],
                                                              capture_output=True).returncode:
            time.sleep(1)
        up = time.monotonic()
        time.sleep(10 + a.release)          # aflagwatch starts ~10 s after AROS is up
        sh("ip", "addr", "del", ADDR + "/32", "dev", TAP)
        released = time.monotonic() - up - 10   # on aflagwatch's clock, roughly
        out = aros.communicate()[0]
    finally:
        sh("ip", "addr", "del", ADDR + "/32", "dev", TAP)
    p = os.path.join(a.out, "aros", "out", "watch.log")
    events = [(float(m.group(1)), int(m.group(2))) for m in
              re.finditer(r"t=([\d.]+) flags=(-?\d+)", open(p).read())] if os.path.exists(p) else []
    dup = [t for t, f in events if f == 2]
    back = [t for t, f in events if f == 0 and dup and t > dup[0]]
    res = {"boot": "ok" if "finished" in out else "did not finish", "events": events,
           "released_at_s": round(released, 1) if released is not None else None,
           "duplicated_at_s": dup[0] if dup else None, "ready_again_at_s": back[0] if back else None}
    res["sanity"] = {"duplicated_first": bool(dup) and dup[0] < (released or 0)}
    res["sanity"]["ok"] = all(res["sanity"].values())
    json.dump(res, open(os.path.join(a.out, "result.json"), "w"), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
