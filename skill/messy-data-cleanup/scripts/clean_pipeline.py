#!/usr/bin/env python3
"""Clean messy xlsx/csv files against a YAML contract and write a full audit workbook.

usage: clean_pipeline.py --contract contract.yaml [--input-dir DIR] [--out DIR] [--name NAME]
                         [--llm off|cache|live] [--llm-provider auto|openrouter|gemini] [--llm-model M] [--llm-cache DIR]

LLM layer (optional): off = rules only (default). live = answers come from the cache, else the
provider (OPENROUTER_API_KEY or GEMINI_API_KEY), and are cached by input hash. cache = replay the
cache only, never call (reproduce a past run offline). Env CLEANKIT_LLM sets the default mode.

Re-runnable: reads the originals (never writes them), replaces only its own outputs,
and produces byte-identical files for identical inputs.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cleankit.contract import load  # noqa: E402
from cleankit.llm import LLM  # noqa: E402
from cleankit.pipeline import Run  # noqa: E402
from cleankit import write as W  # noqa: E402
from cleankit.write import write_all  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--contract", required=True, type=Path)
    ap.add_argument("--input-dir", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--name")
    ap.add_argument("--llm", choices=["off", "cache", "live"], default=os.environ.get("CLEANKIT_LLM", "off"))
    ap.add_argument("--llm-provider", default="auto", choices=["auto", "openrouter", "gemini"])
    ap.add_argument("--llm-model")
    ap.add_argument("--llm-cache", type=Path)
    ap.add_argument("--xlsx-rows", type=int, default=W.XLSX_ROWS,
                    help="rows per sheet in the workbook (default %(default)s); longer tables are previews there and complete in csv/")
    ap.add_argument("--perf", type=Path, help="write per-stage wall time and memory (JSON) here; not part of the audit outputs")
    a = ap.parse_args()
    W.XLSX_ROWS = max(1, a.xlsx_rows)
    contract = load(a.contract)
    input_dir = a.input_dir or a.contract.parent
    out = a.out or input_dir / "cleaned"
    llm = LLM(a.llm, a.llm_provider, a.llm_model, a.llm_cache or contract.base / contract.llm["cache_dir"])
    if a.llm != "off" and not llm.on:
        print("llm: no OPENROUTER_API_KEY / GEMINI_API_KEY found, running rules only")
    run = Run(contract, input_dir, llm)
    run.self_checks = run.run()["self_check"]
    name = a.name or a.contract.stem.replace(".contract", "")
    with run.timed("write"):
        s = write_all(run, out, name)
    if a.perf:
        a.perf.write_text(json.dumps(run.perf, indent=1), encoding="utf-8")
    u = llm.usage
    if llm.on:   # usage differs between a live run and a cached rerun, so it stays out of the audit files
        (out / "llm_usage.json").write_text(json.dumps({"llm": llm.label, "mode": llm.mode, "calls": u.calls, "cache_hits": u.cache_hits,
                                                         "prompt_tokens": u.prompt_tokens, "completion_tokens": u.completion_tokens,
                                                         "cost_usd": round(u.cost_usd, 6), "errors": u.errors}, indent=1), encoding="utf-8")
        print(f"llm {llm.label} ({llm.mode}): {s['n_llm_changes']} decisions applied; calls {u.calls}, cache hits {u.cache_hits}, "
              f"tokens {u.prompt_tokens}+{u.completion_tokens}, cost ${u.cost_usd:.4f}" + (f", errors {len(u.errors)}: {u.errors[:2]}" if u.errors else ""))
    for t, st in s["tables"].items():
        print(f"{t}: {st['rows_in']} rows in -> {st['rows_out']} cleaned, dropped {st['dropped']}")
    print(f"changes {s['n_changes']}, review items {s['n_review']}, duplicate groups {s['n_dup_groups']}")
    for j in s["joins"]:
        print(f"join {j['join']} {j['left']}->{j['right']}: {j['match_rate']:.1%} (raw keys {j['raw_key_match_rate']:.1%}"
              + (f", rules only {j['rules_only_match_rate']:.1%}, llm {j['matched_llm']}" if j['matched_llm'] else "") + f"), orphans {j['orphans']}, ambiguous {j['ambiguous']}")
    failed = [c for c in s["self_check"] if not c["ok"]]
    for c in s["self_check"]:
        print(("PASS " if c["ok"] else "FAIL ") + c["check"] + f" ({c['detail']})")
    print(f"wrote {out}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
