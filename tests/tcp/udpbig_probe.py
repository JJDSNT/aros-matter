#!/usr/bin/env python3
"""
udpbig_probe.py - large UDP datagrams between hosted AROS and the Linux
host over the tap (MTU 1500), both ways, IPv4 and IPv6.

AROS (udpecho) sends datagrams of 1200 to 9000 bytes; the host echoes each
back. Per size it reports whether the echo came back whole, and from the
capture how many fragments went each way: above 1472 (IPv4) or 1452
(IPv6) bytes a datagram must be fragmented at a 1500-byte link, so the
fragments are expected - a missing or corrupt echo is the defect.

    udpbig_probe.py [--arostcp FILE] [--image DIR] [--out DIR]
"""
import argparse, json, os, re, socket, subprocess, sys, threading, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import run_tcp

IFACE = run_tcp.IFACE
HOST4 = "192.168.166.1"
PORT = 7030
SIZES = [1200, 1452, 1472, 1473, 1500, 4000, 8192, 9000]


def echo(family, stop):
    s = socket.socket(family, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1 << 20)
    if family == socket.AF_INET6:       # not on the IPv4 one's port too
        s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
    s.bind(("::" if family == socket.AF_INET6 else "0.0.0.0", PORT))
    s.settimeout(0.5)
    while not stop.is_set():
        try:
            data, peer = s.recvfrom(65536)
            s.sendto(data, peer)
        except socket.timeout:
            pass
    s.close()


def fragments(text, aros):
    """Fragments each way between AROS and the host, by family."""
    out = {"v4_from_aros": 0, "v4_to_aros": 0, "v6_from_aros": 0, "v6_to_aros": 0}
    text = re.sub(r"\n\s+(?=[0-9a-f:.]+ >)", " ", text)
    for line in text.splitlines():
        if " IP6 " in line and "frag (" in line:
            src = re.search(r"\) (\S+) > (\S+):", line)
            if src:
                out["v6_from_aros" if src.group(1).startswith(aros.get("ll", "-")) else "v6_to_aros"] += 1
        elif " IP " in line:
            off = re.search(r"offset (\d+)", line)
            fl = re.search(r"flags \[([^\]]*)\]", line)
            src = re.search(r"\)\s+(\d+\.\d+\.\d+\.\d+)", line)
            if src and ((fl and "+" in fl.group(1)) or (off and off.group(1) != "0")):
                out["v4_from_aros" if src.group(1) == run_tcp.AROS_IP else "v4_to_aros"] += 1
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", default=os.environ.get("AROS_HOSTED_IMAGE",
        os.path.expanduser("~/aros-build-ipv6-hosted-claude/bin/linux-x86_64/AROS")))
    ap.add_argument("--arostcp")
    ap.add_argument("--out", default=os.path.join(ROOT, "tests", "tcp", "out", "udpbig-" + time.strftime("%Y%m%d-%H%M%S")))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    exe = os.path.join(a.out, "udpecho")
    subprocess.run([run_tcp.CROSS, "-std=gnu99", "-O2", "-Wall", "-Wno-pointer-sign", "-o", exe,
                    os.path.join(HERE, "udpecho.c")], check=True, capture_output=True)
    subprocess.run([os.path.join(ROOT, "tools", "tap-up.sh")], check=True, stdout=subprocess.DEVNULL)
    host_ll = re.findall(r"inet6 (fe80::[0-9a-f:]+)/", subprocess.run(
        ["ip", "-6", "addr", "show", "dev", IFACE], capture_output=True, text=True).stdout)[0]
    run_tcp.kill_strays()
    run_tcp.tc_clear()
    stop = threading.Event()
    for fam in (socket.AF_INET, socket.AF_INET6):
        threading.Thread(target=echo, args=(fam, stop), daemon=True).start()
    script = os.path.join(a.out, "udpbig.script")
    sizes = " ".join(str(n) for n in SIZES)
    with open(script, "w") as f:
        f.write("Execute SYS:System/Network/AROSTCP/S/startnet\nWait 4\n")
        f.write("C:udpecho 4 eth0 %s %d %s >SYS:out/v4.log\n" % (HOST4, PORT, sizes))
        f.write("C:udpecho 6 eth0 %s %d %s >SYS:out/v6.log\n" % (host_ll, PORT, sizes))
    pcap = os.path.join(a.out, "udpbig.pcap")
    dump = subprocess.Popen(["sudo", "-n", "tcpdump", "-U", "-i", IFACE, "-n", "-s", "128", "-w", pcap, "ip or ip6"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1)
    env = dict(os.environ, AROS_HOSTED_IMAGE=a.image, AROS_TAP_IP=run_tcp.AROS_IP, AROS_RUN_TIMEOUT="200")
    if a.arostcp:
        env["AROS_AROSTCP"] = a.arostcp
    r = subprocess.run([os.path.join(ROOT, "tools", "hosted-run.sh"), os.path.join(a.out, "aros"), script, exe],
                       env=env, capture_output=True, text=True)
    stop.set()
    time.sleep(1)
    for pid in subprocess.run(["pgrep", "-f", "^tcpdump -U -i %s -n -s 128 -w %s" % (IFACE, pcap)],
                              capture_output=True, text=True).stdout.split():
        subprocess.run(["sudo", "-n", "kill", "-INT", pid])
    dump.wait(timeout=10)
    text = subprocess.run(["sudo", "-n", "tcpdump", "-tt", "-nn", "-v", "-r", pcap], capture_output=True, text=True).stdout
    aros_ll = None
    m = re.search(r"\) (fe80::[0-9a-f:]+)\.\d+ > %s\.%d" % (re.escape(host_ll), PORT), re.sub(r"\n\s+", " ", text))
    if m:
        aros_ll = m.group(1)
    res = {"boot": "ok" if "finished" in r.stdout else "did not finish"}
    for fam in ("v4", "v6"):
        log = os.path.join(a.out, "aros", "out", fam + ".log")
        res[fam] = dict(re.findall(r"size=(\d+) (\S+)", open(log).read())) if os.path.exists(log) else {}
    res["fragments"] = fragments(text, {"ll": aros_ll or "-"})
    # the bench checks itself: every size answered for, and the sizes above
    # the link MTU seen fragmented both ways
    fr = res["fragments"]
    res["sanity"] = {"all_sizes_reported": all(len(res[f]) == len(SIZES) for f in ("v4", "v6")),
                     "fragments_seen": all(fr[k] > 0 for k in fr)}
    res["sanity"]["ok"] = all(res["sanity"].values())
    json.dump(res, open(os.path.join(a.out, "result.json"), "w"), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
