#!/usr/bin/env python3
"""
nd6_mem.py - what IPv6 neighbour cache entries cost AROS's memory, on the
emulated Amiga (m68k, tools/amiga-run.sh) or hosted AROS.

The host sends Neighbor Solicitations to AROS's link-local address from
fe80::a:0:0:N (N counting from 0), each with its own link-layer address:
each makes an entry (RFC 4861 section 7.2.3). AROS answers each with an
advertisement, which puts the entry in DELAY; nobody answers the probes
that follow, and the entry is deleted some 8 s later (section 7.3.3) -
a flood cleans itself up. So each step sends its burst afresh and AROS's
C:nd6mem counts the entries on eth0 (GetRouteInfo, as ip -6 neigh) a
second later, then records its free memory:
  rest            before any flood
  n64, n256, n300 that many sources (eth0's cache holds nd6_maxnbrs = 256)
  gone64, ...     15 s after each: the entries expired
  again256        256 once more, after all that: does the memory climb again?
The stack allocates from its own pool (CreatePool, 128 KB puddles): free
memory moves when a puddle is taken or given back, not per entry. The
entries' own size is sizeof(struct llinfo_nd6) in a pooled vector.

    nd6_mem.py [--mode amiga|hosted] [--system DIR] [--out DIR]
Needs sudo -n (raw frames on aros0).
"""
import argparse, json, os, re, socket, struct, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tests", "stack"))


def csum(data):
    if len(data) % 2:
        data += b"\0"
    s = sum(struct.unpack("!%dH" % (len(data) // 2), data))
    while s >> 16:
        s = (s & 0xffff) + (s >> 16)
    return ~s & 0xffff


def send_ns(iface, target, first, count):
    """count NSes to target from fe80::a:0:0:N, N = first.. (run as root)"""
    t = socket.inet_pton(socket.AF_INET6, target)
    group = bytes.fromhex("ff0200000000000000000001ff") + t[13:]   # ff02::1:ffXX:XXXX
    gmac = b"\x33\x33" + group[12:]
    s = socket.socket(socket.AF_PACKET, socket.SOCK_RAW)
    s.bind((iface, 0))
    for n in range(first, first + count):
        src = bytes.fromhex("fe80000000000000000a00000000") + struct.pack("!H", n)
        mac = b"\x02\xaa\x00\x00" + struct.pack("!H", n)
        icmp = struct.pack("!BBHI", 135, 0, 0, 0) + t + struct.pack("!BB", 1, 1) + mac
        pseudo = src + group + struct.pack("!I", len(icmp)) + b"\0\0\0\x3a"
        icmp = icmp[:2] + struct.pack("!H", csum(pseudo + icmp)) + icmp[4:]
        ip6 = struct.pack("!IHBB", 0x60000000, len(icmp), 58, 255) + src + group
        s.send(gmac + mac + b"\x86\xdd" + ip6 + icmp)
        time.sleep(0.004)
    s.close()


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--send":
        send_ns(sys.argv[2], sys.argv[3], int(sys.argv[4]), int(sys.argv[5]))
        return
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("amiga", "hosted"), default="amiga")
    ap.add_argument("--system")
    ap.add_argument("--out", default=os.path.join(HERE, "out", "nd6mem-" + time.strftime("%Y%m%d-%H%M%S")))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    import memcost
    amiga = a.mode == "amiga"
    exe = memcost.build(a.out, "nd6mem", os.path.join(HERE, "nd6mem.c"), amiga=amiga)
    steps = []
    for n in (64, 256, 300):
        steps += [("n%d" % n, 0, n), ("gone%d" % n, None, 15)]
    # the second round: the same load again; memory that keeps climbing
    # would be a leak, memory that comes back to the plateau is kept for reuse
    steps += [("again256", 0, 256), ("goneagain", None, 15)]
    script = os.path.join(a.out, "s.script")
    with open(script, "w") as f:
        if amiga:
            f.write("Delete >NIL: SYS:System/Network/AROSTCP/db/services.d/#? QUIET\n")
        f.write("Execute SYS:System/Network/AROSTCP/S/startnet\nWait %d\n" % (40 if amiga else 15))
        f.write("C:nd6mem rest >>SYS:out/mem.log\nEcho >>SYS:out/mbuf.log \"== rest\"\nC:netstat -m >>SYS:out/mbuf.log\n"
                "Echo >SYS:out/ready0 r\n")
        for i, (label, first, n) in enumerate(steps, 1):
            # wait for the host's go, by polling for the file
            f.write("Lab w%d\nIf NOT EXISTS SYS:out/go%d\n Wait 1\n Skip w%d BACK\nEndIf\n" % (i, i, i))
            f.write("Wait 1\nC:nd6mem %s >>SYS:out/mem.log\n" % label)
            f.write("Echo >>SYS:out/mbuf.log \"== %s\"\nC:netstat -m >>SYS:out/mbuf.log\n" % label)
            f.write("Echo >SYS:out/ready%d r\n" % i)
        f.write("C:ip -6 neigh >SYS:out/neigh.log\n")
    env = dict(os.environ)
    subprocess.run([os.path.join(ROOT, "tools", "tap-up.sh"), "0"], check=True, stdout=subprocess.DEVNULL)
    if amiga:
        if a.system:
            env["AMIGA_SYSTEM"] = a.system
        env.update(AMIGA_TAP_IP="192.168.166.2", AMIGA_RUN_TIMEOUT="900")
        run = [os.path.join(ROOT, "tools", "amiga-run.sh"), os.path.join(a.out, "aros"), script, exe]
        outdir = os.path.join(a.out, "aros", "AROS", "out")
    else:
        if a.system:
            env["AROS_HOSTED_IMAGE"] = a.system
        env.update(AROS_TAP_IP="192.168.166.2", AROS_RUN_TIMEOUT="600")
        run = [os.path.join(ROOT, "tools", "hosted-run.sh"), os.path.join(a.out, "aros"), script, exe]
        outdir = os.path.join(a.out, "aros", "AROS", "out")
    p = subprocess.Popen(run, env=env, stdout=open(os.path.join(a.out, "run.txt"), "w"), stderr=subprocess.STDOUT)

    def wait_for(name, secs):
        t0 = time.time()
        while time.time() - t0 < secs:
            for d in (outdir, os.path.join(a.out, "aros", "out")):
                if os.path.exists(os.path.join(d, name)):
                    return d
            if p.poll() is not None:
                return None
            time.sleep(0.5)
        return None

    d = wait_for("ready0", 600)
    if d is None:
        print("AROS did not get ready")
        p.wait()
        return
    # AROS's link-local address, from its MAC (EUI-64): ARP after a ping to
    # its IPv4 address (not ifconfig -a, which overflows a 4 KB Amiga stack:
    # bugs.md B39; AROS does not answer echo to ff02::1)
    subprocess.run(["ping", "-c", "2", "-w", "4", "192.168.166.2"], capture_output=True)
    neigh = subprocess.run(["ip", "neigh", "show", "192.168.166.2", "dev", "aros0"],
                           capture_output=True, text=True).stdout
    m = re.search(r"lladdr ([0-9a-f:]{17})", neigh)
    target = None
    if m:
        b = bytes.fromhex(m.group(1).replace(":", ""))
        eui = bytes([b[0] ^ 2]) + b[1:3] + b"\xff\xfe" + b[3:]
        target = socket.inet_ntop(socket.AF_INET6, bytes.fromhex("fe80000000000000") + eui)
    if target is None:
        print("AROS's link-local address did not answer")
        p.wait()
        return
    for i, (label, first, n) in enumerate(steps, 1):
        if first is not None:
            subprocess.run(["sudo", "-n", sys.executable, os.path.abspath(__file__), "--send", "aros0", target,
                            str(first), str(n)], check=True)
        else:
            time.sleep(n)
        open(os.path.join(d, "go%d" % i), "w").close()
        if wait_for("ready%d" % i, 300) is None:
            print("no ready%d" % i)
            break
    p.wait()
    if not os.path.exists(os.path.join(d, "mem.log")):    # the run's copy, after it ended
        d = os.path.join(a.out, "aros", "out")
    rows = {}
    for line in open(os.path.join(d, "mem.log")):
        f = line.split()
        if len(f) >= 11:
            rows[f[0]] = dict(rows=int(f[2]), flood=int(f[4]), lladdr=int(f[6]), free=int(f[8]), largest=int(f[10]))
    mb = os.path.join(d, "mbuf.log")
    if os.path.exists(mb):
        label = None
        for line in open(mb):
            m = re.match(r"== (\w+)", line)
            if m:
                label = m.group(1)
            m = re.search(r"(\d+)\s*K?bytes? allocated to network", line) or re.search(r"(\d+)K bytes allocated", line)
            if m and label in rows:
                rows[label]["mbuf_line"] = line.strip()
    res = {"mode": a.mode, "target": target, "steps": rows}
    base = rows.get("rest")
    if base:
        for k, v in rows.items():
            v["taken"] = base["free"] - v["free"]
        for x, y in (("rest", "n64"), ("rest", "n256"), ("rest", "n300")):
            if x in rows and y in rows and rows[y]["rows"] != rows[x]["rows"]:
                res["per_entry_%s_%s" % (x, y)] = round((rows[x]["free"] - rows[y]["free"]) /
                                                         (rows[y]["rows"] - rows[x]["rows"]), 1)
    json.dump(res, open(os.path.join(a.out, "result.json"), "w"), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
