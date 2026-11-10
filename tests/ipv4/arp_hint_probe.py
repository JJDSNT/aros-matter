#!/usr/bin/env python3
"""
arp_hint_probe.py - ARP traffic from AROS during a long TCP send over IPv4.

AROS (tests/tcp/tcp4send) sends BYTES to the host over IPv4 with netem
delay DELAY ms (a minute or so); a capture of the tap counts the ARP
requests AROS sends. With neighbour reachability checked as IPv6's NUD,
an entry is probed when it has gone 30 s without confirmation; TCP's
acknowledged data confirms it (RFC 4861 7.3.1), so a sending connection
should need no probe at all.

    arp_hint_probe.py [--arostcp FILE] [--image DIR] [--bytes N] [--delay MS] [--out DIR]
Needs sudo -n (tcpdump, tc).
"""
import argparse, json, os, re, socket, subprocess, sys, threading, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tests", "tcp"))
import run_tcp

TAP, HOST, AROS, PORT = "aros0", "192.168.166.1", "192.168.166.2", 7041


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", default=os.environ.get("AROS_HOSTED_IMAGE",
        os.path.expanduser("~/aros-build-ipv6-hosted-claude/bin/linux-x86_64/AROS")))
    ap.add_argument("--arostcp")
    ap.add_argument("--bytes", type=int, default=150000000)
    ap.add_argument("--delay", type=int, default=100)
    ap.add_argument("--out", default=os.path.join(HERE, "out", "arphint-" + time.strftime("%Y%m%d-%H%M%S")))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    exe = os.path.join(a.out, "tcp4send")
    subprocess.run([run_tcp.CROSS, "-std=gnu99", "-O2", "-Wall", "-o", exe,
                    os.path.join(ROOT, "tests", "tcp", "tcp4send.c")], check=True, capture_output=True)
    subprocess.run([os.path.join(ROOT, "tools", "tap-up.sh")], check=True, stdout=subprocess.DEVNULL)
    run_tcp.tc_clear()
    run_tcp.tc_delay(a.delay)
    got, span = [0], []
    ls = socket.socket()
    ls.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    ls.bind((HOST, PORT))
    ls.listen(1)

    def sink():
        c, _ = ls.accept()
        span.append(time.time())
        while True:
            d = c.recv(65536)
            if not d:
                break
            got[0] += len(d)
        span.append(time.time())
    threading.Thread(target=sink, daemon=True).start()
    pcap = os.path.join(a.out, "arp.pcap")
    dump = subprocess.Popen(["sudo", "-n", "tcpdump", "-U", "-p", "-i", TAP, "-n", "-w", pcap, "arp"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    script = os.path.join(a.out, "hint.script")
    with open(script, "w") as f:
        f.write("Execute SYS:System/Network/AROSTCP/S/startnet\nWait 10\n")
        f.write("C:tcp4send %s %d %d >SYS:out/send.log\n" % (HOST, PORT, a.bytes))
    env = dict(os.environ, AROS_HOSTED_IMAGE=a.image, AROS_TAP_IP=AROS, AROS_RUN_TIMEOUT="400")
    if a.arostcp:
        env["AROS_AROSTCP"] = os.path.abspath(a.arostcp)
    try:
        r = subprocess.run([os.path.join(ROOT, "tools", "hosted-run.sh"), os.path.join(a.out, "aros"), script, exe],
                           env=env, capture_output=True, text=True)
    finally:
        run_tcp.tc_clear()
        subprocess.run(["sudo", "-n", "pkill", "-INT", "-f", "tcpdump -U -p -i %s -n -w %s" % (TAP, pcap)])
        dump.wait(timeout=10)
    text = subprocess.run(["sudo", "-n", "tcpdump", "-tt", "-e", "-n", "-r", pcap], capture_output=True, text=True).stdout
    reqs = []
    for line in text.splitlines():
        m = re.match(r"(\d+\.\d+) \S+ > (\S+), .*Request who-has (\S+) tell (\S+),", line)
        if m and m.group(4) == AROS:
            reqs.append((float(m.group(1)), m.group(2) != "ff:ff:ff:ff:ff:ff"))
    during = [u for t, u in reqs if len(span) == 2 and span[0] <= t <= span[1]]
    res = {"boot": "ok" if "finished" in r.stdout else "did not finish", "bytes": got[0],
           "seconds": round(span[1] - span[0], 1) if len(span) == 2 else None,
           "arp_requests_during": len(during), "unicast_during": sum(during)}
    res["sanity"] = {"sent_all": got[0] == a.bytes, "long_enough": res["seconds"] is not None and res["seconds"] > 40}
    res["sanity"]["ok"] = all(res["sanity"].values())
    json.dump(res, open(os.path.join(a.out, "result.json"), "w"), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
