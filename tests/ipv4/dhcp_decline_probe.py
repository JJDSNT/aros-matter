#!/usr/bin/env python3
"""
dhcp_decline_probe.py - AROS declining a DHCP address another host uses
(RFC 2131 section 3.1 (5), with the stack's conflict detection, RFC 5227).

AROS's eth0 (tap aros0) is IP=DHCP. tests/ipv4/dhcpserv.py on the host
offers 192.168.166.50 first, then .51; the host itself holds .50 on aros0
(a second address: Linux answers ARP probes for it), so .50 is in use.
Expected: AROS takes .50, finds it in use, sends DHCPDECLINE, and some
10 s later is bound to .51. Before the change: bound to .50 with the host.

    dhcp_decline_probe.py [--arostcp FILE] [--dhclient FILE] [--image DIR] [--out DIR]
Needs sudo -n (port 67, ip addr).
"""
import argparse, json, os, shutil, subprocess, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
TAP, SERVER, INUSE, NEXT = "aros0", "192.168.166.1", "192.168.166.50", "192.168.166.51"


def sh(*a):
    return subprocess.run(["sudo", "-n"] + list(a), capture_output=True, text=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", default=os.environ.get("AROS_HOSTED_IMAGE",
        os.path.expanduser("~/aros-build-ipv6-hosted-claude/bin/linux-x86_64/AROS")))
    ap.add_argument("--arostcp")
    ap.add_argument("--dhclient", help="boot with this dhclient")
    ap.add_argument("--out", default=os.path.join(HERE, "out", "decline-" + time.strftime("%Y%m%d-%H%M%S")))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    subprocess.run([os.path.join(ROOT, "tools", "tap-up.sh")], check=True, stdout=subprocess.DEVNULL)
    sh("ip", "addr", "add", INUSE + "/32", "dev", TAP)
    log = os.path.join(a.out, "dhcp.jsonl")
    open(log, "w").close()
    srv = subprocess.Popen(["sudo", "-n", "python3", "-I", os.path.join(HERE, "dhcpserv.py"), TAP, SERVER,
                            INUSE, NEXT, "110", log])
    script = os.path.join(a.out, "decline.script")
    files = []
    with open(script, "w") as f:
        if a.dhclient:
            d = os.path.join(a.out, "dhc")
            os.makedirs(d, exist_ok=True)
            shutil.copy(a.dhclient, os.path.join(d, "dhclient"))
            files.append(os.path.join(d, "dhclient"))
            f.write("Copy C:dhclient SYS:System/Network/AROSTCP/C/dhclient\n")
        f.write("Execute SYS:System/Network/AROSTCP/S/startnet\nWait 60\n")
        f.write("C:ifconfig eth0 >SYS:out/if0.log\n")
    env = dict(os.environ, AROS_HOSTED_IMAGE=a.image, AROS_TAP_IP="DHCP", AROS_RUN_TIMEOUT="150")
    if a.arostcp:
        env["AROS_AROSTCP"] = os.path.abspath(a.arostcp)
    try:
        r = subprocess.run([os.path.join(ROOT, "tools", "hosted-run.sh"), os.path.join(a.out, "aros"), script] + files,
                           env=env, capture_output=True, text=True)
    finally:
        sh("pkill", "-f", "dhcpserv.py %s" % TAP)
        srv.wait(timeout=10)
        sh("ip", "addr", "del", INUSE + "/32", "dev", TAP)
    msgs = [json.loads(l) for l in open(log)]
    ifc = os.path.join(a.out, "aros", "out", "if0.log")
    inet = [l.strip() for l in open(ifc)] if os.path.exists(ifc) else []
    inet = [l for l in inet if l.startswith("inet ")]
    res = {"boot": "ok" if "finished" in r.stdout else "did not finish",
           "dhcp": [m.get("got") or ("> " + m["sent"]) for m in msgs],
           "declined": [m.get("requested") for m in msgs if m.get("got") == "DECLINE"],
           "acked": [m["yiaddr"] for m in msgs if m.get("sent") == "ACK"],
           "ifconfig_eth0": inet}
    # the bench checks itself: the server heard AROS, and acknowledged .50 first
    res["sanity"] = {"server_heard_aros": any(m.get("got") == "DISCOVER" for m in msgs),
                     "offered_inuse_first": bool(res["acked"]) and res["acked"][0] == INUSE}
    res["sanity"]["ok"] = all(res["sanity"].values())
    json.dump(res, open(os.path.join(a.out, "result.json"), "w"), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
