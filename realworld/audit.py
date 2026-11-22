#!/usr/bin/env python3
"""Quality audit of one cleaned real-world output (no ground truth): silent-damage scan + change sample.

usage: audit.py OUT_DIR [--sample 60] [--seed 7] [--json out.json]

Silent damage = a change that loses information without asking: leading zeros dropped, a long
digit code turned into a float/scientific notation, a time of day dropped, a non-blank value blanked
by something other than a placeholder rule, a code column reformatted. Scans every Change in audit.json.
The change sample is stratified by rule (seeded) for reading by hand / an LLM judge (judge.py).
"""
import argparse
import collections
import json
import random
import re
from pathlib import Path

LZ = re.compile(r"^0\d+$")
TIME = re.compile(r"\d{1,2}:\d{2}")


def damage(c: dict) -> str | None:
    b, a, rule = c["before"], c["after"], c["rule"]
    bs, as_ = ("" if b is None else str(b)), ("" if a is None else str(a))
    if isinstance(b, str) and LZ.match(b.strip()) and as_.lstrip("0") == b.strip().lstrip("0") and as_ != b.strip():
        return "leading zero lost"
    if isinstance(b, str) and re.fullmatch(r"\d{12,}", b.strip()) and ("e+" in as_.lower() or isinstance(a, float)):
        return "long digit code became a float"
    if "e+" in as_.lower() and "e+" not in bs.lower() and re.fullmatch(r"[\d.]+e\+\d+", as_.lower()):
        return "scientific notation introduced"
    if TIME.search(bs) and not TIME.search(as_) and rule.startswith("D"):
        return "time of day dropped"
    if bs.strip() and not as_.strip() and rule not in ("M1-PLACEHOLDER", "S3-SHIFT"):
        return "value blanked"
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--sample", type=int, default=60)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--json", type=Path)
    a = ap.parse_args()
    audit = json.loads((a.out / "audit.json").read_text())
    summ = json.loads((a.out / "run_summary.json").read_text())
    rows = sum(t["rows_out"] for t in summ["tables"].values())
    ch = audit["changes"]
    dmg = collections.Counter()
    examples = collections.defaultdict(list)
    for c in ch:
        d = damage(c)
        if d:
            dmg[d] += 1
            if len(examples[d]) < 5:
                examples[d].append({k: c[k] for k in ("table", "source_row", "column", "before", "after", "rule")})
    by_rule = collections.defaultdict(list)
    for c in ch:
        if c["rule"] not in ("S2-MERGE",):    # merge fills are structural copies, checked by the self-check
            by_rule[c["rule"]].append(c)
    rnd = random.Random(a.seed)
    per = max(1, a.sample // max(1, len(by_rule)))
    sample = []
    for rule in sorted(by_rule):
        for c in rnd.sample(by_rule[rule], min(per, len(by_rule[rule]))):
            sample.append({k: c[k] for k in ("table", "source_row", "column", "before", "after", "rule", "evidence")})
    pat = collections.Counter((r["table"], r["column"], r["flag"]) for r in audit["review"])
    vals = collections.Counter((r["column"], r["flag"], str(r["value"])[:40]) for r in audit["review"])
    res = {"out": str(a.out), "rows_out": rows, "changes": len(ch), "changes_by_rule": summ["changes_by_rule"],
           "review": len(audit["review"]), "review_per_1k_rows": round(1000 * len(audit["review"]) / max(rows, 1), 1),
           "review_patterns": len(pat), "review_distinct_values": len(vals),
           "top_review_patterns": [[*k, n] for k, n in pat.most_common(8)],
           "top_review_values": [[*k, n] for k, n in vals.most_common(8)],
           "dup_groups": len(audit["dups"]), "silent_damage": dict(dmg), "damage_examples": examples,
           "self_check_failed": [c["check"] for c in summ["self_check"] if not c["ok"]],
           "dropped_by_kind": dict(collections.Counter(d["kind"] for d in audit["dropped"])),
           "sample": sample}
    txt = json.dumps(res, ensure_ascii=False, indent=1, default=str)
    if a.json:
        a.json.write_text(txt)
    print(json.dumps({k: v for k, v in res.items() if k not in ("sample", "damage_examples")}, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
