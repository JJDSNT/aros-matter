#!/usr/bin/env python3
"""
ack_probe.py - how often AROS's TCP receiver acknowledges (RFC 5681 section
4.2: at least every second full-sized segment, and within 500 ms), on the
wire.

AROS listens (tcpserve 4 PORT recv); the host connects over IPv4, sends
BYTES and closes. From a capture of the tap it reports the size of the
segments that reached AROS (larger than the MSS would mean offload
aggregation on the host side, not separate segments), and for each ACK
from AROS that takes the acknowledgement forward, how many full-sized
segments it covers: the distribution, and the share of ACKs covering more
than two. --gap MS has the host send in 16 KB writes MS apart, so that the
delayed-ACK timer, not the second segment, sends some ACKs.

    ack_probe.py [--arostcp FILE] [--image DIR] [--bytes 2000000] [--gap 0] [--out DIR]
Needs sudo -n for tcpdump.
"""
import argparse, collections, json, os, re, socket, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import run_tcp

PORT = 7401


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", default=os.path.expanduser("~/aros-build-ipv6-hosted-claude/bin/linux-x86_64/AROS"))
    ap.add_argument("--arostcp")
    ap.add_argument("--bytes", type=int, default=2000000)
    ap.add_argument("--gap", type=int, default=0)
    ap.add_argument("--delay", type=int, default=0, help="netem delay (ms) on what the host sends")
    ap.add_argument("--ifopts", default="", help="extra options for AROS's interfaces line, e.g. IPREQ=128")
    ap.add_argument("--out", default=os.path.join(ROOT, "tests", "tcp", "out", "ack-" + time.strftime("%Y%m%d-%H%M%S")))
    a = ap.parse_args()
    run_tcp.clock()                     # sampled from now; the capture's times made monotonic
    os.makedirs(a.out, exist_ok=True)
    exe = os.path.join(a.out, "tcpserve")
    subprocess.run([run_tcp.CROSS, "-std=gnu99", "-O2", "-Wall", "-Wno-pointer-sign", "-o", exe,
                    os.path.join(HERE, "tcpserve.c")], check=True)
    subprocess.run([os.path.join(ROOT, "tools", "tap-up.sh")], check=True, stdout=subprocess.DEVNULL)
    run_tcp.kill_strays()
    run_tcp.tc_clear()
    if a.delay:
        run_tcp.tc_delay(a.delay)
    offload = subprocess.run(["ethtool", "-k", run_tcp.IFACE], capture_output=True, text=True).stdout
    pcap = os.path.join(a.out, "ack.pcap")
    dump = subprocess.Popen(["sudo", "-n", "tcpdump", "-i", run_tcp.IFACE, "-n", "-s", "96", "-w", pcap,
                             "tcp port %d" % PORT], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    script = os.path.join(a.out, "ack.script")
    with open(script, "w") as f:
        f.write("Execute SYS:System/Network/AROSTCP/S/startnet\nWait 4\n")
        f.write("C:tcpserve 4 %d recv 0 >SYS:out/serve.log\n" % PORT)
    env = dict(os.environ, AROS_HOSTED_IMAGE=a.image, AROS_TAP_IP=run_tcp.AROS_IP, AROS_RUN_TIMEOUT="180",
               AROS_TAP_OPTS=(a.ifopts + " ") if a.ifopts else "")
    if a.arostcp:
        env["AROS_AROSTCP"] = os.path.abspath(a.arostcp)
    boot = subprocess.Popen([os.path.join(ROOT, "tools", "hosted-run.sh"), os.path.join(a.out, "aros"), script, exe],
                            env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    sent, err = 0, None
    deadline = time.time() + 90
    while time.time() < deadline:
        try:
            c = socket.create_connection((run_tcp.AROS_IP, PORT), timeout=2)
            break
        except OSError:
            time.sleep(1)
    else:
        err = "no connection"
    if err is None:
        try:
            chunk = b"d" * (16384 if a.gap else 65536)
            while sent < a.bytes:
                c.sendall(chunk)
                sent += len(chunk)
                if a.gap:
                    time.sleep(a.gap / 1000)
            c.shutdown(socket.SHUT_WR)
            c.settimeout(10)
            while c.recv(4096):
                pass
        except OSError as e:
            err = str(e)
        c.close()
    out_text = boot.communicate()[0]
    run_tcp.tc_clear()
    time.sleep(1)
    for pid in subprocess.run(["pgrep", "-P", str(dump.pid)], capture_output=True, text=True).stdout.split():
        subprocess.run(["sudo", "-n", "kill", "-INT", pid])
    dump.wait(timeout=10)
    text = subprocess.run(["sudo", "-n", "tcpdump", "-tt", "-nn", "-S", "-r", pcap], capture_output=True, text=True).stdout
    text = run_tcp.clock().monotonic(text)    # wall clock -> monotonic (WSL2 steps)
    sizes = collections.Counter()
    data = []                                   # (t, end) of each new data segment from the host
    acks = []                                   # (t, ack) from AROS
    mss = 0
    hport = collections.Counter()               # the host's port of the data connection
    for line in text.splitlines():
        m = re.match(r"(\d+\.\d+) IP (\S+)\.(\d+) > (\S+)\.(\d+): Flags \[([^\]]*)\](.*)", line)
        if not m:
            continue
        t, rest = float(m.group(1)), m.group(7)
        if "R" in m.group(6):
            continue                            # attempts before AROS listened
        if int(m.group(5)) == PORT:
            ms = re.search(r"seq (\d+):(\d+)", rest)
            if ms:
                n = int(ms.group(2)) - int(ms.group(1))
                sizes[n] += 1
                data.append((t, int(ms.group(2))))
                hport[int(m.group(3))] += 1
        elif int(m.group(3)) == PORT:
            mo = re.search(r"mss (\d+)", rest)     # AROS's, in its SYN-ACK
            if mo:
                mss = int(mo.group(1))
            ma = re.search(r"ack (\d+)", rest)
            if ma and "S" not in m.group(6):
                acks.append((t, int(ma.group(1)), int(m.group(5))))
    full = max(sizes) if sizes else 0           # the full segment size seen
    per_ack = collections.Counter()
    last = None
    delays = []
    conn = hport.most_common(1)[0][0] if hport else None
    for t, ack, dport in acks:
        if dport != conn:
            continue
        if last is not None and 0 < (ack - last) & 0xffffffff < 1 << 31:
            per_ack[round(((ack - last) & 0xffffffff) / full)] += 1
            done = [td for td, end in data if end == ack]
            if done:
                delays.append(t - done[-1])
        if last is None or 0 < (ack - last) & 0xffffffff < 1 << 31:
            last = ack
    total = sum(per_ack.values())
    over2 = sum(v for k, v in per_ack.items() if k > 2)
    span = (data[-1][0] - data[0][0]) if len(data) > 1 else 0
    seen_seq, retx = set(), 0
    for line in text.splitlines():
        m = re.search(r"> \S+\.%d: Flags \[[^\]]*\], seq (\d+):" % PORT, line)
        if m:
            retx += m.group(1) in seen_seq
            seen_seq.add(m.group(1))
    res = {"host_retransmissions": retx, "mbit": round(sent * 8 / span / 1e6, 1) if span else None, "delay_ms": a.delay,
           "bytes_sent": sent, "error": err, "mss_option": mss, "segment_sizes": dict(sizes.most_common(6)),
           "full_segment": full, "acks": total, "segments_per_ack": dict(sorted(per_ack.items())),
           "acks_over_2_segments": over2, "share_over_2": round(over2 / total, 3) if total else None,
           "max_ack_delay_ms": round(max(delays) * 1000, 1) if delays else None,
           "host_offload": [l.strip() for l in offload.splitlines() if "segmentation" in l or "generic-receive" in l],
           "boot": "ok" if "finished" in out_text else "did not finish"}
    # the bench's own checks: data went through, and no segment larger than
    # the MSS reached AROS (no aggregation to mistake for segments)
    res["ok"] = err is None and total > 0 and (mss == 0 or full <= mss)
    json.dump(res, open(os.path.join(a.out, "result.json"), "w"), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
