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
from openpyxl.cell import WriteOnlyCell
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


XLSX_MAX_ROWS = 1_048_576   # Excel's hard limit per sheet, header included
BOLD = Font(bold=True)
WRAP = Alignment(wrap_text=True, vertical="top")


def xcell(ws, v: Any) -> Any:
    """A value for a write-only sheet; dates and long text get a styled cell."""
    v = cell(v)
    if isinstance(v, dt.date):
        c = WriteOnlyCell(ws, value=v)
        c.number_format = "yyyy-mm-dd hh:mm:ss" if isinstance(v, dt.datetime) else "yyyy-mm-dd"
        return c
    if isinstance(v, str) and len(v) > 60:
        c = WriteOnlyCell(ws, value=v)
        c.alignment = WRAP
        return c
    return v


def head_row(ws, labels: list[Any]) -> list[Any]:
    out = []
    for h in labels:
        c = WriteOnlyCell(ws, value=h)
        c.font, c.fill = BOLD, HEAD
        out.append(c)
    return out


XLSX_ROWS = 100_000   # rows per sheet in the workbook; beyond this the sheet is a preview and csv/ has everything


def cap(reserve: int = 0) -> int:
    return min(XLSX_ROWS, XLSX_MAX_ROWS - 2) - reserve


def sheet(wb: Workbook, title: str, header: list[str], rows: list[list[Any]], widths: dict[int, int] | None = None,
          total: int | None = None, spill: Path | None = None, spill_rows=None, reserve: int = 0):
    """Stream rows into a write-only sheet. If the table has more rows (`total`) than the sheet takes,
    the sheet ends with a pointer to the CSV `spill`; `spill_rows()` (a generator of all rows) writes it."""
    ws = wb.create_sheet(title[:31])
    for i, h in enumerate(header, start=1):
        w = (widths or {}).get(i) or min(60, max(10, len(str(h)) + 2, *(len(str(r[i - 1])) + 2 for r in rows[:200] if i - 1 < len(r))))
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"
    ws.append(head_row(ws, header))
    n = cap(reserve)
    for r in rows[:n]:
        ws.append([xcell(ws, v) for v in r])
    total = len(rows) if total is None else total
    if total > n:
        ws.append([f"... {total - n:,} more rows (sheet shows the first {n:,}); all {total:,} rows are in csv/{spill.name if spill else '?'}"])
        if spill is not None and spill_rows is not None:
            write_csv(spill, header, spill_rows())
    return ws


def big_table(wb, title, header, n, rowfn, items, widths=None, spill=None):
    """sheet() for a long list: only the preview rows are built in memory; the CSV is streamed."""
    k = cap()
    preview = [rowfn(x) for x in items[:k]]
    return sheet(wb, title, header, preview, widths, total=n, spill=spill, spill_rows=lambda: (rowfn(x) for x in items))


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
    wb = Workbook(write_only=True)   # streamed: memory stays flat however big the tables are
    big: list[str] = []              # notes about sheets cut at Excel's row limit
    csv_dir = out_dir / "csv"
    csv_dir.mkdir(exist_ok=True)
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
    over = big_sheets(run)
    for n in over:
        summ_rows.append(["note", "", "", n])
    sheet(wb, "Summary", ["section", "item", "value", "detail"], summ_rows, {1: 14, 2: 46, 3: 40, 4: 90})

    # ---- raw copies (untouched values and merges)
    for file, grids in run.grids.items():
        for g in grids:
            ws = wb.create_sheet(("Raw_" + (g.sheet or Path(g.source).stem))[:31])
            ws.sheet_properties.tabColor = "BFBFBF"
            k = cap() + 1
            for row in g.cells[:k]:
                ws.append([cell(v) for v in row])
            if len(g.cells) > k:
                ws.append([f"... {len(g.cells) - k:,} more rows: see the original file {g.source} (unchanged)"])
            for r1, c1, r2, c2 in g.merges:
                if r2 < k:
                    ws.merged_cells.add(f"{get_column_letter(c1 + 1)}{r1 + 1}:{get_column_letter(c2 + 1)}{r2 + 1}")

    # ---- cleaned tables (CSV always holds every row; the sheet holds up to XLSX_ROWS)
    for tname, recs in run.tables.items():
        t = run.c.tables[tname]
        extras = sorted({k for r in recs for k in r.values if k.startswith("extra:")}) + run.derived.get(tname, [])
        hdr = list(t.columns) + extras + ["_source"]
        sh = run.sheet_of[tname]
        rowfn = lambda r, hdr=hdr, sh=sh: [r.values.get(c) for c in hdr[:-1]] + [f"{sh}!{r.source_row}"]  # noqa: E731
        big_table(wb, f"Cleaned_{tname}", hdr, len(recs), rowfn, recs, spill=csv_dir / f"{tname}.csv")
        write_csv(csv_dir / f"{tname}.csv", hdr, (rowfn(r) for r in recs))
    for jname, (cols, rows) in run.joined.items():
        rowfn = lambda r, cols=cols: [r.get(c) for c in cols]  # noqa: E731
        big_table(wb, f"Joined_{jname}", cols, len(rows), rowfn, rows, spill=csv_dir / f"joined_{jname}.csv")
        write_csv(csv_dir / f"joined_{jname}.csv", cols, (rowfn(r) for r in rows))

    used = Counter(c.rule for c in a.changes) + Counter(r.flag for r in a.review) + Counter(d.reason.split(":")[0] for d in a.dropped)
    sheet(wb, "Rules", ["rule", "stage", "what it does", "times applied"],
          [[k, st, desc, used.get(k, 0)] for k, (st, desc) in RULES.items()], {3: 100})
    big_table(wb, "Change log", ["table", "sheet", "row", "column", "before", "after", "rule", "confidence", "evidence"], len(a.changes),
              lambda c: [c.table, c.sheet, c.source_row, c.column, show(c.before), show(c.after), c.rule, c.confidence, c.evidence],
              a.changes, {5: 28, 6: 28, 9: 80}, spill=csv_dir / "_change_log.csv")
    big_table(wb, "Dropped rows", ["table", "sheet", "row", "kind", "reason", "evidence", "original values"], len(a.dropped),
              lambda d: [d.table, d.sheet, d.source_row, d.kind, d.reason, d.evidence, d.raw_values], a.dropped, {5: 50, 6: 60, 7: 90},
              spill=csv_dir / "_dropped_rows.csv")
    big_table(wb, "Suspected duplicates", ["group", "table", "kind", "rows", "kept row", "similarity", "evidence"], len(a.dups),
              lambda g: [g.group, g.table, g.kind, ", ".join(map(str, g.rows)), g.kept, g.similarity, g.evidence], a.dups, {7: 100},
              spill=csv_dir / "_suspected_duplicates.csv")
    jr = [list(j.values()) for j in a.joins]
    jh = list(a.joins[0].keys()) if a.joins else ["join"]
    details = a.join_details[:max(0, cap() - len(jr) - 4)]
    ws = sheet(wb, "Join report", jh, jr, reserve=len(details) + 2)
    ws.append([])
    ws.append(head_row(ws, ["join", "step", "left row", "key", "issue", "detail"]))
    for d in details:
        ws.append([d["join"], d["step"], d["left_row"], d["key"], d["issue"], d["detail"]])
    if len(details) < len(a.join_details):
        ws.append([f"... {len(a.join_details) - len(details):,} more join details: see audit.json"])
    pats = review_patterns(run)
    sheet(wb, "Review patterns", ["table", "column", "flag", "cells", "distinct values", "share of rows", "example value", "example question", "hint"],
          [[p["table"], p["column"], p["flag"], p["cells"], p["distinct_values"], p["share_of_rows"], show(p["example_value"]),
            p["example_question"], p["hint"]] for p in pats], {8: 80, 9: 60})
    big_table(wb, "Needs human review", ["table", "sheet", "row", "column", "value", "flag", "suggestion", "question", "decision"], len(a.review),
              lambda r: [r.table, r.sheet, r.source_row, r.column, show(r.value), r.flag, r.suggestion, r.question, ""], a.review, {8: 90},
              spill=csv_dir / "_needs_review.csv")
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
        "notes": a.notes + over,
        "review_patterns": [{k: v for k, v in p.items() if k != "example_value"} | {"example_value": show(p["example_value"])} for p in pats[:30]],
        "n_llm_changes": sum(1 for c in a.changes if c.rule.startswith("llm:")),
        "n_changes": len(a.changes), "n_review": len(a.review), "n_dropped": len(a.dropped), "n_dup_groups": len(a.dups),
    }
    write_json(out_dir / "run_summary.json", summary)
    write_audit_json(out_dir / "audit.json", a)
    return summary


def review_patterns(run: Run) -> list[dict]:
    """Review items grouped by (table, column, flag): one decision per pattern instead of one per cell.

    A pattern covering most of a column usually means the contract is wrong for that column (a code typed
    as a number, a missing vocabulary value), which is fixed once in the contract, not cell by cell.
    """
    groups: dict[tuple, list] = {}
    for r in run.audit.review:
        groups.setdefault((r.table, r.column, r.flag), []).append(r)
    out = []
    for (t, c, f), items in groups.items():
        n_rows = len(run.raw_tables.get(t) or run.tables.get(t) or []) or 1
        share = len(items) / n_rows
        distinct = len({repr(x.value) for x in items})
        hint = ""
        if len(items) >= 100 and share >= 0.5:
            hint = "most of the column: likely a contract issue (type, regex or vocabulary) - fix it once in the contract"
        elif len(items) >= 100 and distinct <= max(5, len(items) // 50):
            hint = f"only {distinct} distinct value(s): decide per value (contract overrides/vocabulary), not per cell"
        out.append({"table": t, "column": c, "flag": f, "cells": len(items), "distinct_values": distinct,
                    "share_of_rows": round(share, 4), "example_value": items[0].value, "example_question": items[0].question, "hint": hint})
    return sorted(out, key=lambda p: (-p["cells"], p["table"], p["column"], p["flag"]))


def big_sheets(run: Run) -> list[str]:
    """Notes for every sheet that will be a preview (known before anything is written)."""
    a, k, out = run.audit, cap(), []
    sizes = {"Change log": (len(a.changes), "_change_log.csv"), "Dropped rows": (len(a.dropped), "_dropped_rows.csv"),
             "Suspected duplicates": (len(a.dups), "_suspected_duplicates.csv"), "Needs human review": (len(a.review), "_needs_review.csv")}
    sizes.update({f"Cleaned_{t}"[:31]: (len(r), f"{t}.csv") for t, r in run.tables.items()})
    sizes.update({f"Joined_{j}"[:31]: (len(rows), f"joined_{j}.csv") for j, (_, rows) in run.joined.items()})
    for name, (n, spill) in sizes.items():
        if n > k:
            out.append(f"sheet {name!r}: {n:,} rows; the workbook shows the first {k:,}, csv/{spill} has all of them")
    for grids in run.grids.values():
        for g in grids:
            if len(g.cells) > k + 1:
                out.append(f"sheet 'Raw_{g.sheet or Path(g.source).stem}': first {k + 1:,} of {len(g.cells):,} rows; the original file {g.source} has them all")
    return out


def write_json(path: Path, obj: Any) -> None:
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    os.replace(tmp, path)


def write_audit_json(path: Path, a) -> None:
    """Same bytes as json.dumps({...}, indent=1), but streamed item by item (audit lists reach millions)."""
    parts = (("changes", a.changes, True), ("dropped", a.dropped, True), ("review", a.review, True),
             ("dups", a.dups, True), ("join_details", a.join_details, False))
    tmp = path.with_name(f".{path.name}.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        f.write("{")
        for i, (key, items, dc) in enumerate(parts):
            f.write(("," if i else "") + f'\n "{key}": ')
            if not items:
                f.write("[]")
                continue
            f.write("[")
            for j, it in enumerate(items):
                txt = json.dumps(asdict(it) if dc else it, ensure_ascii=False, indent=1, default=str)
                f.write(("," if j else "") + "\n  " + txt.replace("\n", "\n  "))
            f.write("\n ]")
        f.write("\n}")
    os.replace(tmp, path)


def write_csv(path: Path, header: list[str], rows) -> None:
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in rows:
            w.writerow(["" if v is None else v.isoformat() if isinstance(v, (dt.date, dt.datetime)) else v for v in r])
    os.replace(tmp, path)
