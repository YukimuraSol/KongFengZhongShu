#!/usr/bin/env python3
from __future__ import annotations
import argparse, importlib.util, json, sys
from pathlib import Path
APP = Path(r"d:\控分中枢\irminsul_scanner\app")

def load(name):
    spec = importlib.util.spec_from_file_location(name, APP / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def validate(path, catalog):
    doc = json.loads(path.read_text(encoding="utf-8"))
    known = set()
    if catalog.is_file():
        cat = json.loads(catalog.read_text(encoding="utf-8"))
        known = {s["mona_setName"] for s in cat.get("sets", []) if s.get("mona_setName")}
    bad = set(); n = 0
    for slot in ("flower","feather","sand","cup","head"):
        for piece in doc.get(slot, []):
            n += 1
            sn = piece.get("setName","")
            if sn and sn not in known: bad.add(sn)
    return {"ok": not bad, "piece_count": n, "unknown_sets": sorted(bad)}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("input", nargs="?")
    p.add_argument("-o","--output")
    p.add_argument("-d","--dir")
    p.add_argument("--min-star", type=int, default=1)
    p.add_argument("--validate-only", action="store_true")
    a = p.parse_args()
    cat = Path(r"d:\控分中枢\resources\artifact_set_catalog.json")
    if a.validate_only:
        t = Path(a.input or a.output or "")
        r = validate(t, cat); print(r); return 0 if r["ok"] else 1
    gtm = load("good_to_mona")
    if a.input: good = Path(a.input)
    elif a.dir:
        good = gtm.find_latest_good_export(Path(a.dir))
        if not good: print("no export", file=sys.stderr); return 2
    else: p.error("need input")
    out = Path(a.output) if a.output else good.parent / "mona.json"
    info = gtm.convert_file(good, out, min_star=a.min_star)
    r = validate(out, cat)
    print("Wrote", info["piece_count"], "->", out, r)
    return 0 if r["ok"] else 1

if __name__ == "__main__":
    raise SystemExit(main())