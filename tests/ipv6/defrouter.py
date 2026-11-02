#!/usr/bin/env python3
"""Default router bench: router selection by reachability (RFC 4861
section 6.3.6, RFC 4191 sections 3.2 and 3.5).

  tests/ipv6/defrouter.py [--image DIR] [--arostcp FILE] [--out DIR]

The host is two routers on the tap (defrouter_ra.py, as root): DEAD,
preferred, advertises once and never answers; LIVE, the host's link-local,
less preferred, advertises every 2 s. rtwatch on AROS sends traffic to a
destination beyond them and prints the gateway its route has each second.
What should happen:
  1. at first the route is through DEAD, the preferred router;
  2. neighbour unreachability detection gives up on DEAD (5 s DELAY, 3
     probes), and the route moves to LIVE;
  3. it stays on LIVE, though DEAD's entry is still in the list and LIVE
     keeps advertising, while DEAD does not answer;
  4. DEAD comes back at BACK, answering Neighbor Solicitations but sending
     no advertisements: AROS's probe of it (once a minute at most) finds it,
     and the route goes back through it.
"""
import argparse, os, re, socket, struct, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
CROSS = os.environ.get("AROS_CROSS",
    os.path.expanduser("~/aros-midihub/build-aros-linux/bin/linux-x86_64/tools/crosstools/x86_64-aros-gcc"))
IFACE = "aros0"
DEAD = "fe80::4d54:d"
DST = "2001:db8:ffff::1"
BACK, SECONDS = int(os.environ.get("DR_BACK", 40)), int(os.environ.get("DR_SECONDS", 115))
FAILOVER_MAX = 20       # DELAY 5 s + 3 probes 1 s apart, and slack
PROBE_MAX = 70          # once a minute, and slack


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", default=os.path.expanduser("~/aros-build-ipv6-hosted-claude/bin/linux-x86_64/AROS"))
    ap.add_argument("--arostcp")
    ap.add_argument("--out", default=os.path.join(HERE, "out", "defrouter-" + time.strftime("%Y%m%d-%H%M%S")))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    exe = os.path.join(a.out, "rtwatch")
    subprocess.run([CROSS, "-std=gnu99", "-O2", "-Wall", "-Wno-pointer-sign", "-o", exe,
                    os.path.join(HERE, "rtwatch.c")], check=True)
    subprocess.run([os.path.join(ROOT, "tools", "tap-up.sh")], check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["sudo", "-n", "ip", "-6", "addr", "del", DEAD + "/64", "dev", IFACE], stderr=subprocess.DEVNULL)
    # the host plays routers: forwarding on the tap makes its Neighbor
    # Advertisements carry the Router flag, as a router's do (a clear one
    # takes a router off AROS's list, RFC 4861 section 7.2.5)
    fwd_key = "net.ipv6.conf.%s.forwarding" % IFACE
    fwd_was = subprocess.run(["sysctl", "-n", fwd_key], capture_output=True, text=True).stdout.strip() or "0"
    subprocess.run(["sudo", "-n", "sysctl", "-qw", fwd_key + "=1"], check=True)
    live = "fe80::1"            # the host's link-local, which tools/tap-up.sh gives the tap

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
        f.write("C:rtwatch eth0 %s %d >SYS:out/rtwatch.log\n" % (DST, SECONDS))
    env = dict(os.environ, AROS_HOSTED_IMAGE=a.image, AROS_TAP_IP="192.168.166.2",
               AROS_RUN_TIMEOUT=str(SECONDS + 90))
    if a.arostcp:
        env["AROS_AROSTCP"] = os.path.abspath(a.arostcp)
    boot = subprocess.Popen([os.path.join(ROOT, "tools", "hosted-run.sh"), os.path.join(a.out, "boot"), script, exe],
                            env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    sender = None
    deadline = time.time() + 90
    while time.time() < deadline and sender is None:
        lst.settimeout(1.0)
        try:
            data, _ = lst.recvfrom(256)
        except socket.timeout:
            continue
        if data == b"P:start":
            sender = subprocess.Popen(["sudo", "-n", sys.executable, os.path.join(HERE, "defrouter_ra.py"), IFACE,
                                       repr(time.time()), live, "none" if os.environ.get("DR_NODEAD") else DEAD,
                                       str(BACK), str(SECONDS)],
                                      stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    boot.wait()
    sent = sender.communicate()[0] if sender else ""
    subprocess.run(["sudo", "-n", "ip", "-6", "addr", "del", DEAD + "/64", "dev", IFACE], stderr=subprocess.DEVNULL)
    subprocess.run(["sudo", "-n", "sysctl", "-qw", "%s=%s" % (fwd_key, fwd_was)])

    log = os.path.join(a.out, "boot", "out", "rtwatch.log")
    gw = {}
    for line in open(log).read().splitlines() if os.path.exists(log) else []:
        m = re.match(r"t (\d+) (\S+)", line)
        if m:
            gw[int(m.group(1))] = m.group(2)
    ts = sorted(gw)
    fail = next((t for t in ts if gw[t] == live), None)
    back = next((t for t in ts if t >= max(BACK, fail or 0) and gw[t] == DEAD), None)
    checks = [
        ("bench: AROS reported every second, the routers ran",
         len(ts) >= SECONDS - 2 and "dead advertised" in sent and "defrouter_ra done" in sent),
        ("at first the route is through the preferred router", any(gw[t] == DEAD for t in ts if t <= 4)),
        ("it moves to the other once the preferred one does not answer",
         fail is not None and fail <= FAILOVER_MAX),
        ("and stays there while the preferred one is gone",
         fail is not None and all(gw[t] == live for t in ts if fail <= t < BACK)),
        ("the preferred router, back, is found by the probe and used again",
         fail is not None and back is not None and back <= BACK + PROBE_MAX and
         all(gw[t] == DEAD for t in ts if t >= back)),
    ]
    with open(os.path.join(a.out, "report.txt"), "w") as rep:
        for name, ok in checks:
            line = "%s  %s" % ("PASS" if ok else "FAIL", name)
            print(line); rep.write(line + "\n")
        s = "arostcp=%s live=%s failover_at=%s back_at=%s (dead back at %d)\n%s" % (
            a.arostcp or "(image)", live, fail, back, BACK, sent.strip())
        print(s); rep.write(s + "\n")
    return 0 if all(ok for _, ok in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
