#!/usr/bin/env python3
"""
ecn_probe.py - ECN (RFC 3168) between hosted AROS and the Linux host, over
IPv4 and IPv6.

The host opens the connections, with ECN asked for by its route only
("features ecn"; the global net.ipv4.tcp_ecn is left alone). AROS
(tcpserve) accepts four: per family one where it sends 1 MB and one where
the host sends 1 MB. Before them AROS opens a connection itself (tcpbench),
which gives the host AROS's address and shows whether AROS asks for ECN. Both directions go through a 5 Mbit/s bottleneck with
fq_codel marking CE past 1 ms of queue (an ifb for AROS's direction), so ECT
packets are marked, never dropped.

For each connection it reports, from the capture: the SYN-ACK's ECE/CWR,
how AROS's data was marked (ECT(0), CE), and the ECE/CWR each side sent.

    ecn_probe.py [--arostcp FILE] [--image DIR] [--no-ce] [--out DIR]

Needs sudo -n for tcpdump, tc and ip.
"""
import argparse, json, os, re, socket, struct, subprocess, sys, threading, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import run_tcp   # CROSS, IFACE, AROS_IP, tc helpers

IFACE = run_tcp.IFACE
HOST4 = "192.168.166.1"
BYTES = 1000000
PORTS = {"send6": 7010, "send4": 7011, "recv6": 7012, "recv4": 7013}
CLIENT_PORT = 7002


def sh(*a, check=False):
    return subprocess.run(["sudo", "-n"] + list(a), capture_output=True, text=True, check=check)


def routes(ecn):
    """The tap's two routes, with or without "features ecn"."""
    f = ["features", "ecn"] if ecn else []
    sh("ip", "route", "replace", "192.168.166.0/24", "dev", IFACE, "proto", "kernel",
       "scope", "link", "src", HOST4, *f)
    sh("ip", "-6", "route", "replace", "fe80::/64", "dev", IFACE, "proto", "kernel",
       "metric", "256", *f)


def shaping(on):
    sh("tc", "qdisc", "del", "dev", IFACE, "root")
    sh("tc", "qdisc", "del", "dev", IFACE, "ingress")
    sh("ip", "link", "del", "ifb-ecn")
    if not on:
        return
    for dev in (IFACE, "ifb-ecn"):
        if dev == "ifb-ecn":
            sh("ip", "link", "add", "ifb-ecn", "type", "ifb", check=True)
            sh("ip", "link", "set", "ifb-ecn", "up", check=True)
            sh("tc", "qdisc", "add", "dev", IFACE, "handle", "ffff:", "ingress", check=True)
            sh("tc", "filter", "add", "dev", IFACE, "parent", "ffff:", "matchall",
               "action", "mirred", "egress", "redirect", "dev", "ifb-ecn", check=True)
        sh("tc", "qdisc", "add", "dev", dev, "root", "handle", "1:", "tbf", "rate", "5mbit",
           "burst", "16k", "latency", "200ms", check=True)
        sh("tc", "qdisc", "add", "dev", dev, "parent", "1:1", "fq_codel", "ecn",
           "ce_threshold", "1ms", check=True)


def host_side(res, deadline):
    """Open AROS's four connections as tcpserve brings them up, in order."""
    # AROS's address: from its own connection to the host, which comes first
    while "aros_ll" not in res and time.time() < deadline:
        time.sleep(0.5)
    ll = res.get("aros_ll")
    if ll is None:
        return
    idx = socket.if_nametoindex(IFACE)
    for name in ("send6", "send4", "recv6", "recv4"):
        addr = (ll, PORTS[name], 0, idx) if name.endswith("6") else (run_tcp.AROS_IP, PORTS[name])
        fam = socket.AF_INET6 if name.endswith("6") else socket.AF_INET
        got = None
        while got is None and time.time() < deadline:
            s = socket.socket(fam, socket.SOCK_STREAM)
            s.settimeout(30)
            try:
                s.connect(addr)
                n = 0
                if name.startswith("send"):
                    while True:
                        b = s.recv(65536)
                        if not b:
                            break
                        n += len(b)
                else:
                    blk = b"y" * 16384
                    while n < BYTES:
                        s.sendall(blk)
                        n += len(blk)
                    s.shutdown(socket.SHUT_WR)
                    s.recv(1)
                got = n
            except (ConnectionRefusedError, OSError):
                time.sleep(0.5)
            finally:
                s.close()
        res[name] = got


def client_listener(res, deadline):
    """AROS's connection to the host; its address is where the host's go."""
    s = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("::", CLIENT_PORT))
    s.listen(4)
    s.settimeout(max(1, deadline - time.time()))
    try:
        c, peer = s.accept()
        res["aros_ll"] = peer[0].split("%")[0]
        c.settimeout(10)
        try:
            while c.recv(65536):
                pass
        except socket.timeout:
            pass
        c.close()
    except socket.timeout:
        pass
    s.close()


def packets(pcap):
    """(src, sport, dst, dport, tcp flags, ECN codepoint, payload length) of
    each TCP packet in an Ethernet pcap."""
    out = []
    with open(pcap, "rb") as f:
        hdr = f.read(24)
        if len(hdr) < 24:
            return out
        end = "<" if hdr[:4] == b"\xd4\xc3\xb2\xa1" else ">"
        while True:
            rh = f.read(16)
            if len(rh) < 16:
                break
            incl = struct.unpack(end + "IIII", rh)[2]
            fr = f.read(incl)
            if len(fr) < 14:
                continue
            et = struct.unpack("!H", fr[12:14])[0]
            ip = fr[14:]
            if et == 0x0800 and len(ip) >= 20 and ip[9] == 6:
                hl = (ip[0] & 15) * 4
                ecn = ip[1] & 3
                plen = struct.unpack("!H", ip[2:4])[0] - hl
                src, dst = socket.inet_ntop(socket.AF_INET, ip[12:16]), socket.inet_ntop(socket.AF_INET, ip[16:20])
                tcp = ip[hl:]
            elif et == 0x86dd and len(ip) >= 40 and ip[6] == 6:
                ecn = (struct.unpack("!I", ip[0:4])[0] >> 20) & 3
                plen = struct.unpack("!H", ip[4:6])[0]
                src, dst = socket.inet_ntop(socket.AF_INET6, ip[8:24]), socket.inet_ntop(socket.AF_INET6, ip[24:40])
                tcp = ip[40:]
            else:
                continue
            if len(tcp) < 14:
                continue
            sp, dp = struct.unpack("!HH", tcp[0:4])
            doff = (tcp[12] >> 4) * 4
            out.append((src, sp, dst, dp, tcp[13], ecn, plen - doff))
    return out


FIN, SYN, ACK, ECE, CWR = 0x01, 0x02, 0x10, 0x40, 0x80


def analyse(pkts, aros4, aros6):
    aros = {aros4, aros6}
    res = {}
    for name, port in list(PORTS.items()) + [("client", None)]:
        if port is None:      # AROS's own connection to the host
            mine = [p for p in pkts if (p[0] in aros and p[3] == CLIENT_PORT) or (p[2] in aros and p[1] == CLIENT_PORT)]
            syn = [p for p in mine if p[0] in aros and p[4] & SYN and not p[4] & ACK]
            res[name] = {"syn_ece": bool(syn and syn[0][4] & ECE), "syn_cwr": bool(syn and syn[0][4] & CWR),
                         "syn_seen": bool(syn)}
            continue
        mine = [p for p in pkts if (p[0] in aros and p[1] == port) or (p[2] in aros and p[3] == port)]
        frm = [p for p in mine if p[0] in aros]
        to = [p for p in mine if p[2] in aros]
        synack = [p for p in frm if p[4] & SYN and p[4] & ACK]
        syn = [p for p in to if p[4] & SYN and not p[4] & ACK]
        data_from = [p for p in frm if p[6] > 0]
        data_to = [p for p in to if p[6] > 0]
        res[name] = {
            "host_syn_ece_cwr": bool(syn and syn[0][4] & ECE and syn[0][4] & CWR),
            "synack_ece": bool(synack and synack[0][4] & ECE),
            "synack_cwr": bool(synack and synack[0][4] & CWR),
            "aros_data": len(data_from),
            "aros_data_ect0": sum(1 for p in data_from if p[5] == 2),
            "aros_data_ce": sum(1 for p in data_from if p[5] == 3),
            "host_data": len(data_to),
            "host_data_ce": sum(1 for p in data_to if p[5] == 3),
            "aros_ece": sum(1 for p in frm if p[4] & ECE and not p[4] & SYN),
            "aros_cwr": sum(1 for p in frm if p[4] & CWR and not p[4] & SYN),
            "host_ece": sum(1 for p in to if p[4] & ECE and not p[4] & SYN),
            "host_cwr": sum(1 for p in to if p[4] & CWR and not p[4] & SYN),
        }
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", default=os.environ.get("AROS_HOSTED_IMAGE",
        os.path.expanduser("~/aros-build-ipv6-hosted-claude/bin/linux-x86_64/AROS")))
    ap.add_argument("--arostcp")
    ap.add_argument("--no-ce", action="store_true", help="no bottleneck: negotiation and marking only")
    ap.add_argument("--out", default=os.path.join(ROOT, "tests", "tcp", "out", "ecn-" + time.strftime("%Y%m%d-%H%M%S")))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    exes = []
    for prog in ("tcpserve", "tcpbench"):
        exe = os.path.join(a.out, prog)
        subprocess.run([run_tcp.CROSS, "-std=gnu99", "-O2", "-Wall", "-Wno-pointer-sign", "-o", exe,
                        os.path.join(HERE, prog + ".c")], check=True)
        exes.append(exe)
    subprocess.run([os.path.join(ROOT, "tools", "tap-up.sh")], check=True, stdout=subprocess.DEVNULL)
    host_ll = [x for x in re.findall(r"inet6 (fe80::[0-9a-f:]+)/", subprocess.run(
        ["ip", "-6", "addr", "show", "dev", IFACE], capture_output=True, text=True).stdout)][0]
    run_tcp.kill_strays()
    routes(True)
    shaping(not a.no_ce)

    script = os.path.join(a.out, "ecn.script")
    with open(script, "w") as f:
        f.write("Execute SYS:System/Network/AROSTCP/S/startnet\nWait 4\n")
        f.write("C:tcpbench eth0 %s connect %d 1 >SYS:out/client.log\n" % (host_ll, CLIENT_PORT))
        f.write("C:tcpserve 6 %d send %d >SYS:out/send6.log\n" % (PORTS["send6"], BYTES))
        f.write("C:tcpserve 4 %d send %d >SYS:out/send4.log\n" % (PORTS["send4"], BYTES))
        f.write("C:tcpserve 6 %d recv 0 >SYS:out/recv6.log\n" % PORTS["recv6"])
        f.write("C:tcpserve 4 %d recv 0 >SYS:out/recv4.log\n" % PORTS["recv4"])
    pcap = os.path.join(a.out, "ecn.pcap")
    dump = subprocess.Popen(["sudo", "-n", "tcpdump", "-U", "-i", IFACE, "-n", "-s", "96", "-w", pcap, "tcp"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1)
    host = {}
    threading.Thread(target=client_listener, args=(host, time.time() + 60), daemon=True).start()
    th = threading.Thread(target=host_side, args=(host, time.time() + 250), daemon=True)
    th.start()
    env = dict(os.environ, AROS_HOSTED_IMAGE=a.image, AROS_TAP_IP=run_tcp.AROS_IP, AROS_RUN_TIMEOUT="300")
    if a.arostcp:
        env["AROS_AROSTCP"] = a.arostcp
    r = subprocess.run([os.path.join(ROOT, "tools", "hosted-run.sh"), os.path.join(a.out, "aros"), script] + exes,
                       env=env, capture_output=True, text=True)
    th.join(timeout=5)
    shaping(False)
    routes(False)
    time.sleep(1)
    for pid in subprocess.run(["pgrep", "-f", "^tcpdump -U -i %s -n -s 96 -w %s" % (IFACE, pcap)],
                              capture_output=True, text=True).stdout.split():
        sh("kill", "-INT", pid)
    dump.wait(timeout=10)
    sh("chmod", "a+r", pcap)

    res = {"boot": "ok" if "finished" in r.stdout else "did not finish", "ce_marking": not a.no_ce,
           "host": host}
    res["connections"] = analyse(packets(pcap), run_tcp.AROS_IP, host.get("aros_ll"))
    # the bench checks itself: AROS found, every transfer whole, all of it captured
    conns = res["connections"]
    res["sanity"] = {"aros_found": host.get("aros_ll") is not None,
                     "transfers_whole": all((host.get(n) or 0) >= BYTES for n in PORTS),
                     "captured": all(conns[n]["aros_data"] + conns[n]["host_data"] > 0 for n in PORTS)}
    res["sanity"]["ok"] = all(res["sanity"].values())
    json.dump(res, open(os.path.join(a.out, "result.json"), "w"), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
