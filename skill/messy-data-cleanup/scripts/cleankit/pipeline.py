"""Run a contract over raw files: structure -> text -> shift -> types -> categories -> dedup -> checks -> joins.

Fix order follows normalize-before-dedupe: nothing is compared for duplicates until every value
is in canonical form. Blanks are never filled. Every changed cell leaves a Change; every removed
row a Dropped; every doubt a Review.
"""
from __future__ import annotations

import datetime as dt
import re
import resource
import time
from collections import Counter, defaultdict
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from . import normalize as N
from .contract import NUMERIC, Column, Contract, Table
from .io_read import read_any
from .llm import LLM
from . import llm_tasks as L
from .match import BUILTIN_VOCAB, Vocab, fold, similarity
from .model import RULES, Audit, Change, Dropped, DupGroup, Grid, Record, Review, RowKind
from .structure import GRAND_RE, SUM_RE, block_starts, best_shift, classify, fill_merges, find_headers

PHONE_OK = re.compile(r"^0\d{1,2}-\d{3,4}-\d{4}$")


def col_letter(c: int) -> str:
    s = ""
    c += 1
    while c:
        c, r = divmod(c - 1, 26)
        s = chr(65 + r) + s
    return s


class Run:
    def __init__(self, contract: Contract, input_dir: Path, llm: LLM | None = None):
        self.c = contract
        self.llm = llm or LLM("off")
        self.derived: dict[str, list[str]] = {}   # LLM-extracted columns per table
        self.input_dir = input_dir
        self.audit = Audit()
        self.grids: dict[str, list[Grid]] = {}
        self.tables: dict[str, list[Record]] = {}
        self.raw_tables: dict[str, list[Record]] = {}
        self.vocabs: dict[tuple[str, str], Vocab] = {}
        self.sheet_of: dict[str, str] = {}
        self.subtotals: dict[str, list[dict]] = defaultdict(list)
        self.stats: dict[str, dict] = {}
        self.dup_dropped: dict[str, list[Record]] = defaultdict(list)
        self.joined: dict[str, tuple[list[str], list[dict]]] = {}
        self.layout: dict[str, list[str]] = {}
        self.perf: list[dict] = []   # per-stage wall time and memory; kept out of the audit files

    @contextmanager
    def timed(self, stage: str, table: str = ""):
        t0 = time.perf_counter()
        try:
            yield
        finally:
            self.perf.append({"stage": stage, "table": table, "sec": round(time.perf_counter() - t0, 3),
                              "rss_mb": round(rss_mb()), "peak_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024)})

    # ------------------------------------------------------------ logging helpers
    def log(self, t: str, row: int, col: str, steps: list[N.Step]) -> None:
        for s in steps:
            assert s.rule in RULES, s.rule
            self.audit.changes.append(Change(t, self.sheet_of[t], row, col, s.before, s.after, s.rule, s.confidence, s.evidence))

    def flag(self, t: str, row: int, col: str, value: Any, f: tuple[str, str, str]) -> None:
        assert f[0] in RULES, f[0]
        self.audit.review.append(Review(t, self.sheet_of[t], row, col, value, f[0], f[1], f[2]))

    def apply(self, t: str, rec: Record, col: str, o: N.Outcome) -> None:
        self.log(t, rec.source_row, col, o.steps)
        rec.values[col] = o.value
        if o.flag:
            self.flag(t, rec.source_row, col, o.value, o.flag)

    # ------------------------------------------------------------ validators
    def vocab(self, t: Table, col: Column) -> Vocab:
        key = (t.name, col.name)
        if key not in self.vocabs:
            canon: dict[str, list[str]] = {}
            if col.vocab_builtin:
                canon.update({k: list(v) for k, v in BUILTIN_VOCAB[col.vocab_builtin].items()})
            for k, v in (col.vocab or {}).items():
                canon.setdefault(k, []).extend(v or [])
            if col.vocab_from:
                ft, _, fc = col.vocab_from.partition(".")
                for name in [n for n in self.c.tables if n == ft or self.c.tables[n].file == self.c.tables[ft].file and self.c.tables[n].sheet == self.c.tables[ft].sheet]:
                    for r in self.tables.get(name, []):
                        if not N.is_blank(r.values.get(fc)):
                            canon.setdefault(r.values[fc], [])
            self.vocabs[key] = Vocab(canon, self.c.fuzzy_auto, self.c.fuzzy_margin)
        return self.vocabs[key]

    def fits(self, t: Table, col: Column):
        """Loose 'could this value belong here' test, used only to detect shifted rows. Memoized per value."""
        memo: dict[tuple[type, Any], bool | None] = {}

        def f(v: Any) -> bool | None:
            try:
                key = (type(v), v)
                if key not in memo:
                    memo[key] = g(v)
                return memo[key]
            except TypeError:
                return g(v)

        def g(v: Any) -> bool | None:
            if col.type in ("text", "freetext"):
                return None
            if col.type == "id":
                s = str(int(v)) if isinstance(v, float) and v.is_integer() else str(v)
                return re.fullmatch(col.regex, s.strip()) is not None
            if col.type == "date":
                return bool(N.date_candidates(v, 2000)[0])
            if col.type in NUMERIC:
                o = N.parse_number(v, ",", True) if col.decimal == "," else N.parse_number(v, ".", True)
                if o.flag or not isinstance(o.value, (int, float)):
                    return False
                return (col.min is None or o.value >= col.min) and (col.max is None or o.value <= col.max)
            if col.type == "category":
                if col.vocab_from:
                    return None
                return self.vocab(t, col).match(v).flag is None
            if col.type == "email":
                return "@" in str(v)
            if col.type == "phone":
                return len(re.sub(r"\D", "", str(v))) >= 9 and len(re.sub(r"[\d\s\-.+()]", "", str(v))) == 0
            return None
        return f

    def conforms(self, t: Table, col: Column, v: Any) -> bool:
        """Strict contract check on the stored value."""
        if N.is_blank(v):
            return not col.required
        if col.type == "id":
            return isinstance(v, str) and N.parse_id(v, col.regex, col.format).value == v
        if col.type == "date":
            return isinstance(v, dt.date)
        if col.type in NUMERIC:
            return isinstance(v, (int, float)) and not isinstance(v, bool) and (col.min is None or v >= col.min) and (col.max is None or v <= col.max)
        if col.type == "category":
            return self.vocab(t, col).contains(v)
        if col.type == "phone":
            return isinstance(v, str) and bool(PHONE_OK.match(v))
        if col.type == "email":
            return isinstance(v, str) and bool(N.EMAIL_RE.match(v))
        if isinstance(v, str):
            return N.normalize_text(v, col.type == "freetext").value == v
        return True

    def violations(self, t: Table, recs: list[Record], use_raw: bool = False) -> dict[str, int]:
        out = {}
        for cname, col in t.columns.items():
            vals = [(r.raw if use_raw else r.values).get(cname) for r in recs]
            out[cname] = sum(not self.conforms(t, col, v) for v in vals)
        return out

    # ------------------------------------------------------------ stage 1: structure
    def grid_for(self, t: Table) -> Grid:
        if t.file not in self.grids:
            with self.timed("read", t.file):
                self.grids[t.file] = read_any(self.input_dir / t.file)
        for g in self.grids[t.file]:
            if g.sheet == t.sheet or (not t.sheet and len(self.grids[t.file]) == 1):
                return g
        raise SystemExit(f"{t.name}: sheet {t.sheet!r} not found in {t.file}")

    def extract(self, t: Table) -> list[Record]:
        g = self.grid_for(t)
        with self.timed("structure", t.name):
            return self._extract(t, g)

    def _extract(self, t: Table, g: Grid) -> list[Record]:
        self.sheet_of[t.name] = g.sheet or Path(g.source).stem
        cells, origin = fill_merges(g)
        aliases = {c: col.aliases for c, col in t.columns.items()}
        headers = find_headers(cells, aliases)
        starts = block_starts(cells, headers)
        if len(starts) < t.block:
            raise SystemExit(f"{t.name}: header block {t.block} not found in {g.source}/{g.sheet}")
        h = starts[t.block - 1]
        same_sheet = [x for x in self.c.tables.values() if x.file == t.file and x.sheet == t.sheet]
        if len(same_sheet) == 1:
            end = len(cells)
            region_start = 0
        else:
            nxt = starts[t.block] if t.block < len(starts) else None
            end = nxt.start if nxt else len(cells)
            region_start = 0 if t.block == 1 else h.start
        sheet = self.sheet_of[t.name]
        width = max(h.mapping.values()) + 1
        header_folds = {fold(a) for al in aliases.values() for a in al} | {fold(x) for x in h.labels.values()}
        for v in h.labels.values():
            header_folds |= {fold(p) for p in str(v).split(" ")}
        key_col = t.columns[t.key] if t.key else None
        key_ok = (lambda v: self.fits(t, key_col)(v) is True) if key_col else (lambda v: False)
        n_in = 0
        recs: list[Record] = []
        mapping = dict(h.mapping)
        extras = {f"extra:{lab}": c for c, lab in h.extras.items() if c < width + 3}
        mapping_all = {**mapping, **extras}
        ordered = sorted(mapping_all.items(), key=lambda kv: kv[1])
        self.layout[t.name] = [n for n, _ in ordered]
        last_sub = None
        for r in range(region_start, end):
            n_in += 1
            row = cells[r] + [None] * max(0, width + 3 - len(cells[r]))
            rawrow = g.cells[r] + [None] * max(0, width + 3 - len(g.cells[r]))
            if h.start <= r < h.start + h.depth:
                self.audit.dropped.append(Dropped(t.name, sheet, g.row_no(r), RowKind.HEADER.value, "header row (mapped to contract columns)",
                                                  "; ".join(f"{col_letter(c)}={h.labels.get(c)}→{n}" for n, c in sorted(h.mapping.items(), key=lambda x: x[1])) +
                                                  (" [S1-HEADER2: 2-row header combined]" if h.depth == 2 else ""), show_row(g.cells[r])))
                continue
            if r < h.start:
                kind = RowKind.BLANK if all(N.is_blank(v) for v in row) else RowKind.TITLE
            else:
                kind = classify(row[:width + 3], header_folds, key_ok, row[mapping[t.key]] if t.key else None)
            if kind != RowKind.DATA:
                rule = {RowKind.TITLE: "S1-TITLE", RowKind.REPEATED_HEADER: "S1-REPHEADER", RowKind.SUBTOTAL: "S1-SUBTOTAL",
                        RowKind.NOTE: "S1-NOTE", RowKind.BLANK: "S1-BLANK"}[kind]
                self.audit.dropped.append(Dropped(t.name, sheet, g.row_no(r), kind.value, f"{rule}: {RULES[rule][1]}", "", show_row(g.cells[r])))
                if kind == RowKind.SUBTOTAL and SUM_RE.search(next(str(v) for v in row if isinstance(v, str) and v.strip())):
                    label = next(str(v) for v in row if isinstance(v, str) and v.strip())
                    self.subtotals[t.name].append({"row": g.row_no(r), "label": label, "grand": bool(GRAND_RE.search(label)),
                                                   "after": last_sub, "cells": {n: row[c] for n, c in mapping.items()}})
                    if not GRAND_RE.search(label):
                        last_sub = g.row_no(r)
                continue
            rec = Record(t.name, g.row_no(r), {}, {})
            for name, c in ordered:
                rec.values[name] = row[c]
                rec.raw[name] = rawrow[c]
            # overflow cells to the right of the last column (shift evidence)
            for i in range(width, width + 3):
                if not N.is_blank(row[i]) and i not in mapping_all.values():
                    rec.values[f"_overflow{i}"] = row[i]
                    rec.raw[f"_overflow{i}"] = rawrow[i]
            for name, c in ordered:
                if (r, c) in origin and not N.is_blank(row[c]):
                    o0 = origin[(r, c)]
                    self.log(t.name, g.row_no(r), name, [N.Step("S2-MERGE", None, row[c], 1.0,
                             f"merged range starting {col_letter(o0[1])}{o0[0] + 1}")])
            recs.append(rec)
        self.stats[t.name] = {"rows_in": n_in, "header_row": h.start + 1, "header_depth": h.depth,
                              "mapped": {n: col_letter(c) for n, c in sorted(h.mapping.items(), key=lambda x: x[1])},
                              "unmapped": [n for n in t.columns if n not in h.mapping], "extras": list(extras)}
        for n in t.columns:
            if n not in h.mapping:
                for rec in recs:
                    rec.values[n] = None
                    rec.raw[n] = None
        return recs

    # ------------------------------------------------------------ stage 2-4: values
    def clean_table(self, t: Table) -> None:
        recs = self.extract(t)
        with self.timed("text", t.name):
            self.text_stage(t, recs)
        with self.timed("shift", t.name):
            self.shift_stage(t, recs)
        with self.timed("types", t.name):
            self.types_stage(t, recs)
        with self.timed("llm", t.name):
            self.apply_overrides(t, recs)
            L.resolve_open_items(self, t, recs)   # owner overrides first: a human decision always wins
            L.extract_fields(self, t, recs)
        with self.timed("required", t.name):
            self.required_stage(t, recs)
        self.raw_tables[t.name] = recs
        with self.timed("dedup", t.name):
            self.tables[t.name] = self.dedup(t, recs)
            gone = {r.source_row for r in self.dup_dropped[t.name]}   # a dropped copy repeats its kept twin's flags
            self.audit.review = [x for x in self.audit.review if not (x.table == t.name and x.source_row in gone)]
        with self.timed("checks", t.name):
            self.cross_checks(t, self.tables[t.name])

    def text_stage(self, t: Table, recs: list[Record]) -> None:
        """Text normalization + placeholders (all cells)."""
        cols = t.columns
        for rec in recs:
            for name in list(rec.values):
                col = cols.get(name)
                o = N.normalize_text(rec.values[name], freetext=bool(col and col.type == "freetext"))
                is_vocab_word = col is not None and col.type == "category" and fold(o.value) in self.vocab(t, col).alias
                if (col is None or col.type != "freetext") and not is_vocab_word:   # 'X' can mean 'N' in a Y/N vocab
                    N.placeholder(o)
                self.apply(t.name, rec, name, o)

    def shift_stage(self, t: Table, recs: list[Record]) -> None:
        cols = t.columns
        order = self.layout[t.name]
        fits = [self.fits(t, cols[n]) if n in cols else (lambda v: None) for n in order]
        for rec in recs:
            row = [rec.values.get(n) for n in order] + [v for k, v in rec.values.items() if k.startswith("_overflow")]
            res = best_shift(row, fits)
            if res:
                new, how, b, a = res
                for i, n in enumerate(order):
                    if rec.values.get(n) != new[i]:
                        self.log(t.name, rec.source_row, n, [N.Step("S3-SHIFT", rec.values.get(n), new[i], round(1 - a / max(b, 1), 2),
                                                                      f"{how}: type violations {b} -> {a}")])
                        rec.values[n] = new[i]
                for k in [k for k in rec.values if k.startswith("_overflow")]:
                    del rec.values[k]
            elif any(k.startswith("_overflow") for k in rec.values):
                self.flag(t.name, rec.source_row, "(row)", "", ("R8-SHIFT", "", "values found right of the last column: is this row misaligned?"))
        for rec in recs:
            for k in [k for k in rec.values if k.startswith("_overflow")]:
                del rec.values[k]

    def types_stage(self, t: Table, recs: list[Record]) -> None:
        """Typed columns, column by column, with a no-regression guard."""
        for name, col in t.columns.items():
            before = [r.values.get(name) for r in recs]
            v0 = sum(not self.conforms(t, col, v) for v in before)
            snapshot = (len(self.audit.changes), len(self.audit.review))
            self.type_column(t, col, recs)
            v1 = sum(not self.conforms(t, col, r.values.get(name)) for r in recs)
            if v1 > v0:   # never keep a transform that makes the column worse
                for r, v in zip(recs, before):
                    r.values[name] = v
                del self.audit.changes[snapshot[0]:]
                del self.audit.review[snapshot[1]:]
                self.audit.notes.append(f"{t.name}.{name}: typed stage rejected (violations {v0} -> {v1})")

    def required_stage(self, t: Table, recs: list[Record]) -> None:
        for rec in recs:
            for name, col in t.columns.items():
                if col.required and N.is_blank(rec.values.get(name)) and not any(
                        rv.source_row == rec.source_row and rv.column == name and rv.table == t.name for rv in self.audit.review):
                    self.flag(t.name, rec.source_row, name, "", ("R7-REQUIRED", "", f"{name} is required but blank: what is it? (not imputed)"))

    def type_column(self, t: Table, col: Column, recs: list[Record]) -> None:
        name = col.name
        vals = [r.values.get(name) for r in recs]
        if col.type == "id":
            for r in recs:
                self.apply(t.name, r, name, N.parse_id(r.values.get(name), col.regex, col.format))
        elif col.type in NUMERIC:
            dec, why = (col.decimal, "contract") if col.decimal in (".", ",") else N.decide_decimal(vals)
            if dec == ",":
                self.audit.notes.append(f"{t.name}.{name}: decimal comma column ({why})")
            for r in recs:
                o = N.parse_number(r.values.get(name), dec, allow_percent=col.type == "percent")
                if isinstance(o.value, (int, float)) and not o.flag and ((col.min is not None and o.value < col.min) or (col.max is not None and o.value > col.max)):
                    o.flag = ("R2-NUMBER", "", f"{o.value} is outside the expected range {col.min}..{col.max}")
                self.apply(t.name, r, name, o)
            if col.type == "percent":
                nums = [r.values.get(name) for r in recs if isinstance(r.values.get(name), (int, float))]
                if any(v > 1 for v in nums):
                    for r in recs:
                        v = r.values.get(name)
                        if isinstance(v, (int, float)) and 0 < v < 1:
                            self.flag(t.name, r.source_row, name, v, ("R2-NUMBER", str(round(v * 100, 6)),
                                      f"{v} looks like a fraction in a 0-100 percent column: is it {v * 100:g}%? (not converted)"))
        elif col.type == "date":
            years = Counter()
            for v in vals:
                cands = N.date_candidates(v, None)[0] if not N.is_blank(v) else []
                if len({d for _, d in cands}) == 1:
                    years[cands[0][1].year] += 1
            year_hint = years.most_common(1)[0][0] if years else None
            sure = sorted(d for v in vals if not N.is_blank(v) for c in [N.date_candidates(v, None)[0]] if len({x for _, x in c}) == 1 for d in [c[0][1]])
            if t.date_window:
                window = (dt.date.fromisoformat(t.date_window[0]), dt.date.fromisoformat(t.date_window[1]))
            elif sure:
                window = (sure[0] - dt.timedelta(days=31), sure[-1] + dt.timedelta(days=31))
            else:
                window = None
            pref = list(t.date_order)
            votes = Counter()
            for v in vals:
                if isinstance(v, str) and (m := N.RE_XXY4.match(v.strip())):
                    a, b = int(m.group(1)), int(m.group(2))
                    if a > 12 >= b:
                        votes["DMY"] += 1
                    elif b > 12 >= a:
                        votes["MDY"] += 1
            if len(votes) == 1:
                winner = next(iter(votes))
                pref = [winner] + [p for p in pref if p != winner]
                self.audit.notes.append(f"{t.name}.{name}: day/month order {winner} decided by {votes[winner]} value(s) with a part > 12")
            for r in recs:
                self.apply(t.name, r, name, N.parse_date(r.values.get(name), pref, year_hint, window))
        elif col.type == "phone":
            for r in recs:
                self.apply(t.name, r, name, N.parse_phone(r.values.get(name)))
        elif col.type == "email":
            for r in recs:
                self.apply(t.name, r, name, N.parse_email(r.values.get(name)))
        elif col.type == "category":
            vb = self.vocab(t, col)
            for r in recs:
                v = r.values.get(name)
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    v = r.values[name] = str(v)
                self.apply(t.name, r, name, vb.match(v))

    def apply_overrides(self, t: Table, recs: list[Record]) -> None:
        for ov in self.c.overrides:
            if ov.get("table") != t.name:
                continue
            for r in recs:
                if ("row" in ov and ov["row"] != r.source_row) or str(r.values.get(ov["column"])) != str(ov["before"]):
                    continue
                self.log(t.name, r.source_row, ov["column"], [N.Step("O1-DECISION", r.values[ov["column"]], ov["after"], 1.0, "owner decision (contract overrides)")])
                r.values[ov["column"]] = ov["after"]
                self.audit.review = [x for x in self.audit.review if not (x.table == t.name and x.source_row == r.source_row and x.column == ov["column"])]

    # ------------------------------------------------------------ stage 5: duplicates
    def dedup(self, t: Table, recs: list[Record]) -> list[Record]:
        extras = sorted({k for r in recs for k in r.values if k.startswith("extra:")})
        index_cols = [k for k in extras if is_row_index([r.values.get(k) for r in recs])]
        if index_cols:
            self.audit.notes.append(f"{t.name}: {', '.join(index_cols)} is a running row number; ignored when comparing rows for duplicates")
        cols = list(t.columns) + [k for k in extras if k not in index_cols]
        sig = lambda r: tuple(repr(r.values.get(c)) for c in cols)  # noqa: E731
        seen: dict[tuple, Record] = {}
        kept: list[Record] = []
        n = 0
        for r in recs:
            s = sig(r)
            if s in seen and t.exact_dups == "drop":
                first = seen[s]
                differed = [c for c in cols if r.raw.get(c) != first.raw.get(c)]
                ev = f"identical to row {first.source_row} after normalization" + (f"; raw text differed in {', '.join(differed)}" if differed else "; raw row was a verbatim copy")
                self.audit.dropped.append(Dropped(t.name, self.sheet_of[t.name], r.source_row, "duplicate", "U1-EXACT: " + RULES["U1-EXACT"][1], ev,
                                                  " | ".join("" if r.raw.get(c) is None else str(r.raw.get(c)) for c in cols)))
                n += 1
                self.audit.dups.append(DupGroup(f"{t.name}-X{n}", t.name, "exact", [first.source_row, r.source_row], first.source_row, 1.0, ev))
                self.dup_dropped[t.name].append(r)
                continue
            seen.setdefault(s, r)
            kept.append(r)
        if t.key:
            by_key = defaultdict(list)
            for r in kept:
                if not N.is_blank(r.values.get(t.key)):
                    by_key[r.values[t.key]].append(r)
            for k, rs in by_key.items():
                if len(rs) > 1:
                    diff = [c for c in t.columns if len({repr(r.values.get(c)) for r in rs}) > 1]
                    n += 1
                    ev = f"{t.key}={k} on rows {', '.join(str(r.source_row) for r in rs)}; differs in {', '.join(diff)}"
                    self.audit.dups.append(DupGroup(f"{t.name}-K{n}", t.name, "key_conflict", [r.source_row for r in rs], None, 0.0, ev))
                    for r in rs:
                        self.flag(t.name, r.source_row, t.key, k, ("U3-KEYCONFLICT", "", f"same {t.key} {k} with different {', '.join(diff)}: which row is right?"))
        groups: list[tuple[list[Record], str]] = []
        for keyset in t.suspect_keys:
            bucket = defaultdict(list)
            for r in kept:
                vals = tuple(repr(r.values.get(c)) for c in keyset)
                if all(not N.is_blank(r.values.get(c)) for c in keyset):
                    bucket[vals].append(r)
            for vals, rs in bucket.items():
                if len(rs) > 1 and (not t.key or len({r.values.get(t.key) for r in rs}) == len(rs)):
                    groups.append((rs, f"same {' + '.join(keyset)}"))
        if t.contact_keys:
            parent = {r.source_row: r.source_row for r in kept}

            def find(x):
                while parent[x] != x:
                    x = parent[x]
                return x
            why = defaultdict(set)
            for c in t.contact_keys:
                idx = defaultdict(list)
                for r in kept:
                    v = r.values.get(c)
                    if not N.is_blank(v):
                        idx[fold(v)].append(r.source_row)
                for rows in idx.values():
                    for x in rows[1:]:
                        parent[find(x)] = find(rows[0])
                    if len(rows) > 1:
                        why[tuple(rows)].add(c)
            comp = defaultdict(list)
            for r in kept:
                comp[find(r.source_row)].append(r)
            name_col = next((c for c, col in t.columns.items() if col.type == "text"), None)
            for rs in comp.values():
                if len(rs) > 1:
                    shared = sorted({c for rows, cs in why.items() if set(rows) & {r.source_row for r in rs} for c in cs})
                    nsim = similarity(str(rs[0].values.get(name_col)), str(rs[1].values.get(name_col))) if name_col else 0.0
                    # one shared contact (a family phone) is not identity; need two contacts, or one plus a similar name
                    if len(shared) >= 2 or nsim >= 0.8:
                        groups.append((rs, f"same {' + '.join(shared)}"))
                    else:
                        self.audit.notes.append(f"{t.name}: rows {', '.join(str(r.source_row) for r in rs)} share {' + '.join(shared)} but names differ "
                                                f"({name_col} similarity {nsim:.2f}); not listed as duplicates (shared family/company contact?)")
        for rs, how in groups:
            others = [c for c in t.columns if c != t.key]
            a, b = rs[0], rs[1]
            eq = sum(repr(a.values.get(c)) == repr(b.values.get(c)) for c in others) / max(1, len(others))
            name_cols = [c for c, col in t.columns.items() if col.type == "text"]
            name_sim = f"; {name_cols[0]} similarity {similarity(str(a.values.get(name_cols[0])), str(b.values.get(name_cols[0]))):.2f}" if name_cols else ""
            n += 1
            gid = f"{t.name}-S{n}"
            keys = ", ".join(f"{r.values.get(t.key)}@row{r.source_row}" for r in rs) if t.key else ", ".join(f"row{r.source_row}" for r in rs)
            self.audit.dups.append(DupGroup(gid, t.name, "suspected", [r.source_row for r in rs], None, round(eq, 3),
                                            f"{how}; {eq:.0%} of other columns equal{name_sim}; keys {keys}. Not merged."))
            for r in rs:
                self.flag(t.name, r.source_row, t.key or "(row)", r.values.get(t.key) if t.key else "",
                          ("U2-SUSPECT", gid, f"possible duplicate ({how}) in group {gid}: same record?"))
        return kept

    # ------------------------------------------------------------ stage 6: checks
    def cross_checks(self, t: Table, recs: list[Record]) -> None:
        env = {"nz": lambda x: 0 if x is None else x, "round": round, "abs": abs, "blank": N.is_blank}
        for chk in t.checks:
            code = compile(chk["expr"], f"<check {chk.get('name')}>", "eval")
            for r in recs:
                try:
                    ok = eval(code, {"__builtins__": {}}, {**env, **r.values})  # contract is trusted config
                except TypeError:
                    continue   # a needed value is blank or not numeric; that is reported elsewhere
                if not ok:
                    hint = ""
                    if chk.get("expected"):
                        try:
                            hint = str(eval(compile(chk["expected"], "<exp>", "eval"), {"__builtins__": {}}, {**env, **r.values}))
                        except TypeError:
                            pass
                    open_flags = sorted({x.column for x in self.audit.review if x.table == t.name and x.source_row == r.source_row})
                    msg = chk.get("message", chk["expr"]) + (f" (this row also has open flags on {', '.join(open_flags)}; fix those first)" if open_flags else "")
                    self.flag(t.name, r.source_row, chk.get("column", "(row)"), r.values.get(chk.get("column")), ("R6-CROSS", hint, msg))

    # ------------------------------------------------------------ stage 7: joins
    def run_joins(self) -> None:
        for j in self.c.joins:
            left = self.tables[j.left]
            rows = [dict(r.values, _source=f"{self.sheet_of[j.left]}!{r.source_row}") for r in left]
            cols = list(self.c.tables[j.left].columns) + ["_source"]
            for st in j.steps:
                lk, rk = st.on
                right = [(rt, r) for rt in st.right for r in self.tables[rt]]
                idx = defaultdict(list)
                raw_keys = set()
                for rt, r in right:
                    if not N.is_blank(r.values.get(rk)):
                        idx[r.values[rk]].append((rt, r))
                    raw_keys.add(str(r.raw.get(rk)).strip())
                fb = defaultdict(list)
                if st.fallback:
                    for rt, r in right:
                        if not N.is_blank(r.values.get(st.fallback[1])):
                            fb[fold(r.values[st.fallback[1]])].append((rt, r))
                rcols = [c for c in dict.fromkeys(c for rt in st.right for c in self.c.tables[rt].columns) if c != rk]
                counts = Counter()
                raw_hits = 0
                status_col = f"_join_{st.prefix.rstrip('_')}"
                pending = []
                for row, rec in zip(rows, left):
                    key = row.get(lk)
                    raw_hits += str(rec.raw.get(lk)).strip() in raw_keys and not N.is_blank(rec.raw.get(lk))
                    hits, method = [], ""
                    if not N.is_blank(key):
                        hits, method = idx.get(key, []), "exact key"
                    if not hits and st.fallback and not N.is_blank(row.get(st.fallback[0])):
                        hits, method = fb.get(fold(row[st.fallback[0]]), []), f"fallback on {st.fallback[0]}"
                    if len(hits) == 1:
                        rt, r = hits[0]
                        for c in rcols:
                            row[st.prefix + c] = r.values.get(c)
                        if method.startswith("fallback"):
                            row[st.prefix + rk] = r.values.get(rk)
                        status = "matched" + ("" if method == "exact key" else f" ({method})") + ("" if rt == st.right[0] else f" [in {rt}]")
                        counts["fallback" if method.startswith("fallback") else "exact"] += 1
                        if rt != st.right[0]:
                            counts[f"in {rt}"] += 1
                        for lc, rc in st.compare:
                            if fold(row.get(lc)) != fold(r.values.get(rc)) and not N.is_blank(row.get(lc)):
                                self.flag(j.left, rec.source_row, lc, row.get(lc), ("R6-CROSS", str(r.values.get(rc)),
                                          f"{lc} {row.get(lc)!r} differs from {rt}.{rc} {r.values.get(rc)!r} for {lk}={key}: which is right?"))
                    elif len(hits) > 1:
                        status = f"ambiguous ({len(hits)} matches)"
                        counts["ambiguous"] += 1
                        self.audit.join_details.append({"join": j.name, "step": "+".join(st.right), "left_row": rec.source_row, "key": key,
                                                        "issue": "J3-AMBIG", "detail": f"{len(hits)} rows in {'/'.join(st.right)} share this key; not joined to avoid multiplying rows"})
                        self.flag(j.left, rec.source_row, lk, key, ("J3-AMBIG", "", f"{lk}={key} matches {len(hits)} rows: which one?"))
                    elif N.is_blank(key) and not st.fallback:
                        status = "blank key"
                        counts["blank"] += 1
                        pending.append((row, rec, key))
                    else:
                        status = "orphan"
                        counts["orphan"] += 1
                        pending.append((row, rec, key))
                        self.audit.join_details.append({"join": j.name, "step": "+".join(st.right), "left_row": rec.source_row, "key": key,
                                                        "issue": "J2-ORPHAN", "detail": f"no row in {'/'.join(st.right)} with {rk}={key!r}" + (f" or {st.fallback[1]}={row.get(st.fallback[0])!r}" if st.fallback else "")})
                        self.flag(j.left, rec.source_row, lk, key, ("J2-ORPHAN", "", f"{lk}={key!r} not found in {'/'.join(st.right)}: typo, or missing master row?"))
                    row[status_col] = status
                rules_matched = counts["exact"] + counts["fallback"]
                found = L.resolve_entities(self, j.name, st, j.left, pending, right, rk)
                for row, rec, key in pending:
                    if rec.source_row not in found:
                        continue
                    rt, r, a = found[rec.source_row]
                    for c in rcols:
                        row[st.prefix + c] = r.values.get(c)
                    row[st.prefix + rk] = r.values.get(rk)
                    counts["blank" if row[status_col] == "blank key" else "orphan"] -= 1
                    counts["llm"] += 1
                    row[status_col] = "matched (llm entity)" + ("" if rt == st.right[0] else f" [in {rt}]")
                    ev = L.evidence(self, a["confidence"], a["evidence_quote"], a["rationale"])
                    self.audit.changes.append(Change(j.left, self.sheet_of[j.left], rec.source_row, st.prefix + rk, key, r.values.get(rk),
                                                     "llm:entity", round(a["confidence"], 3), ev))
                    self.audit.join_details = [d for d in self.audit.join_details if not (d["join"] == j.name and d["left_row"] == rec.source_row and d["issue"] == "J2-ORPHAN")]
                    self.audit.join_details.append({"join": j.name, "step": "+".join(st.right), "left_row": rec.source_row, "key": r.values.get(rk),
                                                    "issue": "llm:entity", "detail": f"{key!r} -> {r.values.get(rk)!r}: {ev}"})
                    self.audit.review = [x for x in self.audit.review if not (x.table == j.left and x.source_row == rec.source_row and x.column == lk and x.flag == "J2-ORPHAN")]
                cols += [st.prefix + c for c in rcols] + ([st.prefix + rk] if st.fallback or counts["llm"] else []) + [status_col]
                total = len(rows)
                dup_right = sum(1 for k, v in idx.items() if len(v) > 1)
                matched = counts["exact"] + counts["fallback"] + counts["llm"]
                self.audit.joins.append({
                    "join": j.name, "left": j.left, "right": "+".join(st.right), "on": f"{lk} = {rk}", "expect": st.expect,
                    "left_rows": total, "matched": matched, "match_rate": round(matched / total, 4) if total else 0,
                    "matched_exact": counts["exact"], "matched_fallback": counts["fallback"], "matched_llm": counts["llm"],
                    "rules_only_match_rate": round(rules_matched / total, 4) if total else 0,
                    "orphans": counts["orphan"], "ambiguous": counts["ambiguous"], "blank_keys": counts["blank"],
                    "right_dup_keys": dup_right, "raw_key_match_rate": round(raw_hits / total, 4) if total else 0,
                    "rows_out": total, "row_multiplication": "none (ambiguous keys left unjoined)",
                    "notes": "; ".join(f"{v} matched {k}" for k, v in counts.items() if k.startswith("in ")),
                })
            self.joined[j.name] = (list(dict.fromkeys(cols)), rows)

    # ------------------------------------------------------------ reconciliation and self-checks
    def reconcile(self) -> None:
        for tname, subs in self.subtotals.items():
            t = self.c.tables[tname]
            kept = {r.source_row: r for r in self.tables[tname]}
            dups = {r.source_row: r for r in self.dup_dropped[tname]}
            for s in subs:
                lo = 0 if s["grand"] or s["after"] is None else s["after"]
                for cname, raw in s["cells"].items():
                    col = t.columns[cname]
                    if col.type not in ("money", "number", "count") or N.is_blank(raw):
                        continue
                    stated = N.parse_number(N.normalize_text(raw).value).value
                    if not isinstance(stated, (int, float)):
                        continue
                    inscope = lambda rows: [r for row_no, r in rows.items() if lo < row_no < s["row"]]  # noqa: E731
                    vals = [r.values.get(cname) for r in inscope(kept)]
                    total = sum(v for v in vals if isinstance(v, (int, float)))
                    dsum = sum(r.values.get(cname) for r in inscope(dups) if isinstance(r.values.get(cname), (int, float)))
                    missing = [r.source_row for r in inscope(kept) if not isinstance(r.values.get(cname), (int, float))]
                    diff = stated - total
                    if diff == 0:
                        expl = "matches"
                    elif diff == dsum:
                        expl = "difference = dropped duplicate rows"
                    else:
                        rest = diff - dsum
                        expl = (f"{dsum:,} from dropped duplicates; " if dsum else "") + f"{rest:,} unexplained" + (
                            f": {cname} is blank/unparsed on row(s) {', '.join(map(str, missing))}, likely the missing value" if missing else "")
                    self.audit.reconcile.append({"table": tname, "subtotal_row": s["row"], "label": s["label"], "column": cname,
                                                 "scope": f"rows {lo + 1}-{s['row'] - 1}" if lo else f"rows up to {s['row'] - 1}",
                                                 "stated": stated, "cleaned_sum": total, "dropped_duplicates_sum": dsum,
                                                 "difference": diff, "explanation": expl})

    def self_check(self) -> list[dict]:
        out = []
        for tname in self.c.tables:
            n_drop = sum(1 for d in self.audit.dropped if d.table == tname)
            ok = self.stats[tname]["rows_in"] == len(self.tables[tname]) + n_drop
            out.append({"check": f"{tname}: rows in = rows out + dropped", "ok": ok,
                        "detail": f"{self.stats[tname]['rows_in']} = {len(self.tables[tname])} + {n_drop}"})
            chains = defaultdict(list)
            for ch in self.audit.changes:
                if ch.table == tname:
                    chains[(ch.source_row, ch.column)].append(ch)
            bad, unlogged, blanked = 0, 0, 0
            for r in self.raw_tables[tname]:
                for c in self.c.tables[tname].columns:
                    ch = chains.get((r.source_row, c), [])
                    raw, fin = r.raw.get(c), r.values.get(c)
                    if ch:
                        links = all(same(a.after, b.before) for a, b in zip(ch, ch[1:]))
                        if not (links and same(ch[-1].after, fin) and (same(ch[0].before, raw) or ch[0].rule in ("S2-MERGE", "S3-SHIFT") or raw is None)):
                            bad += 1
                        if not N.is_blank(raw) and N.is_blank(fin) and not any(x.rule in ("M1-PLACEHOLDER", "S3-SHIFT") for x in ch):
                            blanked += 1
                    elif not same(raw, fin):
                        unlogged += 1
            out.append({"check": f"{tname}: every changed cell has a consistent change chain", "ok": bad == 0 and unlogged == 0,
                        "detail": f"{bad} broken chains, {unlogged} unlogged changes"})
            out.append({"check": f"{tname}: no value became blank except placeholders", "ok": blanked == 0, "detail": f"{blanked} cells"})
            viol0 = self.violations(self.c.tables[tname], self.raw_tables[tname], use_raw=True)
            viol1 = self.violations(self.c.tables[tname], self.tables[tname])
            for c in self.c.tables[tname].columns:
                self.audit.checks.append({"table": tname, "column": c, "type": self.c.tables[tname].columns[c].type,
                                          "violations_before": viol0[c], "violations_after": viol1[c],
                                          "rows": len(self.tables[tname])})
            t = self.c.tables[tname]
            if t.key:
                keys = [r.values.get(t.key) for r in self.tables[tname] if not N.is_blank(r.values.get(t.key))]
                self.audit.checks.append({"table": tname, "column": f"{t.key} (unique)", "type": "key",
                                          "violations_before": len(self.raw_tables[tname]) - len({repr(r.raw.get(t.key)) for r in self.raw_tables[tname]}),
                                          "violations_after": len(keys) - len(set(keys)), "rows": len(self.tables[tname])})
        return out

    def run(self) -> dict:
        for t in self.c.tables.values():
            self.clean_table(t)
        with self.timed("joins"):
            self.run_joins()
        with self.timed("reconcile"):
            self.reconcile()
        with self.timed("self_check"):
            checks = self.self_check()
        return {"self_check": checks}



def show_row(row: list) -> str:
    """' | '-joined raw row, built only for rows that end up in Dropped."""
    return " | ".join("" if v is None else str(v) for v in row).strip(" |")


def rss_mb() -> float:
    try:
        with open("/proc/self/statm") as f:
            return int(f.read().split()[1]) * resource.getpagesize() / 2 ** 20
    except OSError:
        return 0.0


def same(a: Any, b: Any) -> bool:
    """Equal up to representation: 00:00 datetime == date, 45000.0 == 45000, '' == blank."""
    if isinstance(a, dt.datetime) and a.time() == dt.time(0):
        a = a.date()
    if isinstance(b, dt.datetime) and b.time() == dt.time(0):
        b = b.date()
    if a == "" or b == "":
        a, b = (None if a == "" else a), (None if b == "" else b)
    if isinstance(a, float) and isinstance(b, (int, float)) and not isinstance(b, bool):
        return a == b
    return repr(a) == repr(b)


def is_row_index(vals: list[Any]) -> bool:
    """True for a 'No.' column: integers that step by exactly 1 down the rows."""
    nums = [v for v in vals if not N.is_blank(v)]
    if len(nums) < 3 or not all(isinstance(v, int) or (isinstance(v, str) and v.isdigit()) for v in nums):
        return False
    ints = [int(v) for v in nums]
    return all(b - a == 1 for a, b in zip(ints, ints[1:]))
