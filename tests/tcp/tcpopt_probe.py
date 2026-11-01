#!/usr/bin/env python3
"""
tcpopt_probe.py - when AROS gives up on a TCP connection: keepalive per
socket (TCP_KEEPIDLE/INTVL/CNT) and TCP_USER_TIMEOUT (RFC 5482), on the wire.

AROS (tcpbench) opens one connection to the host per case, over IPv6
link-local; the host makes the peer go silent at a known time by dropping
AROS's packets for that port at ingress (tc), or never reads:

  keepalive   idle 2 s, interval 1 s, 3 probes; the host goes silent 1 s
              after the connection: AROS should give up about 5 s after its
              last segment
  ka_uto      keepalive 2/1/9 with TCP_USER_TIMEOUT 4000 ms: about 4 s,
              before the 9 probes would end it (Linux's rule)
  uto         TCP_USER_TIMEOUT 3000 ms while sending; the host goes silent
              2 s in: AROS should give up about 3 s later, not after the
              12 retransmissions (minutes)
  zerowin     TCP_USER_TIMEOUT 3000 ms; the host never reads, with a small
              receive buffer: AROS should give up about 3 s after the
              window closes (+ up to one persist interval, 5 s)

For each it reports what AROS printed (ms since it connected, errno) and,
from the capture, the time between the host going silent and AROS's last
packet or RST, and AROS's keepalive probes.

    tcpopt_probe.py [--arostcp FILE] [--image DIR] [--only a,b] [--out DIR]
"""
import argparse, json, os, re, socket, subprocess, sys, threading, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import run_tcp

IFACE = run_tcp.IFACE
CASES = {
    #  name       port  tcpbench args                       silent after accept (s)
    "keepalive": (7021, "keepalive 7021 2 1 3",              1.0),
    "ka_uto":    (7022, "keepalive 7022 2 1 9 4000",         1.0),
    "uto":       (7023, "uto 7023 3000",                     2.0),
    "zerowin":   (7024, "zerowin 7024 3000",                 None),
}


def sh(*a):
    return subprocess.run(["sudo", "-n"] + list(a), capture_output=True, text=True)


def silence(port):
    """Drop what AROS sends to this port of the host, from now on."""
    sh("tc", "filter", "add", "dev", IFACE, "parent", "ffff:", "protocol", "ipv6", "prio", "1",
       "u32", "match", "ip6", "protocol", "6", "0xff", "match", "ip6", "dport", str(port), "0xffff",
       "action", "drop")


def host(name, port, after, rec, deadline):
    s = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if after is None:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)   # the window closes soon
    s.bind(("::", port))
    s.listen(1)
    s.settimeout(max(1, deadline - time.time()))
    try:
        c, _ = s.accept()
    except socket.timeout:
        return
    rec["accepted"] = time.time()
    if after is None:           # never read
        time.sleep(max(0, deadline - time.time()))
        c.close()
        return
    c.settimeout(0.2)
    t_silent = rec["accepted"] + after
    while time.time() < t_silent:
        try:
            c.recv(65536)
        except socket.timeout:
            pass
        except OSError:
            break
    silence(port)
    rec["silent"] = time.time()
    time.sleep(max(0, min(deadline, rec["silent"] + 30) - time.time()))
    c.close()


def analyse(text, rec, port):
    """From AROS's packets to this port: the last one, RSTs, keepalive probes."""
    out = {"aros_packets_after_silence": 0, "rst_after_s": None, "last_after_s": None, "probes": 0}
    t0 = rec.get("silent") or rec.get("accepted")
    if t0 is None:
        return out
    for line in text.splitlines():
        m = re.match(r"^(\d+\.\d+) IP6 .*?\S+\.(\d+) > \S+\.(\d+): Flags \[([^\]]*)\].*?length (\d+)", line)
        if not m or int(m.group(3)) != port:
            continue
        t = float(m.group(1))
        if t < t0:
            continue
        out["aros_packets_after_silence"] += 1
        out["last_after_s"] = round(t - t0, 2)
        if "R" in m.group(4) and out["rst_after_s"] is None:
            out["rst_after_s"] = round(t - t0, 2)
        if m.group(4) == "." and int(m.group(5)) in (0, 1):
            out["probes"] += 1
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", default=os.environ.get("AROS_HOSTED_IMAGE",
        os.path.expanduser("~/aros-build-ipv6-hosted-claude/bin/linux-x86_64/AROS")))
    ap.add_argument("--arostcp")
    ap.add_argument("--only", default=",".join(CASES))
    ap.add_argument("--out", default=os.path.join(ROOT, "tests", "tcp", "out", "tcpopt-" + time.strftime("%Y%m%d-%H%M%S")))
    a = ap.parse_args()
    cases = [c for c in a.only.split(",") if c in CASES]
    os.makedirs(a.out, exist_ok=True)
    exe = os.path.join(a.out, "tcpbench")
    subprocess.run([run_tcp.CROSS, "-std=gnu99", "-O2", "-Wall", "-Wno-pointer-sign", "-o", exe,
                    os.path.join(HERE, "tcpbench.c")], check=True, capture_output=True)
    subprocess.run([os.path.join(ROOT, "tools", "tap-up.sh")], check=True, stdout=subprocess.DEVNULL)
    host_ll = re.findall(r"inet6 (fe80::[0-9a-f:]+)/", subprocess.run(
        ["ip", "-6", "addr", "show", "dev", IFACE], capture_output=True, text=True).stdout)[0]
    run_tcp.kill_strays()
    run_tcp.tc_clear()
    sh("tc", "qdisc", "add", "dev", IFACE, "handle", "ffff:", "ingress")

    script = os.path.join(a.out, "tcpopt.script")
    with open(script, "w") as f:
        f.write("Execute SYS:System/Network/AROSTCP/S/startnet\nWait 4\n")
        for c in cases:
            f.write("C:tcpbench eth0 %s %s >SYS:out/%s.log\n" % (host_ll, CASES[c][1], c))
    pcap = os.path.join(a.out, "tcpopt.pcap")
    dump = subprocess.Popen(["sudo", "-n", "tcpdump", "-U", "-i", IFACE, "-n", "-s", "96", "-w", pcap, "ip6 and tcp"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1)
    recs = {c: {} for c in cases}
    deadline = time.time() + 400
    for c in cases:
        port, _, after = CASES[c]
        threading.Thread(target=host, args=(c, port, after, recs[c], deadline), daemon=True).start()
    env = dict(os.environ, AROS_HOSTED_IMAGE=a.image, AROS_TAP_IP=run_tcp.AROS_IP, AROS_RUN_TIMEOUT="420")
    if a.arostcp:
        env["AROS_AROSTCP"] = a.arostcp
    r = subprocess.run([os.path.join(ROOT, "tools", "hosted-run.sh"), os.path.join(a.out, "aros"), script, exe],
                       env=env, capture_output=True, text=True)
    run_tcp.tc_clear()
    time.sleep(1)
    for pid in subprocess.run(["pgrep", "-f", "^tcpdump -U -i %s -n -s 96 -w %s" % (IFACE, pcap)],
                              capture_output=True, text=True).stdout.split():
        sh("kill", "-INT", pid)
    dump.wait(timeout=10)
    text = subprocess.run(["sudo", "-n", "tcpdump", "-tt", "-nn", "-r", pcap], capture_output=True, text=True).stdout
    open(os.path.join(a.out, "tcpopt.txt"), "w").write(text)

    res = {"boot": "ok" if "finished" in r.stdout else "did not finish", "cases": {}}
    for c in cases:
        log = os.path.join(a.out, "aros", "out", c + ".log")
        line = open(log).read().strip() if os.path.exists(log) else ""
        m = re.search(r"ms=(-?\d+) wait=(-?\d+) errno=(\d+)", line)
        res["cases"][c] = {"aros": line, "ms": int(m.group(1)) if m else None,
                           "wait_ms": int(m.group(2)) if m else None, "errno": int(m.group(3)) if m else None,
                           "host": {k: round(v - recs[c]["accepted"], 2) for k, v in recs[c].items() if "accepted" in recs[c]},
                           "wire": analyse(text, recs[c], CASES[c][0])}
    json.dump(res, open(os.path.join(a.out, "result.json"), "w"), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
