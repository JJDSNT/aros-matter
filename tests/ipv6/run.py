#!/usr/bin/env python3
"""Run the AROSTCP IPv6 cases (ipv6test.c) on hosted AROS over the tap 'aros0'.

The host side, all in this process:
  * multicasts "H:<seq>" to ff02::fb:5353 on aros0 twice a second;
  * records datagrams AROS sends to ff02::fb:5353 (payload, source, port);
  * captures MLD with tcpdump, to check reports and leaves per group.

Then it boots AROS (tools/hosted-run.sh), runs ipv6test, and merges the AROS
results with the host-side expectations ("host ..." lines) into one report.

Usage: tests/ipv6/run.py [--image DIR] [--out DIR] [CASE...]
"""
import argparse, os, re, select, socket, struct, subprocess, sys, threading, time, json

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
CROSS = os.environ.get("AROS_CROSS",
    os.path.expanduser("~/aros-midihub/build-aros-linux/bin/linux-x86_64/tools/crosstools/x86_64-aros-gcc"))
IFACE = "aros0"
AROS_IP = "192.168.166.2"


class Peer(threading.Thread):
    """Sends H:<seq> to the group and records what arrives on 5353."""
    def __init__(self, iface):
        super().__init__(daemon=True)
        self.idx = socket.if_nametoindex(iface)
        s = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        s.bind(("::", 5353))
        s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_JOIN_GROUP,
                     socket.inet_pton(socket.AF_INET6, "ff02::fb") + struct.pack("@I", self.idx))
        s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_MULTICAST_IF, self.idx)
        s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_MULTICAST_LOOP, 0)
        self.sock, self.stop, self.rx, self.sent = s, threading.Event(), [], 0
        self.iface, self.ping = iface, None

    def run(self):
        nxt = 0.0
        while not self.stop.is_set():
            now = time.time()
            if now >= nxt:
                nxt = now + 0.5
                try:
                    self.sock.sendto(b"H:%d" % self.sent, ("ff02::fb", 5353, 0, self.idx))
                    self.sent += 1
                except OSError:
                    pass  # the tap is down until AROS opens it
            r, _, _ = select.select([self.sock], [], [], max(0.0, nxt - time.time()))
            if r:
                data, src = self.sock.recvfrom(512)
                if not data.startswith(b"H:"):
                    lt = time.localtime()
                    self.rx.append({"t": time.time(), "tod": lt.tm_hour * 3600 + lt.tm_min * 60 + lt.tm_sec + (time.time() % 1),
                                    "data": data.decode(errors="replace"), "src": src[0], "port": src[1]})
                    if data == b"P:ping-me" and self.ping is None:
                        dst = src[0].split("%")[0] + "%" + self.iface
                        threading.Thread(target=self.do_ping, args=(dst,), daemon=True).start()

    def do_ping(self, dst):
        p = subprocess.run(["ping", "-6", "-c", "3", "-W", "2", dst], capture_output=True, text=True)
        self.ping = {"dst": dst, "rc": p.returncode, "out": p.stdout[-300:]}


def tod(hms):
    h, m, sec = hms.split(":")
    return int(h) * 3600 + int(m) * 60 + float(sec)


def mld_events(tcpdump_text, host_ll, with_time=False):
    """(group, kind) in order, from AROS only. kind: report | leave.
    with_time: (time-of-day seconds, group, kind)."""
    ev = []
    for line in tcpdump_text.splitlines():
        ts = re.match(r"(\d+:\d+:\d+\.\d+) ", line)
        # -vv: "IP6 (hlim 1, next-header Options (0) payload length: 32) SRC > DST: ..."
        m = re.search(r"IP6 \((?:[^()]|\([^()]*\))*\) (\S+) > (\S+):", line) or re.search(r"IP6 (\S+) > (\S+):", line)
        if not m or "multicast listener" not in line:
            continue
        src = m.group(1)
        if src in host_ll:
            continue
        if "multicast listener report v2" in line:
            found = [(g, "leave" if mode == "to_in" else "report")
                     for g, mode in re.findall(r"gaddr (\S+) (\w+) \{", line)]
        elif "multicast listener done" in line:
            g = re.search(r"addr: (\S+)", line)
            found = [(g.group(1).rstrip(","), "leave")] if g else []
        elif "multicast listener report" in line:
            g = re.search(r"addr: (\S+)", line)
            found = [(g.group(1).rstrip(","), "report")] if g else []
        else:
            found = []
        for g, k in found:
            ev.append((tod(ts.group(1)) if ts else 0.0, g, k) if with_time else (g, k))
    return ev


def capture_markers(tcpdump_text):
    """{marker: [time-of-day, ...]} for the P:... datagrams in the capture."""
    marks, last_ts = {}, None
    for line in tcpdump_text.splitlines():
        ts = re.match(r"(\d+:\d+:\d+\.\d+) IP6", line)
        if ts:
            last_ts = tod(ts.group(1))
            continue
        m = re.search(r"(P:[a-z-]+)", line)
        if m and last_ts is not None:
            marks.setdefault(m.group(1), []).append(last_ts)
            last_ts = None
    return marks


def collapse(seq):
    out = []
    for k in seq:
        if not out or out[-1] != k:
            out.append(k)
    return out


def host_check(case, what, peer_rx, mld, mldt=None, ping=None, marks=None):
    """Evaluate one 'host <case> <expectation>' line. Returns (ok, detail)."""
    parts = what.split()
    if parts[0] == "received":
        if parts[1] == "A-or-L:loop-on":
            hits = [r for r in peer_rx if r["data"] == "L:loop-on"]
        else:
            hits = [r for r in peer_rx if r["data"] == parts[1]]
        if not hits:
            return False, "host saw nothing"
        if "from-port" in parts:
            want = int(parts[parts.index("from-port") + 1])
            ok = any(r["port"] == want for r in hits)
            return ok, "from %s port %s" % (hits[0]["src"], hits[0]["port"])
        return True, "from %s" % hits[0]["src"]
    if parts[0] == "mld":
        grp, want = parts[1], parts[2].split(",")
        got = collapse([k for g, k in mld if g == grp])
        return got == want, "wire: %s (want %s)" % (",".join(got) or "nothing", ",".join(want))
    if parts[0] == "nd":
        if not ping:
            return False, "host never pinged (no P:ping-me seen)"
        return ping["rc"] == 0, "ping6 %s rc=%d" % (ping["dst"], ping["rc"])
    if parts[0] == "mldwin":
        grp, a, b, want = parts[1], parts[2], parts[3], parts[4]
        ta = (marks or {}).get(a, [])
        tb = (marks or {}).get(b, [])
        if not ta or not tb:
            return False, "marker missing (%s %s)" % (bool(ta), bool(tb))
        kinds = [k for t, g, k in mldt if g == grp and ta[0] <= t < tb[0]]
        if want == "none":
            return not kinds, "between %s and %s: %s" % (a, b, ",".join(kinds) or "nothing")
        return want in kinds, "between %s and %s: %s" % (a, b, ",".join(kinds) or "nothing")
    return False, "unknown expectation " + what


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", default=os.environ.get("AROS_HOSTED_IMAGE",
        os.path.expanduser("~/aros-midihub/build-aros-linux/bin/linux-x86_64/AROS")))
    ap.add_argument("--arostcp", help="AROSTCP binary to use instead of the image's")
    ap.add_argument("--out", default=os.path.join(ROOT, "tests", "ipv6", "out", time.strftime("%Y%m%d-%H%M%S")))
    ap.add_argument("cases", nargs="*")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    exe = os.path.join(a.out, "ipv6test")
    subprocess.run([CROSS, "-std=gnu99", "-O2", "-Wall", "-Wno-pointer-sign", "-o", exe,
                    os.path.join(HERE, "ipv6test.c")], check=True)
    subprocess.run([os.path.join(ROOT, "tools", "tap-up.sh")], check=True, stdout=subprocess.DEVNULL)

    host_ll = set()
    for line in subprocess.run(["ip", "-6", "addr", "show", "dev", IFACE], capture_output=True, text=True).stdout.splitlines():
        m = re.search(r"inet6 (fe80::\S+)/", line)
        if m: host_ll.add(m.group(1))

    dump_path = os.path.join(a.out, "mld.tcpdump")
    # MLD (behind its Hop-by-Hop header) and AROS's own datagrams, with the
    # payload (-A) so the phase markers share the capture's clock; the host's
    # H:<seq> stream is left out.
    flt = "ip6 and not (udp and (%s))" % " or ".join("src host %s" % a for a in sorted(host_ll)) if host_ll else "ip6 and not udp"
    dump = subprocess.Popen(["sudo", "tcpdump", "-i", IFACE, "-n", "-l", "-vv", "-A", flt],
                            stdout=open(dump_path, "w"), stderr=subprocess.DEVNULL)
    peer = Peer(IFACE); peer.start()

    script = os.path.join(a.out, "run.script")
    with open(script, "w") as f:
        f.write("Execute SYS:System/Network/AROSTCP/S/startnet\nWait 4\n")
        f.write("C:ipv6test eth0 %s >SYS:out/aros.log\n" % " ".join(a.cases))
    env = dict(os.environ, AROS_HOSTED_IMAGE=a.image, AROS_TAP_IP=AROS_IP, AROS_RUN_TIMEOUT="200")
    if a.arostcp:
        env["AROS_AROSTCP"] = os.path.abspath(a.arostcp)
    boot = subprocess.run([os.path.join(ROOT, "tools", "hosted-run.sh"), os.path.join(a.out, "boot"), script, exe],
                          env=env, capture_output=True, text=True)
    time.sleep(1)
    peer.stop.set(); peer.join(2)
    subprocess.run(["sudo", "kill", str(dump.pid)], stderr=subprocess.DEVNULL)
    dump.wait(5)

    aros_log = os.path.join(a.out, "boot", "out", "aros.log")
    lines = open(aros_log).read().splitlines() if os.path.exists(aros_log) else []
    dump_text = open(dump_path).read()
    mld = mld_events(dump_text, host_ll)
    mldt = mld_events(dump_text, host_ll, with_time=True)
    marks = capture_markers(dump_text)
    results, failed = [], 0
    for line in lines:
        if line.startswith(("ok ", "not ok ")):
            ok = line.startswith("ok ")
            body = line[3:] if ok else line[7:]
            results.append((ok, body)); failed += not ok
        elif line.startswith("host "):
            _, case, what = line.split(" ", 2)
            ok, detail = host_check(case, what, peer.rx, mld, mldt, peer.ping, marks)
            results.append((ok, "%s host:%s # %s" % (case, what.split()[0], detail))); failed += not ok
        elif line.startswith("info "):
            results.append((None, line[5:]))

    with open(os.path.join(a.out, "report.txt"), "w") as f:
        for ok, body in results:
            tag = "info  " if ok is None else ("PASS  " if ok else "FAIL  ")
            print(tag + body); f.write(tag + body + "\n")
        summary = "image=%s arostcp=%s  checks=%d  failed=%d  boot=%s" % (
            a.image, a.arostcp or "(image)", sum(1 for o, _ in results if o is not None), failed,
            "ok" if lines and lines[-1].startswith("done") else "INCOMPLETE")
        print(summary); f.write(summary + "\n")
    json.dump({"peer_rx": peer.rx, "mld": mldt, "markers": marks, "host_sent": peer.sent, "ping": peer.ping}, open(os.path.join(a.out, "host.json"), "w"), indent=1)
    if not lines:
        print(boot.stdout, boot.stderr)
    return 1 if failed or not lines else 0


if __name__ == "__main__":
    sys.exit(main())
