#!/usr/bin/env python3
"""
arp_stale_probe.py - does AROS notice that a neighbour's MAC changed?

AROS (udptick) sends a UDP datagram to the host every 200 ms. After
--change s the host gives its tap (aros0) another MAC, without announcing
it (arp_notify 0): AROS's ARP entry for the host is stale, and what it
sends to the old MAC the host's tap drops. The bench reports the gap in
the datagrams that reached the host, and whether they came back before
the end. An ARP entry that is never revalidated keeps the old MAC until
it expires (20 min); one checked as IPv6's neighbour unreachability
detection does (RFC 4861 section 7.3; RFC 1122 section 2.3.2.1) comes
back within some 40 s.

    arp_stale_probe.py [--arostcp FILE] [--image DIR] [--secs 120] [--change 20] [--out DIR]
Needs sudo -n (ip link, sysctl).
"""
import argparse, json, os, socket, subprocess, sys, threading, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tests", "tcp"))
import run_tcp

TAP, HOST, AROS, PORT = "aros0", "192.168.166.1", "192.168.166.2", 7040
NEWMAC = "02:00:00:00:00:42"


def sh(*a):
    return subprocess.run(["sudo", "-n"] + list(a), capture_output=True, text=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", default=os.environ.get("AROS_HOSTED_IMAGE",
        os.path.expanduser("~/aros-build-ipv6-hosted-claude/bin/linux-x86_64/AROS")))
    ap.add_argument("--arostcp")
    ap.add_argument("--secs", type=int, default=120)
    ap.add_argument("--change", type=int, default=20, help="s after the first datagram")
    ap.add_argument("--out", default=os.path.join(HERE, "out", "arpstale-" + time.strftime("%Y%m%d-%H%M%S")))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    exe = os.path.join(a.out, "udptick")
    subprocess.run([run_tcp.CROSS, "-std=gnu99", "-O2", "-Wall", "-o", exe, os.path.join(HERE, "udptick.c")],
                   check=True, capture_output=True)
    subprocess.run([os.path.join(ROOT, "tools", "tap-up.sh")], check=True, stdout=subprocess.DEVNULL)
    oldmac = open("/sys/class/net/%s/address" % TAP).read().strip()
    sh("sysctl", "-w", "net.ipv4.conf.%s.arp_notify=0" % TAP)
    got = []
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind((HOST, PORT))
    s.settimeout(0.5)
    stop = threading.Event()

    def rx():
        while not stop.is_set():
            try:
                d, _ = s.recvfrom(64)
                got.append((time.monotonic(), int(d)))
            except (socket.timeout, ValueError):
                pass
    threading.Thread(target=rx, daemon=True).start()
    script = os.path.join(a.out, "stale.script")
    with open(script, "w") as f:
        f.write("Execute SYS:System/Network/AROSTCP/S/startnet\nWait 10\n")
        f.write("C:udptick %s %d %d >SYS:out/tick.log\n" % (HOST, PORT, a.secs))
    env = dict(os.environ, AROS_HOSTED_IMAGE=a.image, AROS_TAP_IP=AROS, AROS_RUN_TIMEOUT=str(a.secs + 120))
    if a.arostcp:
        env["AROS_AROSTCP"] = os.path.abspath(a.arostcp)
    aros = subprocess.Popen([os.path.join(ROOT, "tools", "hosted-run.sh"), os.path.join(a.out, "aros"), script, exe],
                            env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    changed = None
    try:
        t0 = time.monotonic()
        while not got and time.monotonic() - t0 < 120:
            time.sleep(0.2)
        if got:
            time.sleep(max(0, a.change - (time.monotonic() - got[0][0])))
            r = sh("ip", "link", "set", "dev", TAP, "address", NEWMAC)
            changed = time.monotonic() if r.returncode == 0 else None
            if r.returncode:
                print("ip link set address failed:", r.stderr.strip())
        out = aros.communicate()[0]
    finally:
        stop.set()
        sh("ip", "link", "set", "dev", TAP, "address", oldmac)
    res = {"boot": "ok" if "finished" in out else "did not finish", "received": len(got)}
    if changed and got:
        before = [t for t, n in got if t < changed]
        after = [t for t, n in got if t >= changed]
        res["last_before_change_s"] = round(changed - before[-1], 2) if before else None
        res["first_after_change_s"] = round(after[0] - changed, 2) if after else None
        res["after_change"] = len(after)
    res["sanity"] = {"datagrams_before": bool(got) and changed is not None and any(t < changed for t, n in got)}
    res["sanity"]["ok"] = all(res["sanity"].values())
    json.dump(res, open(os.path.join(a.out, "result.json"), "w"), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
