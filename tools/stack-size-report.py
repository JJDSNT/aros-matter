#!/usr/bin/env python3
"""
stack-size-report.py OLD NEW [--size TOOL] [--nm TOOL] [--src REPO] [--json FILE]

Compare two AROSTCP builds kept by tools/stack-size-hist.sh (OLD and NEW are
OUTDIR/<commit>/<arch>): the binary's .text/.data/.bss, the same per object
file and per subsystem (the directory of its source: api, kern, net, netinet,
netinet6), the objects that grew or appeared most, and the functions and
objects (nm sizes) that grew most.

Each object is placed in a subsystem from the AROSTCP sources of the commit
the directory is named after (git ls-tree in --src, default ~/AROS-hist).
"""
import argparse, json, os, re, subprocess, sys

T68 = os.path.expanduser("~/aros-build-emu68-m68k/bin/linux-x86_64/tools/crosstools")


def sections(size, path):
    out = subprocess.run([size, path], capture_output=True, text=True).stdout.splitlines()
    for line in out[1:]:
        p = line.split()
        if len(p) >= 3 and p[0].isdigit():
            return int(p[0]), int(p[1]), int(p[2])
    return 0, 0, 0


def groups(src, commit):
    """object basename -> subsystem, from the sources at commit."""
    out = subprocess.run(["git", "-C", src, "ls-tree", "-r", "--name-only", commit,
                          "workbench/network/stacks/AROSTCP/bsdsocket"], capture_output=True, text=True).stdout
    g = {}
    for path in out.splitlines():
        if path.endswith(".c"):
            parts = path.split("/")
            sub = parts[-2] if parts[-2] != "bsdsocket" else "top"
            g[os.path.splitext(parts[-1])[0]] = sub
    return g


def symbols(nm, path):
    out = subprocess.run([nm, "--size-sort", "-S", path], capture_output=True, text=True).stdout
    s = {}
    for line in out.splitlines():
        p = line.split()
        if len(p) == 4 and p[2] in "tTdDbBrR":
            s[p[3]] = s.get(p[3], 0) + int(p[1], 16)
    return s


def load(d, size, nm, src):
    commit = os.path.basename(os.path.dirname(os.path.normpath(d)))
    g = groups(src, commit)
    objs = {}
    for f in sorted(os.listdir(os.path.join(d, "obj"))):
        if f.endswith(".o"):
            name = f[:-2]
            objs[name] = {"sec": sections(size, os.path.join(d, "obj", f)), "group": g.get(name, "?")}
    return {"commit": commit, "bin": sections(size, os.path.join(d, "AROSTCP")),
            "objs": objs, "syms": symbols(nm, os.path.join(d, "AROSTCP"))}


def fmt(a, b):
    return "%7d %7d %+7d" % (a, b, b - a)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("old"); ap.add_argument("new")
    ap.add_argument("--size", default=os.path.join(T68, "m68k-aros-size"))
    ap.add_argument("--nm", default=os.path.join(T68, "m68k-aros-nm"))
    ap.add_argument("--src", default=os.path.expanduser("~/AROS-hist"))
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--json")
    a = ap.parse_args()
    o, n = load(a.old, a.size, a.nm, a.src), load(a.new, a.size, a.nm, a.src)
    print("AROSTCP %s -> %s" % (o["commit"], n["commit"]))
    print("%-10s %7s %7s %7s" % ("section", "old", "new", "diff"))
    for i, name in enumerate(("text", "data", "bss")):
        print("%-10s %s" % (name, fmt(o["bin"][i], n["bin"][i])))
    print("%-10s %s" % ("total", fmt(sum(o["bin"]), sum(n["bin"]))))

    def bygroup(x):
        r = {}
        for v in x["objs"].values():
            t = r.setdefault(v["group"], [0, 0, 0])
            for i in range(3):
                t[i] += v["sec"][i]
        return r
    go, gn = bygroup(o), bygroup(n)
    print("\nper subsystem (text+data+bss of its objects)")
    print("%-10s %7s %7s %7s   %s" % ("", "old", "new", "diff", "text diff"))
    for k in sorted(set(go) | set(gn), key=lambda k: -(sum(gn.get(k, [0] * 3)) - sum(go.get(k, [0] * 3)))):
        a0, b0 = go.get(k, [0] * 3), gn.get(k, [0] * 3)
        print("%-10s %s   %+d" % (k, fmt(sum(a0), sum(b0)), b0[0] - a0[0]))
    print("\nobjects that grew or appeared most (text+data+bss)")
    diffs = []
    for k in set(o["objs"]) | set(n["objs"]):
        a0 = sum(o["objs"][k]["sec"]) if k in o["objs"] else 0
        b0 = sum(n["objs"][k]["sec"]) if k in n["objs"] else 0
        grp = (n["objs"].get(k) or o["objs"].get(k))["group"]
        diffs.append((b0 - a0, k, grp, a0, b0))
    for d, k, grp, a0, b0 in sorted(diffs, reverse=True)[:a.top]:
        print("%-22s %-9s %s%s" % (k, grp, fmt(a0, b0), "  (new)" if a0 == 0 else ""))
    print("\nsymbols that grew or appeared most")
    sd = []
    for k in set(o["syms"]) | set(n["syms"]):
        sd.append((n["syms"].get(k, 0) - o["syms"].get(k, 0), k, o["syms"].get(k, 0), n["syms"].get(k, 0)))
    for d, k, a0, b0 in sorted(sd, reverse=True)[:a.top]:
        print("%-34s %s%s" % (k[:34], fmt(a0, b0), "  (new)" if a0 == 0 else ""))
    if a.json:
        json.dump({"old": o["commit"], "new": n["commit"], "bin": [o["bin"], n["bin"]],
                   "groups": [go, gn], "objects": diffs}, open(a.json, "w"), indent=1)


if __name__ == "__main__":
    main()
