#!/usr/bin/env python3
"""
tsval_probe.py - the TCP timestamps AROS sends (RFC 7323 section 5.4: a
per-connection offset, so that TSval tells neither the uptime nor how two
connections relate), on the wire.

In one boot:
  passive  the host opens a connection to tcpserve (IPv4) and reads 200 kB:
           the SYN-ACK and the data that follows must carry the same clock
           (TSval within a few seconds' ticks of the SYN-ACK's) - the SYN
           cache hands its offset to the connection
  active   tcpbench opens 10 connections (IPv6 link-local) 0.2 s apart: their
           SYNs' TSvals must not be within 1000 ticks of each other, nor
           below 1000 (the ticks since boot)
  stall    tcpbench's RTO bench: the retransmission intervals must stay as
           they were, 3, 6 and 12 ticks (1.5, 3, 6 s), which a wrong offset
           in the RTT measurement would break. Counted in AROS's own clock,
           from the TSvals: hosted AROS sometimes stalls for seconds, which
           the host's clock would count in (the seconds are reported too)

    tsval_probe.py [--arostcp FILE] [--image DIR] [--out DIR]
Needs sudo -n for tcpdump and tc.
"""
import argparse, json, os, re, socket, subprocess, sys, threading, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import run_tcp

IFACE = run_tcp.IFACE
AROS_IP = run_tcp.AROS_IP
SERVE_PORT = 7041


def passive(log):
    """Connect to tcpserve on AROS and read what it sends."""
    end = time.time() + 120
    while time.time() < end:
        try:
            s = socket.create_connection((AROS_IP, SERVE_PORT), timeout=2)
        except OSError:
            time.sleep(0.5)
            continue
        n = 0
        s.settimeout(10)
        try:
            while True:
                b = s.recv(65536)
                if not b:
                    break
                n += len(b)
        except socket.timeout:
            pass
        s.close()
        log["passive_bytes"] = n
        return


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", default=os.environ.get("AROS_HOSTED_IMAGE",
        os.path.expanduser("~/aros-build-ipv6-hosted-claude/bin/linux-x86_64/AROS")))
    ap.add_argument("--arostcp")
    ap.add_argument("--out", default=os.path.join(HERE, "out", "tsval-" + time.strftime("%Y%m%d-%H%M%S")))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    exes = []
    for prog in ("tcpbench", "tcpserve"):
        exe = os.path.join(a.out, prog)
        subprocess.run([run_tcp.CROSS, "-std=gnu99", "-O2", "-Wall", "-Wno-pointer-sign", "-o", exe,
                        os.path.join(HERE, prog + ".c")], check=True, capture_output=True)
        exes.append(exe)
    subprocess.run([os.path.join(ROOT, "tools", "tap-up.sh")], check=True, stdout=subprocess.DEVNULL)
    run_tcp.tc_clear()
    run_tcp.kill_strays()
    host_ll = re.findall(r"inet6 (fe80::[0-9a-f:]+)/", subprocess.run(
        ["ip", "-6", "addr", "show", "dev", IFACE], capture_output=True, text=True).stdout)[0]
    lst = run_tcp.Listeners()           # the host side of tcpbench's connections
    pcap = os.path.join(a.out, "tsval.pcap")
    dump = subprocess.Popen(["sudo", "-n", "tcpdump", "-i", IFACE, "-n", "-s", "128", "-w", pcap, "tcp"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1)
    log = {}
    threading.Thread(target=passive, args=(log,), daemon=True).start()
    script = os.path.join(a.out, "tsval.script")
    with open(script, "w") as f:
        f.write("Execute SYS:System/Network/AROSTCP/S/startnet\nWait 4\n")
        f.write("C:tcpserve 4 %d send 200000 >SYS:out/serve.log\n" % SERVE_PORT)
        f.write("C:tcpbench eth0 %s connect 7001 10 >SYS:out/connect.log\n" % host_ll)
        f.write("C:tcpbench eth0 %s stall 7004 >SYS:out/stall.log\n" % host_ll)
    env = dict(os.environ, AROS_HOSTED_IMAGE=a.image, AROS_TAP_IP=AROS_IP, AROS_RUN_TIMEOUT="300")
    if a.arostcp:
        env["AROS_AROSTCP"] = os.path.abspath(a.arostcp)
    r = subprocess.run([os.path.join(ROOT, "tools", "hosted-run.sh"), os.path.join(a.out, "aros"), script] + exes,
                       env=env, capture_output=True, text=True)
    time.sleep(1)
    for pid in subprocess.run(["pgrep", "-f", "^tcpdump -i %s -n -s 128 -w %s" % (IFACE, pcap)],
                              capture_output=True, text=True).stdout.split():
        subprocess.run(["sudo", "-n", "kill", "-INT", pid])
    dump.wait(timeout=10)
    run_tcp.tc_clear()
    text = subprocess.run(["sudo", "-n", "tcpdump", "-tt", "-nn", "-S", "-v", "-r", pcap],
                          capture_output=True, text=True).stdout
    open(os.path.join(a.out, "tsval.txt"), "w").write(text)

    res = {"boot": "ok" if "finished" in r.stdout else "did not finish", "passive_bytes": log.get("passive_bytes")}
    # passive: segments from AROS:SERVE_PORT
    pas = [(l, int(m.group(1))) for l in text.splitlines()
           for m in [re.search(r"TS val (\d+)", l)] if m and (" %s.%d >" % (AROS_IP, SERVE_PORT)) in l]
    synack = [v for l, v in pas if "Flags [S.]" in l]
    later = [v for l, v in pas if "Flags [S.]" not in l]
    res["passive"] = {"synack_tsval": synack[:1], "segments": len(later),
                      "spread": (max(later) - min(later + synack[:1])) if later and synack else None}
    # a 2 Hz clock: the transfer takes seconds, so 0..100 ticks
    res["passive"]["ok"] = bool(synack and later and
                                all(0 <= (v - synack[0]) % 2**32 < 100 for v in later))
    act = [int(m.group(1)) for l in text.splitlines() if "Flags [S]," in l and ".7001:" in l
           for m in [re.search(r"TS val (\d+)", l)] if m]
    close = sum(1 for i in range(len(act)) for j in range(i + 1, len(act))
                if min((act[i] - act[j]) % 2**32, (act[j] - act[i]) % 2**32) < 1000)
    res["active"] = {"syn_tsvals": act, "pairs_within_1000": close,
                     "below_1000": sum(1 for v in act if v < 1000)}
    res["active"]["ok"] = len(act) == 10 and close == 0 and res["active"]["below_1000"] == 0
    stall = run_tcp.analyse(run_tcp.parse(text)).get("stall", {})
    res["stall"] = stall
    iv = stall.get("intervals") or []
    ts = [int(m.group(1)) for l in text.splitlines() if ".7004:" in l and not l.rstrip().endswith("length 0")
          for m in [re.search(r"TS val (\d+)", l)] if m]
    ticks = [(ts[i] - ts[i - 1]) % 2**32 for i in range(1, len(ts))]
    res["stall_ticks"] = ticks
    res["stall_ok"] = len(ticks) >= 3 and all(abs(t - w) <= 1 for t, w in zip(ticks, (3, 6, 12)))
    # the bench itself: every part ran
    res["bench_ok"] = res["boot"] == "ok" and bool(log.get("passive_bytes")) and len(act) == 10 and bool(iv)
    json.dump(res, open(os.path.join(a.out, "result.json"), "w"), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
