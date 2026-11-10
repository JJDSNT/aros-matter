#!/usr/bin/env python3
"""
nd_hint_probe.py - Neighbor Solicitations from AROS during a long TCP send
over IPv6 (link-local, tests/tcp/cwnd_probe.py).

A neighbour cache entry not confirmed for 30 s is probed when used (RFC
4861 section 7.3); TCP's acknowledged data is a confirmation (7.3.1), so a
sending connection should need no probe. The bench counts the unicast
Neighbor Solicitations AROS sends while it sends.

    nd_hint_probe.py [--arostcp FILE] [--secs 90] [--out DIR]
Needs sudo -n (tcpdump, tc).
"""
import argparse, json, os, re, subprocess, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
TAP = "aros0"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arostcp")
    ap.add_argument("--secs", type=int, default=90)
    ap.add_argument("--out", default=os.path.join(HERE, "out", "ndhint-" + time.strftime("%Y%m%d-%H%M%S")))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    pcap = os.path.join(a.out, "ns.pcap")
    dump = subprocess.Popen(["sudo", "-n", "tcpdump", "-U", "-p", "-i", TAP, "-n", "-w", pcap,
                             "icmp6 and ip6[40] == 135"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1)
    cmd = ["python3", os.path.join(ROOT, "tests", "tcp", "cwnd_probe.py"), "--secs", str(a.secs), "--delay", "20",
           "--every", "0", "--sndbuf", "0", "--out", os.path.join(a.out, "cwnd")]
    if a.arostcp:
        cmd += ["--arostcp", os.path.abspath(a.arostcp)]
    t0 = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True)
    t1 = time.time()
    subprocess.run(["sudo", "-n", "pkill", "-INT", "-f", "tcpdump -U -p -i %s -n -w %s" % (TAP, pcap)])
    dump.wait(timeout=10)
    host_ll = re.findall(r"inet6 (fe80::[0-9a-f:]+)/", subprocess.run(
        ["ip", "-6", "addr", "show", "dev", TAP], capture_output=True, text=True).stdout)
    text = subprocess.run(["sudo", "-n", "tcpdump", "-tt", "-n", "-r", pcap], capture_output=True, text=True).stdout
    ns = []
    for line in text.splitlines():
        m = re.match(r"(\d+\.\d+) IP6 (\S+) > (\S+): ICMP6, neighbor solicitation", line)
        if m and m.group(2) not in host_ll and m.group(2) != "::" and not m.group(3).startswith("ff02"):
            ns.append(float(m.group(1)))
    res = {"secs": a.secs, "cwnd_probe": r.stdout.strip().splitlines()[-1:] if r.stdout else None,
           "unicast_ns_from_aros": len(ns), "during_run_s": round(t1 - t0, 1)}
    res["sanity"] = {"sent": "ok=True" in (r.stdout or "")}
    res["sanity"]["ok"] = all(res["sanity"].values())
    json.dump(res, open(os.path.join(a.out, "result.json"), "w"), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
