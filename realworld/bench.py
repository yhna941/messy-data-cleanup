#!/usr/bin/env python3
"""Benchmark clean_pipeline.py on the real-world sets: wall time, peak memory, per-stage timings.

usage: bench.py [--data DIR] [--out results.json] [--mem-cap-mb 2800] [--timeout 1800] NAME:SUBDIR [...]

Each run is a fresh subprocess (so peak RSS is that run's alone), capped by RLIMIT_AS so a run that
would not fit fails with MemoryError instead of taking the machine down. Stage timings come from
clean_pipeline.py --perf. Data lives outside git (see scripts/fetch_realworld.sh).
"""
import argparse
import json
import os
import resource
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PIPE = Path(os.environ.get("RW_PIPE", HERE.parent / "skill/messy-data-cleanup/scripts/clean_pipeline.py"))


def rows_in(summary: Path) -> int:
    try:
        s = json.loads(summary.read_text())
        return sum(t["rows_in"] for t in s["tables"].values())
    except (OSError, KeyError, ValueError):
        return 0


def run_one(name: str, sub: str, data: Path, out_root: Path, cap_mb: int, timeout: int, extra: list[str]) -> dict:
    inp, out = data / name / sub, out_root / name / sub
    out.mkdir(parents=True, exist_ok=True)
    perf = out / "perf.json"
    perf.unlink(missing_ok=True)

    def limit():
        if cap_mb:
            resource.setrlimit(resource.RLIMIT_AS, (cap_mb * 2 ** 20, cap_mb * 2 ** 20))
    cmd = [sys.executable, str(PIPE), "--contract", str(HERE / name / "contract.yaml"), "--input-dir", str(inp),
           "--out", str(out), "--name", name, "--perf", str(perf)] + extra
    t0 = time.perf_counter()
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, preexec_fn=limit, env={**os.environ, "PYTHONHASHSEED": "1"})
    try:
        log, _ = p.communicate(timeout=timeout)
        status = "ok" if p.returncode == 0 else f"exit {p.returncode}"
    except subprocess.TimeoutExpired:
        p.kill()
        log, _ = p.communicate()
        status = "timeout"
    wall = time.perf_counter() - t0
    text = log.decode("utf-8", "replace")
    if "MemoryError" in text:
        status = "MemoryError"
    (out / "log.txt").write_text(text)
    stages = json.loads(perf.read_text()) if perf.exists() else []
    n = rows_in(out / "run_summary.json")
    agg: dict[str, float] = {}
    for s in stages:
        agg[s["stage"]] = round(agg.get(s["stage"], 0) + s["sec"], 3)
    return {"dataset": name, "subset": sub, "status": status, "rows": n, "wall_s": round(wall, 2),
            "rows_per_s": round(n / wall) if n and wall else None, "peak_rss_mb": max((s["peak_mb"] for s in stages), default=None),
            "stages": agg, "tail": text.strip().splitlines()[-3:]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--data", type=Path, default=Path(os.environ.get("RW_DATA", HERE.parent / "data/rw")))
    ap.add_argument("--out", type=Path, default=HERE / "results" / "bench.json")
    ap.add_argument("--out-root", type=Path, default=Path(os.environ.get("RW_OUT", HERE / "out")))
    ap.add_argument("--mem-cap-mb", type=int, default=2800)
    ap.add_argument("--timeout", type=int, default=1800)
    ap.add_argument("--label", default="")
    a, extra = ap.parse_known_args()
    res = []
    if a.out.exists():
        res = json.loads(a.out.read_text())
    for spec in a.runs:
        name, _, sub = spec.partition(":")
        r = run_one(name, sub or "full", a.data, a.out_root, a.mem_cap_mb, a.timeout, extra)
        r["label"] = a.label
        print(json.dumps({k: r[k] for k in ("dataset", "subset", "status", "rows", "wall_s", "rows_per_s", "peak_rss_mb", "stages")}, ensure_ascii=False), flush=True)
        res = [x for x in res if not (x["dataset"] == r["dataset"] and x["subset"] == r["subset"] and x.get("label") == r["label"])] + [r]
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(res, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
