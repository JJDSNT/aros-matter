#!/usr/bin/env python3
"""
hold_probe.py - a tap.device opener that stops reading must not stall the
unit's other openers (tap.device receive backpressure, its hold bound).

AROS runs AROSTCP on tap.device unit 0 and holdstall, a second opener that
reads one frame of ethertype 0x88b5 and then stays open without reading.
The host sends a 0x88b5 broadcast frame every 50 ms and pings AROS every
200 ms meanwhile. A frame of 0x88b5 that no read takes is held for
holdstall's reads; held for good, nothing more is read from the tap and
the pings go unanswered. With the bound (TAP_HOLD_MS) the pings are
answered.

    hold_probe.py [--tap FILE] [--image DIR] [--secs 15] [--out DIR]
--tap boots with that tap.device. Needs sudo -n (raw frames).
"""
import argparse, json, os, re, shutil, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tests", "tcp"))
import run_tcp

IFACE = run_tcp.IFACE
ETYPE = "88b5"


def ping(n, interval=0.2):
    r = subprocess.run(["ping", "-n", "-i", str(interval), "-c", str(n), "-W", "1", run_tcp.AROS_IP],
                       capture_output=True, text=True)
    loss = re.search(r"(\d+(?:\.\d+)?)% packet loss", r.stdout)
    rtt = re.search(r"= [\d.]+/([\d.]+)/([\d.]+)/", r.stdout)
    return {"sent": n, "loss_pct": float(loss.group(1)) if loss else 100.0,
            "rtt_avg_ms": float(rtt.group(1)) if rtt else None,
            "rtt_max_ms": float(rtt.group(2)) if rtt else None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", default=os.environ.get("AROS_HOSTED_IMAGE",
        os.path.expanduser("~/aros-build-ipv6-hosted-claude/bin/linux-x86_64/AROS")))
    ap.add_argument("--tap")
    ap.add_argument("--arostcp")
    ap.add_argument("--secs", type=int, default=15)
    ap.add_argument("--out", default=os.path.join(ROOT, "tests", "tap", "out", "hold-" + time.strftime("%Y%m%d-%H%M%S")))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    exe = os.path.join(a.out, "holdstall")
    subprocess.run([run_tcp.CROSS, "-std=gnu99", "-O2", "-Wall", "-o", exe,
                    os.path.join(HERE, "holdstall.c")], check=True, capture_output=True)
    subprocess.run([os.path.join(ROOT, "tools", "tap-up.sh")], check=True, stdout=subprocess.DEVNULL)
    run_tcp.kill_strays()
    run_tcp.tc_clear()
    files = [exe]
    script = os.path.join(a.out, "hold.script")
    with open(script, "w") as f:
        if a.tap:
            f.write("Copy C:tap.device DEVS:Networks/tap.device\n")
            f.write("List DEVS:Networks/tap.device LFORMAT \"%L\" >SYS:out/tap.size\n")
        f.write("Execute SYS:System/Network/AROSTCP/S/startnet\nWait 2\n")
        f.write("Run >SYS:out/holdstall.log C:holdstall 0 %s %d\n" % (ETYPE, a.secs + 40))
        f.write("Wait %d\n" % (a.secs + 45))
    if a.tap:
        # hosted-run.sh copies a file into C: under its own name
        tapdir = os.path.join(a.out, "tap")
        os.makedirs(tapdir, exist_ok=True)
        shutil.copy(a.tap, os.path.join(tapdir, "tap.device"))
        files.append(os.path.join(tapdir, "tap.device"))
    env = dict(os.environ, AROS_HOSTED_IMAGE=a.image, AROS_TAP_IP=run_tcp.AROS_IP,
               AROS_RUN_TIMEOUT=str(a.secs + 150))
    if a.arostcp:
        env["AROS_AROSTCP"] = a.arostcp
    aros = subprocess.Popen([os.path.join(ROOT, "tools", "hosted-run.sh"), os.path.join(a.out, "aros"), script] + files,
                            env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    res = {}
    # AROS up: it answers pings (holdstall opens 2 s after startnet)
    t0 = time.monotonic()
    while time.monotonic() - t0 < 90 and ping(1)["loss_pct"] > 0:
        time.sleep(1)
    time.sleep(5)
    res["before"] = ping(10)
    send = subprocess.Popen(["sudo", "-n", "python3", "-I", os.path.join(HERE, "ethsend.py"), IFACE, ETYPE,
                             "0.05", str(a.secs)], stdout=subprocess.PIPE, text=True)
    time.sleep(0.5)
    res["during"] = ping(int(a.secs / 0.2) - 5)
    res["frames_sent"] = send.communicate()[0].strip()
    res["after"] = ping(10)
    out = aros.communicate()[0]
    log = os.path.join(a.out, "aros", "out", "holdstall.log")
    res["holdstall"] = open(log).read().strip().splitlines() if os.path.exists(log) else []
    res["boot"] = "ok" if "finished" in out else "did not finish"
    # the bench checks itself: AROS answered before the frames, and
    # holdstall read its one frame and stayed open through them
    res["sanity"] = {"answered_before": res["before"]["loss_pct"] == 0,
                     "holdstall_read_one": any(l.startswith("got ") for l in res["holdstall"])}
    if a.tap:
        size = os.path.join(a.out, "aros", "out", "tap.size")
        loaded = open(size).read().strip() if os.path.exists(size) else ""
        res["sanity"]["tap_loaded"] = loaded == str(os.path.getsize(a.tap))
    res["sanity"]["ok"] = all(res["sanity"].values())
    json.dump(res, open(os.path.join(a.out, "result.json"), "w"), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
