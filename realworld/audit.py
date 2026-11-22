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
MIDNIGHT = re.compile(r"(?<!\d)0?0:00(:00(\.0+)?)?(?!\d)")  # exactly midnight carries no time (date-only value)


def damage(c: dict) -> str | None:
    b, a, rule = c["before"], c["after"], c["rule"]
    bs, as_ = ("" if b is None else str(b)), ("" if a is None else str(a))
    if isinstance(b, str) and LZ.match(b.strip()) and as_.lstrip("0") == b.strip().lstrip("0") and as_ != b.strip():
        return "leading zero lost"
    if isinstance(b, str) and re.fullmatch(r"\d{12,}", b.strip()) and ("e+" in as_.lower() or isinstance(a, float)):
        return "long digit code became a float"
    if "e+" in as_.lower() and "e+" not in bs.lower() and re.fullmatch(r"[\d.]+e\+\d+", as_.lower()):
        return "scientific notation introduced"
    if rule == "N1-NUMBER" and isinstance(a, float) and num(b) is not None and num(b) != a and abs(num(b) - a) <= 1e-6 * max(1.0, abs(a)):
        return "number rounded (digits dropped)"
    if TIME.search(bs) and not MIDNIGHT.search(bs) and not TIME.search(as_) and rule.startswith("D"):
        return "time of day dropped"
    if bs.strip() and not as_.strip() and rule not in ("M1-PLACEHOLDER", "S3-SHIFT"):
        return "value blanked"
    return None


PLACEHOLDERS = {"-", "--", "—", "n/a", "na", "#n/a", "null", "none", "nan", "?", "없음", "미입력", "해당없음", "x", "#value!", "#ref!", "#div/0!"}


def num(x):
    try:
        return float(str(x).replace(",", "").strip())
    except ValueError:
        return None


def mechanical(c: dict) -> bool:
    """True when the change is provably value-preserving (checked from before/after alone)."""
    b, a, rule = c["before"], c["after"], c["rule"]
    if rule == "N1-NUMBER":
        return num(b) is not None and num(b) == num(a)
    if rule == "D1-DATE":       # same calendar digits, same time if one was given
        db, da = re.findall(r"\d+", str(b)), re.findall(r"\d+", str(a))
        return len(da) >= 3 and [int(x) for x in da] == [int(x) for x in db[:len(da)]] and all(int(x) == 0 for x in db[len(da):])
    if rule == "T1-WS":
        return isinstance(b, str) and " ".join(b.split()) == a
    if rule == "I1-ID":         # a number read from Excel written back as its text (ZIP 10314 -> '10314')
        return not isinstance(b, str) and str(b) == a
    if rule == "M1-PLACEHOLDER":
        return a is None and str(b).strip().casefold() in PLACEHOLDERS
    return False


def key(c: dict) -> str:
    return f"{c['rule']}|{c['column']}|{c['before']!r}|{c['after']!r}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--sample", type=int, default=60)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--json", type=Path)
    ap.add_argument("--judgments", type=Path, default=Path(__file__).parent / "judgments.json",
                    help="hand labels: list of {rule, column?, before?, after? (regexes), verdict: ok|wrong|debatable, why}")
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
        by_rule[c["rule"]].append(c)
    rnd = random.Random(a.seed)
    per = max(1, a.sample // max(1, len(by_rule)))
    sample = []
    for rule in sorted(by_rule):
        for c in rnd.sample(by_rule[rule], min(per, len(by_rule[rule]))):
            sample.append({k: c[k] for k in ("table", "source_row", "column", "before", "after", "rule", "evidence")})
    # every change is either mechanically verified or belongs to a distinct mapping that gets a label
    labels = json.loads(a.judgments.read_text()) if a.judgments and a.judgments.exists() else []

    def label(c: dict) -> str:
        for j in labels:
            if j["rule"] == c["rule"] and re.fullmatch(j.get("column", ".*"), str(c["column"])) \
                    and re.search(j.get("before", ""), repr(c["before"])) and re.search(j.get("after", ""), repr(c["after"])):
                return j["verdict"]
        return "unlabelled"
    first: dict[str, dict] = {}
    mech, damaged, classes = 0, 0, collections.Counter()
    for c in ch:
        if damage(c):
            damaged += 1          # silent damage is a wrong change whatever the rule
        elif mechanical(c):
            mech += 1
        else:
            classes[key(c)] += 1
            first.setdefault(key(c), c)
    verdict = collections.Counter()
    judg = {k: label(first[k]) for k in classes}
    for k, n in classes.items():
        verdict[judg[k]] += n
    verdict["mechanical"] = mech
    verdict["wrong"] += damaged
    judged = sum(n for v, n in verdict.items() if v in ("ok", "wrong", "debatable", "mechanical"))
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
           "verdicts": dict(verdict), "wrong_rate": round(verdict["wrong"] / judged, 5) if judged else None,
           "debatable_rate": round(verdict["debatable"] / judged, 5) if judged else None,
           "mappings": [[k, n, judg[k]] for k, n in classes.most_common()],
           "sample": sample}
    txt = json.dumps(res, ensure_ascii=False, indent=1, default=str)
    if a.json:
        a.json.write_text(txt)
    print(json.dumps({k: v for k, v in res.items() if k not in ("sample", "damage_examples", "mappings")}, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
