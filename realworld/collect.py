#!/usr/bin/env python3
"""Run audit.py over the real-world outputs and keep the slim results in realworld/results/audits.json.

usage: collect.py LABEL=OUT_ROOT [...]     e.g. before=/data/out_before final=realworld/out
Each OUT_ROOT holds <set>/<subset>/ output folders (what bench.py --out-root writes). The report
(demo/make_report.py) reads only the JSON files in realworld/results/, never the big outputs.
"""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KEEP = ("rows_out", "changes", "changes_by_rule", "review", "review_per_1k_rows", "review_patterns", "top_review_patterns",
        "dup_groups", "silent_damage", "damage_examples", "self_check_failed", "dropped_by_kind", "verdicts", "wrong_rate",
        "debatable_rate", "mappings")


def main() -> int:
    dest = HERE / "results" / "audits.json"
    res = json.loads(dest.read_text()) if dest.exists() else {}
    for spec in sys.argv[1:]:
        label, _, root = spec.partition("=")
        for out in sorted(Path(root).glob("*/*/audit.json")):
            d = out.parent
            name = f"{d.parent.name}:{d.name}"
            tmp = Path("/tmp") / f"audit_{label}_{d.parent.name}_{d.name}.json"
            subprocess.run([sys.executable, str(HERE / "audit.py"), str(d), "--json", str(tmp)], check=True, capture_output=True)
            a = json.loads(tmp.read_text())
            a["mappings"] = a["mappings"][:40]
            res.setdefault(label, {})[name] = {k: a[k] for k in KEEP if k in a}
            print(label, name, a["verdicts"], a["silent_damage"])
    dest.write_text(json.dumps(res, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
