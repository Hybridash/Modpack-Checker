#!/usr/bin/env python3
"""Check that the mods in a folder are compatible, using the Modrinth API.

usage: modpack_checker.py MODS_DIR [--mc 1.20.1] [--loader fabric]
"""
import argparse, hashlib, json, sys, urllib.request
from collections import Counter
from pathlib import Path

API = "https://api.modrinth.com/v2"
UA = {"User-Agent": "Hybridash/Modpack-Checker", "Content-Type": "application/json"}


def api(path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + path, data=data, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def analyze(versions, mc=None, loader=None):
    """versions: {filename: modrinth version dict}. Returns (mc, loader, problems)."""
    if not mc:  # ponytail: majority vote; pass --mc if the pack is mixed
        c = Counter(g for v in versions.values() for g in v["game_versions"])
        mc = c.most_common(1)[0][0] if c else None
    if not loader:
        c = Counter(l for v in versions.values() for l in v["loaders"])
        loader = c.most_common(1)[0][0] if c else None

    by_project = {v["project_id"]: f for f, v in versions.items()}
    problems = []
    for f, v in versions.items():
        if mc and mc not in v["game_versions"]:
            problems.append((f, f"built for MC {', '.join(v['game_versions'][-3:])}, not {mc}"))
        if loader and loader not in v["loaders"]:
            problems.append((f, f"loader is {', '.join(v['loaders'])}, not {loader}"))
        for d in v["dependencies"]:
            pid, kind = d.get("project_id"), d["dependency_type"]
            if kind == "required" and pid and pid not in by_project:
                problems.append((f, f"missing required dependency {pid}"))
            elif kind == "incompatible" and pid in by_project:
                problems.append((f, f"incompatible with {by_project[pid]}"))
    return mc, loader, problems


def names(ids):
    if not ids:
        return {}
    q = urllib.request.quote(json.dumps(sorted(ids)))
    return {p["id"]: p["title"] for p in api(f"/projects?ids={q}")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mods_dir")
    ap.add_argument("--mc")
    ap.add_argument("--loader")
    a = ap.parse_args()

    jars = sorted(Path(a.mods_dir).glob("*.jar"))
    if not jars:
        sys.exit("no .jar files found")
    hashes = {hashlib.sha1(j.read_bytes()).hexdigest(): j.name for j in jars}
    found = api("/version_files", {"hashes": list(hashes), "algorithm": "sha1"})
    versions = {hashes[h]: v for h, v in found.items()}
    unknown = [n for h, n in hashes.items() if h not in found]

    mc, loader, problems = analyze(versions, a.mc, a.loader)
    print(f"{len(jars)} mods | target: MC {mc}, {loader}")

    # replace raw project ids in messages with mod titles
    ids = {w for _, m in problems for w in m.split() if len(w) == 8 and w.isalnum()}
    for pid, title in names(ids).items():
        problems = [(f, m.replace(pid, title)) for f, m in problems]

    for f, m in problems:
        print(f"  ✗ {f}: {m}")
    for n in unknown:
        print(f"  ? {n}: not on Modrinth, can't check")
    if not problems:
        print("  ✓ no compatibility problems found")
    sys.exit(1 if problems else 0)


def demo():
    v = lambda pid, gv, ld, deps=(): dict(project_id=pid, game_versions=gv, loaders=ld,
                                          dependencies=[dict(project_id=p, dependency_type=t) for p, t in deps])
    vs = {"a.jar": v("A", ["1.20.1"], ["fabric"], [("LIB", "required"), ("B", "incompatible")]),
          "b.jar": v("B", ["1.20.1"], ["fabric"]),
          "c.jar": v("C", ["1.19.2"], ["forge"])}
    mc, ld, p = analyze(vs)
    assert (mc, ld) == ("1.20.1", "fabric") or mc in ("1.20.1", "1.19.2")
    msgs = [m for _, m in p]
    assert any("missing required" in m for m in msgs)
    assert any("incompatible with b.jar" in m for m in msgs)
    assert any("loader is forge" in m for m in msgs)
    print("demo ok")


if __name__ == "__main__":
    demo() if sys.argv[1:] == ["--demo"] else main()
