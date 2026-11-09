#!/usr/bin/env python3
"""zone_probe.py - one link-local address on two links (RFC 4007 section 6).

The host has fe80::1 on both of its taps (aros0, aros1: two links, two
neighbours with the same address and different MACs). AROS (zonesend) sends
UDP datagrams to fe80::1%eth0 and fe80::1%eth1 by turns. From captures of
both taps it reports, for each datagram, the tap it left by and the MAC it
was sent to: each must leave by its own link, to that tap's MAC.

    zone_probe.py [--arostcp FILE] [--image DIR] [--rounds 4] [--out DIR]
Needs sudo -n for ip and tcpdump, and the second tap (tools/tap-up.sh 1).
"""
import argparse, json, os, re, socket, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
CROSS = os.environ.get("AROS_CROSS",
    os.path.expanduser("~/aros-midihub/build-aros-linux/bin/linux-x86_64/tools/crosstools/x86_64-aros-gcc"))
ADDR = "fe80::1"
TAPS = ("aros0", "aros1")


def sh(*a, check=False):
    return subprocess.run(["sudo", "-n"] + list(a), capture_output=True, text=True, check=check)


def mac(dev):
    return open("/sys/class/net/%s/address" % dev).read().strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", default=os.path.expanduser("~/aros-build-ipv6-hosted-claude/bin/linux-x86_64/AROS"))
    ap.add_argument("--arostcp")
    ap.add_argument("--rounds", type=int, default=4)
    ap.add_argument("--tcp", action="store_true", help="TCP connections (a host listener on [::]:9999) instead of UDP")
    ap.add_argument("--out", default=os.path.join(HERE, "out", "zone-" + time.strftime("%Y%m%d-%H%M%S")))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    exe = os.path.join(a.out, "zonesend")
    subprocess.run([CROSS, "-std=gnu99", "-O2", "-Wall", "-o", exe, os.path.join(HERE, "zonesend.c")], check=True)
    subprocess.run([os.path.join(ROOT, "tools", "tap-up.sh")], check=True, stdout=subprocess.DEVNULL)
    subprocess.run([os.path.join(ROOT, "tools", "tap-up.sh"), "1"], check=True, stdout=subprocess.DEVNULL)
    for t in TAPS:
        sh("ip", "-6", "addr", "add", ADDR + "/64", "dev", t, "nodad")
    dumps = {}
    for t in TAPS:
        pcap = os.path.join(a.out, t + ".pcap")
        dumps[t] = (pcap, subprocess.Popen(["sudo", "-n", "tcpdump", "-i", t, "-n", "-e", "-w", pcap,
                                            "ip6 and port 9999"],
                                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    got = []
    if a.tcp:
        import socket, threading
        ls = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        ls.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        ls.bind(("::", 9999))
        ls.listen(8)

        def serve():
            while True:
                c, peer = ls.accept()
                c.settimeout(5)
                try:
                    got.append((c.recv(64).decode(errors="replace"), peer[3]))
                except OSError:
                    pass
                c.close()
        threading.Thread(target=serve, daemon=True).start()
    time.sleep(1)
    script = os.path.join(a.out, "zone.script")
    with open(script, "w") as f:
        f.write("Execute SYS:System/Network/AROSTCP/S/startnet\nWait 6\n")
        f.write("C:zonesend %s eth0 eth1 %d%s >SYS:out/zonesend.log\n" % (ADDR, a.rounds, " tcp" if a.tcp else ""))
    env = dict(os.environ, AROS_HOSTED_IMAGE=a.image, AROS_TAP_IP="192.168.166.2", AROS_TAP2_IP="192.168.167.2",
               AROS_RUN_TIMEOUT="120")
    if a.arostcp:
        env["AROS_AROSTCP"] = os.path.abspath(a.arostcp)
    try:
        subprocess.run([os.path.join(ROOT, "tools", "hosted-run.sh"), os.path.join(a.out, "aros"), script, exe],
                       env=env, capture_output=True, text=True)
    finally:
        time.sleep(1)
        for t, (pcap, p) in dumps.items():
            for pid in subprocess.run(["pgrep", "-P", str(p.pid)], capture_output=True, text=True).stdout.split():
                sh("kill", "-INT", pid)
            p.wait(timeout=10)
        for t in TAPS:
            sh("ip", "-6", "addr", "del", ADDR + "/64", "dev", t)
    seen = []
    want = {"eth0": ("aros0", mac("aros0")), "eth1": ("aros1", mac("aros1"))}
    if a.tcp:
        # the host's view: which tap (scope id) each connection came in by
        idx = {socket.if_nametoindex(t): t for t in TAPS}
        for msg, scope in got:
            seen.append({"tap": idx.get(scope, str(scope)), "dst_mac": want.get(msg.split()[0], ("", ""))[1] if msg else "", "msg": msg})
        right = [s for s in seen if s["msg"] and want[s["msg"].split()[0]][0] == s["tap"]]
    else:
        for t in TAPS:
            txt = subprocess.run(["sudo", "-n", "tcpdump", "-n", "-e", "-A", "-r", dumps[t][0]], capture_output=True, text=True).stdout
            for m in re.finditer(r"> ([0-9a-f:]{17}),.*?\n.*?(eth[01] \d+)", txt, re.S):
                seen.append({"tap": t, "dst_mac": m.group(1), "msg": m.group(2)})
        right = [s for s in seen if want[s["msg"].split()[0]] == (s["tap"], s["dst_mac"])]
    try:
        log = open(os.path.join(a.out, "aros", "out", "zonesend.log")).read().splitlines()
    except OSError:
        log = []
    res = {"sent": a.rounds * 2, "seen": seen, "right": len(right), "zonesend": log,
           "ok": len(seen) == a.rounds * 2 and len(right) == a.rounds * 2}
    json.dump(res, open(os.path.join(a.out, "result.json"), "w"), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
