"""Boundary: write the audit workbook, CSV mirrors and run_summary.json deterministically."""
from __future__ import annotations

import csv
import datetime as dt
import json
import os
import re
import zipfile
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .model import RULES
from .pipeline import Run

FIXED = dt.datetime(2000, 1, 1)
HEAD = PatternFill("solid", fgColor="DDEBF7")


def show(v: Any) -> Any:
    if v is None:
        return "(blank)"
    if isinstance(v, str):
        return repr(v)          # quotes make trailing spaces and \u200b visible
    if isinstance(v, dt.datetime) and v.time() == dt.time(0):
        return v.date().isoformat()
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()
    return v


def cell(v: Any) -> Any:
    if isinstance(v, dt.datetime) and v.time() == dt.time(0):
        return v.date()
    return v


def sheet(wb: Workbook, title: str, header: list[str], rows: list[list[Any]], widths: dict[int, int] | None = None):
    ws = wb.create_sheet(title[:31])
    ws.append(header)
    for c in range(1, len(header) + 1):
        ws.cell(1, c).font = Font(bold=True)
        ws.cell(1, c).fill = HEAD
    for r in rows:
        ws.append([cell(v) for v in r])
    for row in ws.iter_rows(min_row=2):
        for x in row:
            if isinstance(x.value, dt.date):
                x.number_format = "yyyy-mm-dd"
            elif isinstance(x.value, str) and len(x.value) > 60:
                x.alignment = Alignment(wrap_text=True, vertical="top")
    for i, h in enumerate(header, start=1):
        w = (widths or {}).get(i) or min(60, max(10, len(str(h)) + 2, *(len(str(r[i - 1])) + 2 for r in rows[:200] if i - 1 < len(r))))
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"
    return ws


def normalize_zip(path: Path) -> None:
    """Rewrite the xlsx zip with fixed timestamps so identical content gives identical bytes."""
    tmp = path.with_suffix(".tmpzip")
    with zipfile.ZipFile(path) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "docProps/core.xml":   # openpyxl stamps 'modified' with the save time
                data = re.sub(rb"(<dcterms:modified[^>]*>)[^<]*", rb"\g<1>2000-01-01T00:00:00Z", data)
            zi = zipfile.ZipInfo(item.filename, date_time=(1980, 1, 1, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o600 << 16
            zout.writestr(zi, data)
    os.replace(tmp, path)


def write_all(run: Run, out_dir: Path, name: str) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    a = run.audit
    wb = Workbook()
    wb.remove(wb.active)
    wb.properties.creator = "messy-data-cleanup"
    wb.properties.created = FIXED
    wb.properties.modified = FIXED

    # ---- summary first so it opens on top
    rule_counts = Counter(c.rule for c in a.changes)
    flag_counts = Counter(r.flag for r in a.review)
    drop_counts = Counter((d.table, d.kind) for d in a.dropped)
    summ_rows: list[list[Any]] = []
    for tname, st in run.stats.items():
        drops = {k: v for (t, k), v in drop_counts.items() if t == tname}
        summ_rows.append(["table", tname, f"rows in {st['rows_in']} -> cleaned {len(run.tables[tname])}; dropped " +
                          ", ".join(f"{k} {v}" for k, v in sorted(drops.items())),
                          f"header row {st['header_row']} ({st['header_depth']}-row); mapped {st['mapped']}" +
                          (f"; unmapped {st['unmapped']}" if st["unmapped"] else "") + (f"; extra columns {st['extras']}" if st["extras"] else "")])
    for rule, n in sorted(rule_counts.items()):
        summ_rows.append(["cell changes", rule, n, RULES[rule][1]])
    for f, n in sorted(flag_counts.items()):
        summ_rows.append(["needs review", f, n, RULES[f][1]])
    for j in a.joins:
        summ_rows.append(["join", f"{j['join']}: {j['left']} -> {j['right']}", f"{j['match_rate']:.1%} matched (raw keys {j['raw_key_match_rate']:.1%})",
                          f"orphans {j['orphans']}, ambiguous {j['ambiguous']}, fallback {j['matched_fallback']}"])
    summ_rows.append(["llm", "mode", run.llm.label, "rules only" if not run.llm.on else
                      f"{sum(1 for c in a.changes if c.rule.startswith('llm:'))} LLM decisions applied (rule llm:*), "
                      f"{sum(1 for r in a.review if 'LLM (' in r.suggestion or r.flag.startswith('llm:'))} LLM proposals left for review"])
    for chk in run.self_checks:
        summ_rows.append(["self-check", chk["check"], "PASS" if chk["ok"] else "FAIL", chk["detail"]])
    for n in a.notes:
        summ_rows.append(["note", "", "", n])
    sheet(wb, "Summary", ["section", "item", "value", "detail"], summ_rows, {1: 14, 2: 46, 3: 40, 4: 90})

    # ---- raw copies (untouched values and merges)
    for file, grids in run.grids.items():
        for g in grids:
            ws = wb.create_sheet(("Raw_" + (g.sheet or Path(g.source).stem))[:31])
            for row in g.cells:
                ws.append([cell(v) for v in row])
            for r1, c1, r2, c2 in g.merges:
                ws.merge_cells(start_row=r1 + 1, start_column=c1 + 1, end_row=r2 + 1, end_column=c2 + 1)
            ws.sheet_properties.tabColor = "BFBFBF"

    # ---- cleaned tables
    csv_dir = out_dir / "csv"
    csv_dir.mkdir(exist_ok=True)
    for tname, recs in run.tables.items():
        t = run.c.tables[tname]
        extras = sorted({k for r in recs for k in r.values if k.startswith("extra:")}) + run.derived.get(tname, [])
        hdr = list(t.columns) + extras + ["_source"]
        rows = [[r.values.get(c) for c in hdr[:-1]] + [f"{run.sheet_of[tname]}!{r.source_row}"] for r in recs]
        sheet(wb, f"Cleaned_{tname}", hdr, rows)
        write_csv(csv_dir / f"{tname}.csv", hdr, rows)
    for jname, (cols, rows) in run.joined.items():
        data = [[r.get(c) for c in cols] for r in rows]
        sheet(wb, f"Joined_{jname}", cols, data)
        write_csv(csv_dir / f"joined_{jname}.csv", cols, data)

    used = Counter(c.rule for c in a.changes) + Counter(r.flag for r in a.review) + Counter(d.reason.split(":")[0] for d in a.dropped)
    sheet(wb, "Rules", ["rule", "stage", "what it does", "times applied"],
          [[k, st, desc, used.get(k, 0)] for k, (st, desc) in RULES.items()], {3: 100})
    sheet(wb, "Change log", ["table", "sheet", "row", "column", "before", "after", "rule", "confidence", "evidence"],
          [[c.table, c.sheet, c.source_row, c.column, show(c.before), show(c.after), c.rule, c.confidence, c.evidence] for c in a.changes],
          {5: 28, 6: 28, 9: 80})
    sheet(wb, "Dropped rows", ["table", "sheet", "row", "kind", "reason", "evidence", "original values"],
          [[d.table, d.sheet, d.source_row, d.kind, d.reason, d.evidence, d.raw_values] for d in a.dropped], {5: 50, 6: 60, 7: 90})
    sheet(wb, "Suspected duplicates", ["group", "table", "kind", "rows", "kept row", "similarity", "evidence"],
          [[g.group, g.table, g.kind, ", ".join(map(str, g.rows)), g.kept, g.similarity, g.evidence] for g in a.dups], {7: 100})
    jr = [list(j.values()) for j in a.joins]
    jh = list(a.joins[0].keys()) if a.joins else ["join"]
    ws = sheet(wb, "Join report", jh, jr)
    ws.append([])
    ws.append(["join", "step", "left row", "key", "issue", "detail"])
    for c in range(1, 7):
        ws.cell(ws.max_row, c).font = Font(bold=True)
        ws.cell(ws.max_row, c).fill = HEAD
    for d in a.join_details:
        ws.append([d["join"], d["step"], d["left_row"], d["key"], d["issue"], d["detail"]])
    sheet(wb, "Needs human review", ["table", "sheet", "row", "column", "value", "flag", "suggestion", "question", "decision"],
          [[r.table, r.sheet, r.source_row, r.column, show(r.value), r.flag, r.suggestion, r.question, ""] for r in a.review], {8: 90})
    sheet(wb, "Contract checks", ["table", "column", "type", "violations before", "violations after", "rows"],
          [list(c.values()) for c in a.checks])
    sheet(wb, "Reconcile", list(a.reconcile[0].keys()) if a.reconcile else ["table"], [list(x.values()) for x in a.reconcile])

    xlsx = out_dir / f"{name}-cleaned.xlsx"
    tmp = out_dir / f".{name}-cleaned.tmp.xlsx"
    wb.save(tmp)
    normalize_zip(tmp)
    os.replace(tmp, xlsx)

    summary = {
        "dataset": run.c.dataset,
        "llm": run.llm.label,
        "tables": {t: {**st, "rows_out": len(run.tables[t]),
                       "dropped": {k: v for (tt, k), v in drop_counts.items() if tt == t}} for t, st in run.stats.items()},
        "changes_by_rule": dict(sorted(rule_counts.items())),
        "review_by_flag": dict(sorted(flag_counts.items())),
        "joins": a.joins,
        "self_check": run.self_checks,
        "contract_checks": a.checks,
        "reconcile": a.reconcile,
        "notes": a.notes,
        "n_llm_changes": sum(1 for c in a.changes if c.rule.startswith("llm:")),
        "n_changes": len(a.changes), "n_review": len(a.review), "n_dropped": len(a.dropped), "n_dup_groups": len(a.dups),
    }
    audit = {"changes": [asdict(c) for c in a.changes], "dropped": [asdict(d) for d in a.dropped],
             "review": [asdict(r) for r in a.review], "dups": [asdict(d) for d in a.dups], "join_details": a.join_details}
    for fname, obj in (("run_summary.json", summary), ("audit.json", audit)):
        p = out_dir / fname
        tmpj = out_dir / f".{fname}.tmp"
        tmpj.write_text(json.dumps(obj, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        os.replace(tmpj, p)
    return summary


def write_csv(path: Path, header: list[str], rows: list[list[Any]]) -> None:
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in rows:
            w.writerow(["" if v is None else v.isoformat() if isinstance(v, (dt.date, dt.datetime)) else v for v in r])
    os.replace(tmp, path)
