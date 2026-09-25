from pathlib import Path
ROOT = Path(__file__).resolve().parent

def w(rel, text):
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8", newline="\n")

w("convert.py", """#!/usr/bin/env python3
from __future__ import annotations
import argparse, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from irm_to_mona.good_to_mona import convert_file, find_latest_good_export
from irm_to_mona.validate import validate_file

def main(argv=None):
    p = argparse.ArgumentParser(description="Convert Irminsul GOOD to Mona/YAS mona.json")
    p.add_argument("input", nargs="?")
    p.add_argument("-o", "--output")
    p.add_argument("-d", "--dir")
    p.add_argument("--min-star", type=int, default=1, choices=range(1,6), metavar="1-5")
    p.add_argument("--validate-only", action="store_true")
    args = p.parse_args(argv)
    if args.validate_only:
        target = Path(args.input or args.output or "")
        if not target.is_file():
            p.error("--validate-only needs mona.json path")
        rep = validate_file(target)
        _print_validate(rep)
        return 0 if rep["ok"] else 1
    if args.input:
        good_path = Path(args.input)
    elif args.dir:
        good_path = find_latest_good_export(Path(args.dir))
        if good_path is None:
            print("No GOOD export found", file=sys.stderr); return 2
        print("Using:", good_path)
    else:
        p.error("Provide input or --dir")
    if not good_path.is_file():
        print("Missing:", good_path, file=sys.stderr); return 2
    out_path = Path(args.output) if args.output else good_path.parent / "mona.json"
    info = convert_file(good_path, out_path, min_star=args.min_star)
    rep = validate_file(out_path)
    print(f"Wrote {info['piece_count']} pieces -> {out_path}")
    _print_validate(rep)
    return 0 if rep["ok"] else 1

def _print_validate(rep):
    if rep["ok"]:
        print(f"Validation OK ({rep['piece_count']} pieces)"); return
    print("Validation issues:")
    if rep.get("unknown_sets"): print("  unknown setName:", ", ".join(rep["unknown_sets"][:10]))
    if rep.get("unknown_stats"): print("  unknown stats:", ", ".join(rep["unknown_stats"]))
    if rep.get("unknown_equip"): print("  unknown equip:", ", ".join(rep["unknown_equip"][:10]))

if __name__ == "__main__":
    raise SystemExit(main())
""")

print("written convert.py")
