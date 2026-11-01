#!/usr/bin/env python3
"""
jumbo_probe.py - a 9000-byte path end to end: the host tap and AROS's
tap.device both at MTU 9000 (AROS_TAP_MTU), IPv4 and IPv6.

- UDP: AROS (udpecho) sends 1500 to 9000-byte datagrams, the host echoes
  them. Only those above the MTU less the headers (8972 bytes IPv4, 8952
  IPv6) may be fragmented: 2 fragments each way for each.
- TCP: AROS sends 2 MB to the host over each family (tcpbench, tcp4send):
  the SYN's MSS should be 8960 (IPv4) / 8940 (IPv6) and the segments that
  large.
- The tap must say it took the MTU ("[tap] [0] MTU 9000" on AROS's serial).

    jumbo_probe.py [--arostcp FILE] [--image DIR] [--mtu 9000] [--out DIR]

The host tap is put back to 1500 at the end.
"""
import argparse, json, os, re, socket, subprocess, sys, threading, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import run_tcp
import udpbig_probe

IFACE = run_tcp.IFACE
HOST4 = "192.168.166.1"
UDP_PORT = udpbig_probe.PORT
TCP_PORT = 7002
SIZES = [1500, 4000, 8192, 8952, 8972, 9000]
BYTES = 2000000


def tcp_listener(log, stop):
    socks = []
    for fam, addr in ((socket.AF_INET6, "::"), (socket.AF_INET, "0.0.0.0")):
        s = socket.socket(fam, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if fam == socket.AF_INET6:
            s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        s.bind((addr, TCP_PORT))
        s.listen(4)
        s.settimeout(0.5)
        socks.append((fam, s))
    while not stop.is_set():
        for fam, s in socks:
            try:
                c, _ = s.accept()
            except socket.timeout:
                continue
            n = 0
            c.settimeout(20)
            try:
                while True:
                    b = c.recv(1 << 16)
                    if not b:
                        break
                    n += len(b)
            except socket.timeout:
                pass
            c.close()
            log.append({"family": 6 if fam == socket.AF_INET6 else 4, "bytes": n})
    for _, s in socks:
        s.close()


def analyse(text, aros4):
    """UDP fragments each way per family; AROS's TCP SYN MSS and largest
    segment per family."""
    text = re.sub(r"\n\s+(?=[0-9a-f:.]+[ .]\S* >)", " ", text)
    out = {"udp_fragments": {"v4": 0, "v6": 0}, "tcp": {"v4": {"syn_mss": [], "largest": 0},
                                                         "v6": {"syn_mss": [], "largest": 0}}}
    for line in text.splitlines():
        v6 = " IP6 " in line
        fam = "v6" if v6 else "v4"
        if v6 and "frag (" in line:
            out["udp_fragments"]["v6"] += 1
            continue
        if not v6 and " IP " in line:
            off = re.search(r"offset (\d+)", line)
            fl = re.search(r"flags \[([^\]]*)\]", line)
            if ("proto UDP" in line or "proto UDP (17)" in line) and (
                    (fl and "+" in fl.group(1)) or (off and off.group(1) != "0")):
                out["udp_fragments"]["v4"] += 1
                continue
        m = re.search(r"\s(\S+)\.(\d+) > \S+\.%d: Flags \[([^\]]*)\]" % TCP_PORT, line)
        if not m:
            continue
        src = m.group(1)
        if not v6 and src != aros4:
            continue
        mss = re.search(r"mss (\d+)", line)
        if "S" in m.group(3) and mss:
            out["tcp"][fam]["syn_mss"].append(int(mss.group(1)))
        ln = re.search(r"length (\d+)\s*$", line)
        if ln:
            out["tcp"][fam]["largest"] = max(out["tcp"][fam]["largest"], int(ln.group(1)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", default=os.environ.get("AROS_HOSTED_IMAGE",
        os.path.expanduser("~/aros-build-ipv6-hosted-claude/bin/linux-x86_64/AROS")))
    ap.add_argument("--arostcp")
    ap.add_argument("--mtu", type=int, default=9000)
    ap.add_argument("--out", default=os.path.join(ROOT, "tests", "tcp", "out", "jumbo-" + time.strftime("%Y%m%d-%H%M%S")))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    exes = []
    for prog in ("udpecho", "tcpbench", "tcp4send"):
        exe = os.path.join(a.out, prog)
        subprocess.run([run_tcp.CROSS, "-std=gnu99", "-O2", "-Wall", "-Wno-pointer-sign", "-o", exe,
                        os.path.join(HERE, prog + ".c")], check=True, capture_output=True)
        exes.append(exe)
    subprocess.run([os.path.join(ROOT, "tools", "tap-up.sh")], check=True, stdout=subprocess.DEVNULL)
    host_ll = re.findall(r"inet6 (fe80::[0-9a-f:]+)/", subprocess.run(
        ["ip", "-6", "addr", "show", "dev", IFACE], capture_output=True, text=True).stdout)[0]
    run_tcp.kill_strays()
    run_tcp.tc_clear()
    subprocess.run(["sudo", "-n", "ip", "link", "set", IFACE, "mtu", str(a.mtu)], check=True)
    try:
        stop = threading.Event()
        tcp = []
        for fam in (socket.AF_INET, socket.AF_INET6):
            threading.Thread(target=udpbig_probe.echo, args=(fam, stop), daemon=True).start()
        threading.Thread(target=tcp_listener, args=(tcp, stop), daemon=True).start()
        script = os.path.join(a.out, "jumbo.script")
        sizes = " ".join(str(n) for n in SIZES)
        with open(script, "w") as f:
            f.write("Execute SYS:System/Network/AROSTCP/S/startnet\nWait 4\n")
            f.write("C:udpecho 4 eth0 %s %d %s >SYS:out/udp4.log\n" % (HOST4, UDP_PORT, sizes))
            f.write("C:udpecho 6 eth0 %s %d %s >SYS:out/udp6.log\n" % (host_ll, UDP_PORT, sizes))
            f.write("C:tcpbench eth0 %s send %d %d >SYS:out/tcp6.log\n" % (host_ll, TCP_PORT, BYTES))
            f.write("C:tcp4send %s %d %d >SYS:out/tcp4.log\n" % (HOST4, TCP_PORT, BYTES))
        pcap = os.path.join(a.out, "jumbo.pcap")
        dump = subprocess.Popen(["sudo", "-n", "tcpdump", "-U", "-i", IFACE, "-n", "-s", "160", "-w", pcap,
                                 "ip or ip6"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1)
        env = dict(os.environ, AROS_HOSTED_IMAGE=a.image, AROS_TAP_IP=run_tcp.AROS_IP,
                   AROS_TAP_MTU=str(a.mtu), AROS_RUN_TIMEOUT="300")
        if a.arostcp:
            env["AROS_AROSTCP"] = a.arostcp
        r = subprocess.run([os.path.join(ROOT, "tools", "hosted-run.sh"), os.path.join(a.out, "aros"), script] + exes,
                           env=env, capture_output=True, text=True)
        stop.set()
        time.sleep(1)
        for pid in subprocess.run(["pgrep", "-f", "^tcpdump -U -i %s -n -s 160 -w %s" % (IFACE, pcap)],
                                  capture_output=True, text=True).stdout.split():
            subprocess.run(["sudo", "-n", "kill", "-INT", pid])
        dump.wait(timeout=10)
    finally:
        subprocess.run(["sudo", "-n", "ip", "link", "set", IFACE, "mtu", "1500"])
    text = subprocess.run(["sudo", "-n", "tcpdump", "-tt", "-nn", "-v", "-r", pcap], capture_output=True, text=True).stdout
    open(os.path.join(a.out, "jumbo.txt"), "w").write(text)
    serial = open(os.path.join(a.out, "aros", "serial.log"), errors="replace").read()
    res = {"boot": "ok" if "finished" in r.stdout else "did not finish",
           "tap_mtu": (re.search(r"\[tap\] \[0\] MTU (\d+)", serial) or [None, None])[1]}
    for fam in ("udp4", "udp6"):
        log = os.path.join(a.out, "aros", "out", fam + ".log")
        res[fam] = dict(re.findall(r"size=(\d+) (\S+)", open(log).read())) if os.path.exists(log) else {}
    res["tcp_host"] = tcp
    res.update(analyse(text, run_tcp.AROS_IP))
    m4, m6 = a.mtu - 28, a.mtu - 48
    res["expected"] = {"udp_fragments": {"v4": 4 * sum(1 for n in SIZES if n > m4),
                                         "v6": 4 * sum(1 for n in SIZES if n > m6)},
                       "syn_mss": {"v4": a.mtu - 40, "v6": a.mtu - 60}}
    res["sanity"] = {"tap_took_mtu": res["tap_mtu"] == str(a.mtu),
                     "all_sizes_reported": all(len(res[f]) == len(SIZES) for f in ("udp4", "udp6")),
                     "tcp_both": len(tcp) == 2}
    res["sanity"]["ok"] = all(res["sanity"].values())
    json.dump(res, open(os.path.join(a.out, "result.json"), "w"), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
