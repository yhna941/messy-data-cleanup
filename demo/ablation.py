#!/usr/bin/env python3
"""Ablation: rules-only vs rules+LLM on the demo, blind and semantic sets, same scorer.

Also proves the LLM run is reproducible: run 2 (cache) and an offline `--llm cache` replay must be
byte-identical to run 1. Writes ../ablation.json. Env: ABL_LLM=live|cache (default live: cache first,
the provider only on a miss), ABL_PROVIDER (default openrouter), ABL_MODEL.
"""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SK = ROOT / "skill" / "messy-data-cleanup" / "scripts"
sys.path.insert(0, str(HERE))
import score  # noqa: E402

SETS = [("demo", "haru"), ("blind", "blind"), ("semantic", "shop"), ("semantic_blind", "bakery")]
MODE = os.environ.get("ABL_LLM", "live")
PROV = os.environ.get("ABL_PROVIDER", "openrouter")
MODEL = os.environ.get("ABL_MODEL")


def clean(d: Path, name: str, out: str, llm: str) -> dict:
    cmd = [sys.executable, str(SK / "clean_pipeline.py"), "--contract", "contract.yaml", "--input-dir", "input", "--out", out, "--name", name,
           "--llm", llm, "--llm-provider", PROV] + (["--llm-model", MODEL] if MODEL else [])
    p = subprocess.run(cmd, cwd=d, capture_output=True, text=True, timeout=900)
    if p.returncode:
        raise SystemExit(f"{d.name}: pipeline failed\n{p.stdout}\n{p.stderr}")
    u = d / out / "llm_usage.json"
    return json.loads(u.read_text()) if u.exists() else {}


def digest(d: Path) -> str:
    h = hashlib.sha256()
    for f in sorted([*d.glob("*-cleaned.xlsx"), d / "run_summary.json", d / "audit.json", *sorted((d / "csv").glob("*.csv"))]):
        h.update(f.name.encode() + f.read_bytes())
    return h.hexdigest()[:16]


def pick(s: dict) -> dict:
    o = s["outcomes"]
    return {"planted": s["planted"], "fixed_by_rules": o.get("fixed", 0), "fixed_by_llm": o.get("llm_fixed", 0),
            "flagged": o.get("flagged", 0), "wrong": o.get("wrong", 0), "missed": o.get("missed", 0), "guessed": o.get("guessed", 0),
            "handled_rate": s["handled_rate"], "auto_resolved_rate": s["auto_resolved_rate"], "review_queue": s["review_queue"],
            "cell_accuracy": s["cell_accuracy"]["rate"], "llm_changes": s["llm_changes"], "llm_wrong": s["llm_wrong"],
            "join_rates": [j["match_rate"] for j in s["joins"]]}


def main():
    res = {"llm_mode": MODE, "provider": PROV, "sets": {}}
    total_cost = 0.0
    for dname, name in SETS:
        d = ROOT / dname
        if dname != "demo":
            subprocess.run([sys.executable, next(d.glob("make_*.py")).name], cwd=d, check=True, capture_output=True)
        clean(d, name, "output", "off")
        rules = score.main(d / "output" / f"{name}-cleaned.xlsx", d / "ground_truth.json")
        u1 = clean(d, name, "output_llm", MODE)
        h1 = digest(d / "output_llm")
        llm = score.main(d / "output_llm" / f"{name}-cleaned.xlsx", d / "ground_truth.json")
        u2 = clean(d, name, "output_llm", MODE)
        h2 = digest(d / "output_llm")
        clean(d, name, "output_llm_replay", "cache")
        h3 = digest(d / "output_llm_replay")
        total_cost += u1.get("cost_usd", 0) + u2.get("cost_usd", 0)
        res["sets"][dname] = {"rules_only": pick(rules), "rules_plus_llm": pick(llm), "llm": u1.get("llm"),
                              "usage_run1": {k: u1.get(k) for k in ("calls", "cache_hits", "prompt_tokens", "completion_tokens", "cost_usd", "errors")},
                              "usage_run2": {k: u2.get(k) for k in ("calls", "cache_hits")},
                              "llm_run_identical_on_rerun": h1 == h2, "offline_cache_replay_identical": h1 == h3}
        r, l_ = res["sets"][dname]["rules_only"], res["sets"][dname]["rules_plus_llm"]
        print(f"{dname:9s} rules: handled {r['handled_rate']:.1%} auto {r['auto_resolved_rate']:.1%} wrong {r['wrong']} missed {r['missed']} "
              f"cells {r['cell_accuracy']:.1%} review {r['review_queue']} joins {r['join_rates']}")
        print(f"{'':9s} +llm : handled {l_['handled_rate']:.1%} auto {l_['auto_resolved_rate']:.1%} wrong {l_['wrong']} missed {l_['missed']} "
              f"cells {l_['cell_accuracy']:.1%} review {l_['review_queue']} joins {l_['join_rates']} | llm changes {l_['llm_changes']}")
        print(f"{'':9s} rerun identical: {h1 == h2}, offline replay identical: {h1 == h3}, run2 calls {u2.get('calls')}")
    res["cost_usd_this_run"] = round(total_cost, 6)
    (ROOT / "ablation.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    bad = [k for k, v in res["sets"].items() if not (v["llm_run_identical_on_rerun"] and v["offline_cache_replay_identical"])]
    if bad:
        raise SystemExit(f"NOT REPRODUCIBLE: {bad}")


if __name__ == "__main__":
    main()
