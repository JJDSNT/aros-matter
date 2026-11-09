#!/usr/bin/env python3
"""
clock_probe.py - does AROS hosted's clock keep up with the host's?

AROS (clocksend) sends its uptime (GetUpTime(), ms) to the host every 250 ms
over UDP for SECS seconds; the host stamps each arrival with its own
monotonic clock. The offset between the two should stay put; a step in it
is time the AROS clock lost (hosted timer.device ticks that never counted).
--load N keeps N host CPUs busy meanwhile, so that the AROS process is
descheduled more often. --timer FILE boots with that timer.device.

    clock_probe.py [--image DIR] [--timer FILE] [--secs 60] [--load 0] [--out DIR]
"""
import argparse, json, multiprocessing, os, shutil, socket, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import run_tcp

PORT = 7501


def burn(stop):
    while not stop.is_set():
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", default=os.path.expanduser("~/aros-build-ipv6-hosted-claude/bin/linux-x86_64/AROS"))
    ap.add_argument("--timer")
    ap.add_argument("--secs", type=int, default=60)
    ap.add_argument("--load", type=int, default=0)
    ap.add_argument("--out", default=os.path.join(ROOT, "tests", "tcp", "out", "clock-" + time.strftime("%Y%m%d-%H%M%S")))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    exe = os.path.join(a.out, "clocksend")
    subprocess.run([run_tcp.CROSS, "-std=gnu99", "-O2", "-Wall", "-Wno-pointer-sign", "-o", exe,
                    os.path.join(HERE, "clocksend.c")], check=True)
    subprocess.run([os.path.join(ROOT, "tools", "tap-up.sh")], check=True, stdout=subprocess.DEVNULL)
    image = a.image
    if a.timer:                         # a copy of the image with that timer.device
        image = os.path.join(a.out, "image")
        shutil.rmtree(image, ignore_errors=True)
        shutil.copytree(a.image, image, symlinks=True)
        shutil.copy(a.timer, os.path.join(image, "boot", "linux", "Devs", "timer.device"))
    u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    u.bind(("0.0.0.0", PORT))
    u.settimeout(1)
    script = os.path.join(a.out, "clock.script")
    with open(script, "w") as f:
        f.write("Execute SYS:System/Network/AROSTCP/S/startnet\nWait 4\n")
        f.write("C:clocksend 192.168.166.1 %d %d >SYS:out/clock.log\n" % (PORT, a.secs))
    env = dict(os.environ, AROS_HOSTED_IMAGE=image, AROS_TAP_IP=run_tcp.AROS_IP, AROS_RUN_TIMEOUT=str(a.secs + 90))
    stop = multiprocessing.Event()
    burners = [multiprocessing.Process(target=burn, args=(stop,), daemon=True) for _ in range(a.load)]
    for b in burners:
        b.start()
    boot = subprocess.Popen([os.path.join(ROOT, "tools", "hosted-run.sh"), os.path.join(a.out, "aros"), script, exe],
                            env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    pts = []
    while boot.poll() is None:
        try:
            d = u.recv(64)
        except socket.timeout:
            continue
        pts.append((time.monotonic() * 1000, int(d)))
    stop.set()
    if a.timer:
        shutil.rmtree(image, ignore_errors=True)
    offs = [h - g for h, g in pts]
    base = min(offs[:8]) if offs else 0
    steps = [(round((pts[i][1] - pts[0][1]) / 1000, 1), round(offs[i] - offs[i - 1], 1))
             for i in range(1, len(offs)) if offs[i] - offs[i - 1] > 50]
    res = {"samples": len(pts), "load": a.load, "timer": a.timer or "image",
           "drift_ms": round(offs[-1] - base, 1) if offs else None,
           "max_offset_ms": round(max(offs) - base, 1) if offs else None,
           "steps_over_50ms": steps,
           "ok": len(pts) >= a.secs * 3}
    json.dump(res, open(os.path.join(a.out, "result.json"), "w"), indent=1)
    print(json.dumps(res))


if __name__ == "__main__":
    main()
