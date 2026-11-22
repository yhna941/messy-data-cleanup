#!/usr/bin/env python3
"""Score the cleaned workbook against ground_truth.json. Reads the real output xlsx, not internals.

Outcome per planted issue:
  fixed    value equals the truth (or the row/drop/join outcome happened)
  flagged  left for a human with a review item at that cell (safe, counted separately)
  guessed  a flag-only issue silently set to the truth: right by luck, counted as NOT handled
  wrong    changed to a value that is not the truth, with no flag (the dangerous case)
  missed   left unchanged and not flagged
  llm_fixed  set to the truth by an LLM decision (rule llm:*) that passed the gates: handled, no human needed
Traps (issue.trap): the LLM must leave these to a human; any LLM-applied change there is `wrong`.
Also audits every llm:* change against the truth: the LLM wrong-change rate.
"""
from __future__ import annotations

import ast
import datetime as dt
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import openpyxl

HERE = Path(__file__).resolve().parent


def norm(v):
    if v is None or v == "":
        return None
    if isinstance(v, dt.datetime):
        return v.date().isoformat()
    if isinstance(v, dt.date):
        return v.isoformat()
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    return v


def table(ws):
    rows = list(ws.iter_rows(values_only=True))
    hdr = rows[0]
    return [dict(zip(hdr, r)) for r in rows[1:] if any(x is not None for x in r)]


def main(out_xlsx: Path, gt_path: Path | None = None) -> dict:
    gt_path = gt_path or HERE / "ground_truth.json"
    gt = json.loads(gt_path.read_text(encoding="utf-8"))
    wb = openpyxl.load_workbook(out_xlsx)
    cleaned = {}
    for t in gt["tables"]:
        cleaned[t] = {int(r["_source"].split("!")[1]): r for r in table(wb[f"Cleaned_{t}"[:31]])}
    review = defaultdict(set)
    for r in table(wb["Needs human review"]):
        review[(r["table"], r["row"])].add(r["column"])
    dropped = {(r["table"], r["row"]): r["kind"] for r in table(wb["Dropped rows"])}
    clog = table(wb["Change log"])
    changed = {(r["table"], r["row"], r["column"]) for r in clog}
    llm_cells = defaultdict(list)
    for r in clog:
        if str(r["rule"]).startswith("llm:"):
            llm_cells[(r["table"], r["row"], r["column"])].append(r)
    groups = table(wb["Suspected duplicates"])
    recon = table(wb["Reconcile"])
    jr_rows = list(wb["Join report"].iter_rows(values_only=True))
    split = next((i for i, r in enumerate(jr_rows) if r and r[0] == "join" and r[1] == "step"), len(jr_rows) - 1)
    jdet = [dict(zip(jr_rows[split], r)) for r in jr_rows[split + 1:] if r and r[0]]
    jsheet = gt.get("meta", {}).get("joined_sheet", "Joined_orders_full")
    joined = {int(r["_source"].split("!")[1]): r for r in table(wb[jsheet])} if jsheet in wb.sheetnames else {}

    jprefix = gt.get("meta", {}).get("join_prefix", "cust_")
    res = []
    for iss in gt["issues"]:
        t, row, col, exp, truth = iss["table"], iss["row"], iss["column"], iss["expect"], iss["truth"]
        flagged = col in review.get((t, row), set()) or (col is None and (t, row) in review)
        out = "missed"
        if exp in ("fix", "flag", "keep"):
            rec = cleaned[t].get(row)
            val = norm(rec.get(col)) if rec else "<row missing>"
            if val == norm(truth):
                out = "fixed"
            elif flagged:
                out = "flagged"
            elif (t, row, col) in changed:
                out = "wrong"
            by_llm = bool(llm_cells.get((t, row, col)))
            if exp == "flag":   # a human had to decide: an unflagged value, even a lucky one, is a guess
                if iss.get("trap") and by_llm:
                    out = "wrong"
                elif out == "fixed" and by_llm and not flagged:
                    out = "llm_fixed"
                else:
                    out = "flagged" if flagged else ("guessed" if out == "fixed" else out)
            elif out == "fixed" and by_llm:
                out = "llm_fixed"
        elif exp == "extract":
            rec = cleaned[t].get(row) or {}
            val, tv = norm(rec.get(col)), norm(truth)
            if val == tv:
                out = "llm_fixed" if tv is not None else "fixed"
            elif val is None:
                out = "flagged" if flagged else "missed"
            else:
                out = "wrong"
        elif exp == "entity":
            j = joined.get(row, {})
            status = str(next((v for k, v in j.items() if k.startswith("_join_" + jprefix.rstrip("_"))), ""))
            got = j.get(col)
            matched = status.startswith("matched")
            if truth is None:
                out = "wrong" if matched else "fixed"
            elif matched:
                out = ("llm_fixed" if "llm" in status else "fixed") if got == truth else "wrong"
            else:
                out = "flagged" if (t, row) in review else "missed"
        elif exp == "drop":
            out = "fixed" if dropped.get((t, row)) not in (None, "duplicate") else "missed"
        elif exp == "dup_drop":
            out = "fixed" if dropped.get((t, row)) == "duplicate" else "missed"
        elif exp == "reconcile":
            hit = [r for r in recon if r["table"] == t and r["subtotal_row"] == row and r["column"] == col]
            out = "fixed" if hit and hit[0]["explanation"] in ("matches", "difference = dropped duplicate rows") else "flagged" if hit else "missed"
            iss["got"] = hit[0]["explanation"] if hit else None
        elif exp == "conflict":
            out = "flagged" if any(g["kind"] == "key_conflict" and str(row) in str(g["rows"]).split(", ") for g in groups) else "missed"
        elif exp == "suspect":
            out = "flagged" if any(g["kind"] == "suspected" and set(map(str, truth)) <= set(str(g["rows"]).split(", ")) for g in groups) else "missed"
        elif exp == "no_suspect":
            bad = any(g["kind"] == "suspected" and set(map(str, truth)) <= set(str(g["rows"]).split(", ")) for g in groups)
            out = "wrong" if bad else "fixed"
        elif exp == "orphan":
            out = "flagged" if any(d["issue"] == "J2-ORPHAN" and d["left row"] == row and d["key"] == truth for d in jdet) else "missed"
        elif exp == "ambiguous":
            out = "flagged" if any(d["issue"] == "J3-AMBIG" and d["left row"] == row for d in jdet) else "missed"
        elif exp == "join_fallback":
            j = joined.get(row, {})
            out = "fixed" if "fallback" in str(j.get("_join_prod")) and j.get("prod_product_code") == truth else "missed"
        elif exp == "join_in_other":
            out = "fixed" if "discontinued" in str(joined.get(row, {}).get("_join_prod")) else "missed"
        elif exp == "found":
            out = "fixed" if len(cleaned[t]) == len(gt["tables"][t]) else "missed"
        elif exp == "encoding":
            ok = all(norm(cleaned[t].get(int(r), {}).get("reason")) == v["reason"] for r, v in gt["tables"][t].items())
            out = "fixed" if ok else "missed"
        iss["outcome"] = out
        res.append(iss)

    # whole-table cell accuracy (every truth cell, not just planted ones)
    cells = Counter()
    wrong_cells = []
    flag_only = {(i["table"], i["row"], i["column"]) for i in gt["issues"] if i["expect"] == "flag"}
    for t, rows in gt["tables"].items():
        for r, rec in rows.items():
            got = cleaned[t].get(int(r))
            for c, tv in rec.items():
                cells["total"] += 1
                ok = got is not None and norm(got.get(c)) == norm(tv)
                cells["ok"] += ok
                if not ok:
                    key = (t, int(r), c)
                    cells["flag_only_wrong" if key in flag_only else "other_wrong"] += 1
                    if key not in flag_only:
                        wrong_cells.append({"table": t, "row": int(r), "column": c, "truth": tv, "got": None if got is None else str(got.get(c))})
    extra_rows = {t: sorted(set(cleaned[t]) - {int(r) for r in gt["tables"][t]}) for t in gt["tables"]}
    planted_cells = {(i["table"], i["row"], i["column"]) for i in gt["issues"]}
    planted_cells |= {(i["table"], r, None) for i in gt["issues"] if i["expect"] == "suspect" for r in i["truth"]}
    planted_cells |= {(i["table"], i["row"], None) for i in gt["issues"] if i["expect"] == "entity"}
    noise = []
    for (t, row), cols in review.items():
        for c in cols:
            row_level = (t, row, None) in planted_cells and (c == "(row)" or str(c).endswith("_id"))
            if (t, row, c) not in planted_cells and not row_level:
                noise.append({"table": t, "row": row, "column": c})

    # every LLM-applied change, checked against the truth where the truth is known
    entity_truth = {i["row"]: i["truth"] for i in gt["issues"] if i["expect"] == "entity"}
    llm_audit = Counter()
    llm_wrong = []
    for (t, row, col), rows_ in llm_cells.items():
        for r in rows_:
            after = r["after"]
            if isinstance(after, str) and after[:1] in "'\"":
                after = ast.literal_eval(after)
            if r["rule"] == "llm:entity":
                tv = entity_truth.get(row, "<unknown>")
            else:
                tv = gt["tables"].get(t, {}).get(str(row), {}).get(col, "<unknown>")
            if tv == "<unknown>":
                llm_audit["unverifiable"] += 1
            elif norm(after) == norm(tv):
                llm_audit["right"] += 1
            else:
                llm_audit["wrong"] += 1
                llm_wrong.append({"table": t, "row": row, "column": col, "rule": r["rule"], "after": after, "truth": tv, "evidence": r["evidence"]})
    n_llm = sum(llm_audit.values())

    by_cat = defaultdict(Counter)
    for i in res:
        by_cat[i["category"]][i["outcome"]] += 1
    tot = Counter(i["outcome"] for i in res)
    by_expect = defaultdict(Counter)
    for i in res:
        by_expect[i["expect"]][i["outcome"]] += 1
    score = {
        "planted": len(res), "outcomes": dict(tot), "by_category": {k: dict(v) for k, v in sorted(by_cat.items())},
        "by_expect": {k: dict(v) for k, v in by_expect.items()},
        "handled": tot["fixed"] + tot["llm_fixed"] + tot["flagged"],
        "handled_rate": round((tot["fixed"] + tot["llm_fixed"] + tot["flagged"]) / len(res), 4),
        "auto_resolved_rate": round((tot["fixed"] + tot["llm_fixed"]) / len(res), 4),
        "review_queue": sum(1 for _ in table(wb["Needs human review"])),
        "llm_changes": {"total": n_llm, **dict(llm_audit),
                        "wrong_rate": round(llm_audit["wrong"] / (llm_audit["right"] + llm_audit["wrong"]), 4) if llm_audit["right"] + llm_audit["wrong"] else None},
        "llm_wrong": llm_wrong,
        "joins": [{k: r.get(k) for k in ("join", "match_rate", "raw_key_match_rate", "rules_only_match_rate", "matched_llm")} for r in
                  (dict(zip(jr_rows[0], x)) for x in jr_rows[1:split]) if r.get("join")],
        "cell_accuracy": {"cells": cells["total"], "correct": cells["ok"], "rate": round(cells["ok"] / cells["total"], 4),
                          "wrong_but_flag_expected": cells["flag_only_wrong"], "wrong_other": cells["other_wrong"]},
        "wrong_cells": wrong_cells, "extra_rows_in_cleaned": extra_rows,
        "noise_flags": noise, "not_handled": [i for i in res if i["outcome"] in ("missed", "wrong", "guessed")],
    }
    (out_xlsx.parent / "score.json").write_text(json.dumps(score, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return score


if __name__ == "__main__":
    s = main(Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "output" / "haru-cleaned.xlsx",
             Path(sys.argv[2]) if len(sys.argv) > 2 else None)
    print(json.dumps({k: s[k] for k in ("planted", "outcomes", "handled_rate", "auto_resolved_rate", "review_queue", "cell_accuracy", "llm_changes")}, ensure_ascii=False))
    print("JOINS:", s["joins"])
    for w in s["llm_wrong"]:
        print("  LLM WRONG:", w)
    for k, v in s["by_category"].items():
        print(f"  {k:20s} {v}")
    print("NOT HANDLED:")
    for i in s["not_handled"]:
        print("  ", i["id"], i["table"], i["row"], i["column"], i["category"], i["expect"], "truth=", i["truth"], i["note"], "->", i["outcome"])
    print("WRONG CELLS (non-flag):", len(s["wrong_cells"]))
    for w in s["wrong_cells"][:40]:
        print("  ", w)
    print("NOISE FLAGS:", s["noise_flags"])
    print("EXTRA ROWS:", s["extra_rows_in_cleaned"])
