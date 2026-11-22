#!/usr/bin/env python3
"""Idempotency, second sense: cleaning the cleaned CSVs again must change no value.

Builds a contract from contract.yaml whose sources are output/csv/<table>.csv (aliases = the
cleaned column names), reruns the pipeline into a temp dir, and counts value-changing log lines
(representation-only steps such as '12000' text -> 12000 number are not counted).
"""
from __future__ import annotations

import datetime as dt
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
SK = HERE.parent / "skill" / "messy-data-cleanup" / "scripts" / "clean_pipeline.py"


def canon(v):
    if v is None or v == "":
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).replace("T", " ") if re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d(:\d\d)?", str(v)) else str(v)   # ISO vs str(datetime)


def main(base: Path) -> int:
    c = yaml.safe_load((base / "contract.yaml").read_text(encoding="utf-8"))
    for name, t in c["tables"].items():
        t.update({"file": f"{name}.csv", "sheet": "", "block": 1})
        for col, spec in t["columns"].items():
            spec["aliases"] = [col]
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "fp.yaml"
        p.write_text(yaml.safe_dump(c, allow_unicode=True, sort_keys=False), encoding="utf-8")
        subprocess.run([sys.executable, str(SK), "--contract", str(p), "--input-dir", str(base / "output" / "csv"),
                        "--out", str(Path(tmp) / "out"), "--name", "fp"], check=False, capture_output=True)
        audit = json.loads((Path(tmp) / "out" / "audit.json").read_text(encoding="utf-8"))
    real = [ch for ch in audit["changes"] if canon(ch["before"]) != canon(ch["after"])]
    drops = [d for d in audit["dropped"] if d["kind"] not in ("header",)]
    rows = sum(1 for _ in audit["changes"])
    print(f"fixed-point check: {len(real)} value changes, {len(drops)} rows dropped on the second pass "
          f"({rows} representation-only log lines such as '12000' -> 12000; {len(audit['review'])} review items carried over)")
    for ch in real[:10]:
        print("  ", ch["table"], ch["source_row"], ch["column"], repr(ch["before"]), "->", repr(ch["after"]), ch["rule"])
    for d in drops[:10]:
        print("  dropped", d["table"], d["source_row"], d["kind"], d["evidence"])
    return 0 if not real and not drops else 1


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else HERE))
