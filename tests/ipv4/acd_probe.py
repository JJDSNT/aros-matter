#!/usr/bin/env python3
"""
acd_probe.py - AROS defending its IPv4 addresses against another host
(RFC 5227 section 2.4 for a configured address, RFC 3927 section 2.5 for
the 169.254/16 one autoip chose).

AROS has 192.168.166.2 on eth0 (tap aros0) and IP=AUTO on eth1 (aros1).
An "intruder" on the host (tests/ipv4/arpsend.py, a made-up MAC) sends a
gratuitous ARP claiming each address, twice, 3 s apart; captures of both
taps show what AROS did:
  - eth0: after the first claim AROS announces the address again (a
    defence) and still answers pings; after the second, within the 10 s
    DEFEND_INTERVAL, the address is duplicated: no more answers, and
    "duplicated" in ifconfig;
  - eth1: after the first claim a defence; after the second AROS gives the
    address up and probes a new 169.254 address.

    acd_probe.py [--arostcp FILE] [--image DIR] [--out DIR]
Needs sudo -n (tcpdump, raw frames) and the second tap (tools/tap-up.sh 1).
"""
import argparse, json, os, re, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
AROS_IP = "192.168.166.2"
INTRUDER = "02:00:00:00:00:99"


def ping(ip, n=3):
    r = subprocess.run(["ping", "-n", "-c", str(n), "-i", "0.3", "-W", "1", ip], capture_output=True, text=True)
    m = re.search(r"(\d+) received", r.stdout)
    return int(m.group(1)) if m else 0


def claim(iface, ip):
    """The intruder claims ip; the time just before (the capture's clock)."""
    t = time.time()
    subprocess.run(["sudo", "-n", "python3", "-I", os.path.join(HERE, "arpsend.py"), iface, INTRUDER, ip], check=True)
    return t


def arps(pcap):
    """(time, src MAC, op, target IP, sender IP) of each ARP in the capture."""
    out = []
    t = subprocess.run(["sudo", "-n", "tcpdump", "-tt", "-e", "-n", "-r", pcap], capture_output=True, text=True).stdout
    for line in t.splitlines():
        m = re.match(r"(\d+\.\d+) (\S+) > \S+, ethertype ARP.*?: (Request|Reply) (?:who-has )?(\S+)(?: \(\S+\))? (?:tell|is-at) (\S+)", line)
        if m:
            out.append((float(m.group(1)), m.group(2).lower(), m.group(3), m.group(4), m.group(5).rstrip(",")))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", default=os.environ.get("AROS_HOSTED_IMAGE",
        os.path.expanduser("~/aros-build-ipv6-hosted-claude/bin/linux-x86_64/AROS")))
    ap.add_argument("--arostcp")
    ap.add_argument("--out", default=os.path.join(HERE, "out", "acd-" + time.strftime("%Y%m%d-%H%M%S")))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    for n in ("0", "1"):
        subprocess.run([os.path.join(ROOT, "tools", "tap-up.sh"), n], check=True, stdout=subprocess.DEVNULL)
    dumps = {}
    for tap in ("aros0", "aros1"):
        pcap = os.path.join(a.out, tap + ".pcap")
        dumps[tap] = (pcap, subprocess.Popen(["sudo", "-n", "tcpdump", "-U", "-i", tap, "-n", "-w", pcap, "arp"],
                                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    time.sleep(1)
    script = os.path.join(a.out, "acd.script")
    with open(script, "w") as f:
        f.write("Execute SYS:System/Network/AROSTCP/S/startnet\nWait 75\n")
        f.write("C:ifconfig eth0 >SYS:out/if0.log\nC:ifconfig eth1 >SYS:out/if1.log\n")
    env = dict(os.environ, AROS_HOSTED_IMAGE=a.image, AROS_TAP_IP=AROS_IP, AROS_TAP2_IP="AUTO",
               AROS_RUN_TIMEOUT="200")
    if a.arostcp:
        env["AROS_AROSTCP"] = os.path.abspath(a.arostcp)
    aros = subprocess.Popen([os.path.join(ROOT, "tools", "hosted-run.sh"), os.path.join(a.out, "aros"), script],
                            env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    res = {}
    t0 = time.monotonic()
    while time.monotonic() - t0 < 90 and ping(AROS_IP, 1) == 0:
        time.sleep(1)
    res["pings_before"] = ping(AROS_IP)

    # eth0: a configured address
    c1 = claim("aros0", AROS_IP)
    time.sleep(1.5)
    res["pings_after_claim1"] = ping(AROS_IP)
    c2 = claim("aros0", AROS_IP)
    time.sleep(1.5)
    res["pings_after_claim2"] = ping(AROS_IP)

    # eth1: the address autoip chose, from its announcements
    ll = None
    for _ in range(30):
        for t, src, op, tgt, snd in arps(dumps["aros1"][0]):
            if op == "Request" and tgt == snd and tgt.startswith("169.254."):
                ll, aros1_mac = tgt, src
        if ll:
            break
        time.sleep(1)
    res["autoip_addr"] = ll
    if ll:
        time.sleep(2)
        d1 = claim("aros1", ll)
        time.sleep(3)
        d2 = claim("aros1", ll)
        time.sleep(8)
    out = aros.communicate()[0]
    for tap, (pcap, p) in dumps.items():
        subprocess.run(["sudo", "-n", "pkill", "-INT", "-f", "tcpdump -U -i %s -n -w %s" % (tap, pcap)])
        p.wait(timeout=10)
    res["boot"] = "ok" if "finished" in out else "did not finish"

    # what AROS sent after each claim
    a0 = [x for x in arps(dumps["aros0"][0]) if x[1] != INTRUDER]
    aros0_mac = a0[0][1] if a0 else None
    res["eth0_defended_after_claim1"] = any(c1 < t < c1 + 1.5 and tgt == snd == AROS_IP for t, src, op, tgt, snd in a0)
    res["eth0_announced_after_claim2"] = any(c2 < t < c2 + 1.5 and tgt == snd == AROS_IP for t, src, op, tgt, snd in a0)
    if ll:
        a1 = [x for x in arps(dumps["aros1"][0]) if x[1] != INTRUDER]
        res["eth1_defended_after_claim1"] = any(d1 < t < d1 + 1.5 and tgt == snd == ll for t, src, op, tgt, snd in a1)
        new = sorted({tgt for t, src, op, tgt, snd in a1 if t > d2 and snd == "0.0.0.0" and tgt != ll})
        res["eth1_new_probes_after_claim2"] = new
    for n in ("0", "1"):
        p = os.path.join(a.out, "aros", "out", "if%s.log" % n)
        res["ifconfig_eth" + n] = open(p).read().strip().splitlines() if os.path.exists(p) else None
    # the bench checks itself: AROS answered before, the intruder's frames were captured
    seen = [x for x in arps(dumps["aros0"][0]) if x[1] == INTRUDER]
    res["sanity"] = {"answered_before": res["pings_before"] > 0, "claims_captured": len(seen) == 2,
                     "autoip_seen": ll is not None}
    res["sanity"]["ok"] = all(res["sanity"].values())
    json.dump(res, open(os.path.join(a.out, "result.json"), "w"), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
