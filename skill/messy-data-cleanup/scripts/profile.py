#!/usr/bin/env python3
"""Profile messy xlsx/csv files with no contract, and draft one.

usage: profile.py FILE [FILE ...] [--out profile.md] [--draft contract.draft.yaml] [--llm off|cache|live]

--llm adds an LLM layout read per sheet (tables, header rows, data rows, column names/types), validated
against the grid; valid reads go into the draft as `llm_layout` hints. Data is never changed here.

Per sheet: encoding, merged ranges, likely header row(s), title/subtotal/note/repeated-header rows,
and per column: guessed type, blanks, placeholders, full-width/mojibake/whitespace counts,
parse failures, top values, and fuzzy clusters of near-identical category values.
Read the profile, then edit the draft contract (types, vocab, synonyms, keys) before cleaning.
"""
from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml  # noqa: E402

from cleankit import normalize as N  # noqa: E402
from cleankit.io_read import read_any  # noqa: E402
from cleankit.match import _jf, similarity  # noqa: E402
from cleankit.structure import NOTE_RE, SUBTOTAL_RE, fill_merges  # noqa: E402


def guess_header(cells, merges=()) -> tuple[int, int]:
    """Row (0-based) with the most short text labels in the first 30 rows; depth 2 if the row above holds merged parents."""
    best, best_n = 0, -1
    for r, row in enumerate(cells[:30]):
        n = len({v.strip() for v in row if isinstance(v, str) and 0 < len(v.strip()) <= 20 and not re.search(r"\d{3,}", v)})
        if n > best_n:   # distinct labels, so a merged title filled across the row does not win
            best, best_n = r, n
    depth = 1
    if best + 1 < len(cells):
        nxt = cells[best + 1]
        n2 = sum(1 for v in nxt if isinstance(v, str) and 0 < len(v.strip()) <= 20 and not re.search(r"\d{3,}", v))
        differs = sum(1 for a, b in zip(cells[best], nxt) if isinstance(b, str) and a != b)
        spans = any(r1 == best and c2 > c1 for r1, c1, r2, c2 in merges)
        if spans and n2 >= 0.5 * best_n and differs >= 2:
            depth = 2   # merged parent labels on top, child labels below
    return best, depth


def guess_type(vals: list) -> str:
    vals = [v for v in vals if not N.is_blank(v) and not (isinstance(v, str) and v.strip().casefold() in N.PLACEHOLDERS)]
    if not vals:
        return "text"
    s = [N.normalize_text(v).value for v in vals]
    share = lambda f: sum(1 for v in s if f(v)) / len(s)  # noqa: E731
    if share(lambda v: isinstance(v, str) and "@" in v) > 0.6:
        return "email"
    # digit strings with leading zeros (zip 06164, industry 000000) are codes: a number type would drop the zeros
    if share(lambda v: isinstance(v, str) and v.strip().isdigit()) > 0.9 and share(lambda v: isinstance(v, str) and N.LEADING_ZERO.fullmatch(v.strip())) > 0.01:
        return "code"
    # a phone has a leading 0 / +82 or separators; bare 10-digit integers are codes (법정동코드 1165010800)
    if share(lambda v: len(re.sub(r"\D", "", str(v))) in (10, 11) and str(re.sub(r"\D", "", str(v))).lstrip("0").startswith(("1", "2", "3", "4", "5", "6"))
             and len(re.sub(r"[\d\s\-.+–()]", "", str(v))) == 0
             and (str(v).strip().startswith(("0", "+")) or not re.fullmatch(r"\d+", str(v).strip()))) > 0.6:
        return "phone"
    if share(lambda v: bool(N.date_candidates(v, 2000)[0]) and not (isinstance(v, (int, float)) and v < 20000)) > 0.6:
        return "date"
    if share(lambda v: isinstance(v, str) and re.fullmatch(r"[A-Za-z]{0,3}[-_ ]?\d{1,8}([-_]\d{1,8})?", v.strip()) is not None and not v.strip().isdigit()) > 0.6:
        return "id"
    if share(lambda v: isinstance(v, str) and v.strip().endswith("%")) > 0.2:
        return "percent"
    if share(lambda v: N.parse_number(v).flag is None and isinstance(N.parse_number(v).value, (int, float))) > 0.7:
        return "money" if share(lambda v: isinstance(v, str) and re.search(r"[₩원,]|천|만", v)) > 0.2 else "number"
    from cleankit.match import BUILTIN_VOCAB, Vocab
    regions = Vocab(BUILTIN_VOCAB["ko_region"])
    if share(lambda v: regions.match(v).flag is None) > 0.6:
        return "category:ko_region"
    distinct = {str(v) for v in s}
    if len(distinct) <= max(12, len(s) * 0.5):
        return "category"
    return "text"


CLUSTER_TOP = 400   # near-duplicate spellings are searched among the most frequent distinct values only


def clusters(values: Counter) -> list[list[str]]:
    """Groups of near-identical spellings among the CLUSTER_TOP most frequent values (pairwise is O(k^2)).

    Same test as before (similarity >= 0.7), with two exact upper bounds checked first: the length
    bound 2*min/(la+lb) and the shared-character bound (difflib's quick_ratio).
    """
    top = set([k for k, _ in values.most_common() if isinstance(k, str)][:CLUSTER_TOP])
    keys = [k for k in values if k in top]          # first-seen order (group member order)
    jf = {k: _jf(k) for k in keys}
    bag = {k: Counter(v) for k, v in jf.items()}
    seen, out = set(), []
    for k in sorted(keys, key=lambda x: -values[x]):   # most frequent first (group leaders)
        if k in seen:
            continue
        grp = [k]
        for o in keys:
            if o == k or o in seen:
                continue
            la, lb = len(jf[k]), len(jf[o])
            if la + lb == 0 or 2 * min(la, lb) / (la + lb) < 0.7:
                continue
            if 2 * sum((bag[k] & bag[o]).values()) / (la + lb) < 0.7:
                continue
            if similarity(k, o) >= 0.7:
                grp.append(o)
        seen.update(grp)
        if len(grp) > 1:
            out.append(grp)
    return out


def profile_grid(g, md: list[str], draft: dict) -> None:
    cells, origin = fill_merges(g)
    name = g.sheet or Path(g.source).stem
    md.append(f"## {g.source} / {name}\n")
    md.append(f"- size: {len(cells)} rows x {max((len(r) for r in cells), default=0)} cols; encoding: {g.encoding or 'xlsx'}; merged ranges: {len(g.merges)}")
    h, depth = guess_header(cells, g.merges)
    labels = []
    for c in range(max(len(r) for r in cells)):
        parts = [cells[r][c] for r in range(h, h + depth) if c < len(cells[r]) and not N.is_blank(cells[r][c])]
        labels.append(" ".join(dict.fromkeys(str(p) for p in parts)) or f"column_{c + 1}")
    md.append(f"- likely header: row {h + 1}" + (f"-{h + depth} (2-row header with merged parents)" if depth == 2 else ""))
    kinds = Counter()
    odd = []
    hdr_set = {str(x).strip() for x in labels}
    for r in range(h + depth, len(cells)):
        row = cells[r]
        nb = [v for v in row if not N.is_blank(v)]
        if not nb:
            kinds["blank"] += 1
        elif sum(isinstance(v, str) and v.strip() in hdr_set for v in nb) >= 0.6 * len(nb) and len(nb) > 1:
            kinds["repeated header"] += 1
            odd.append((r + 1, "repeated header"))
        elif any(isinstance(v, str) and SUBTOTAL_RE.search(v.strip()) for v in nb):
            kinds["subtotal/total"] += 1
            odd.append((r + 1, f"subtotal: {nb[0]}"))
        elif len(nb) == 1 or (isinstance(nb[0], str) and NOTE_RE.match(nb[0])):
            kinds["note/title"] += 1
            odd.append((r + 1, f"note: {str(nb[0])[:40]}"))
        else:
            kinds["data"] += 1
            width = len([x for x in labels if not x.startswith("column_")])
            if any(not N.is_blank(v) for v in row[width:]):
                odd.append((r + 1, "values right of the last header column (shifted row?)"))
    md.append(f"- rows below header: {dict(kinds)}")
    if odd:
        md.append("- structural rows: " + "; ".join(f"row {r}: {w}" for r, w in odd[:20]))
    md.append("\n| column | guess | blanks | placeholders | full-width | mojibake | spaces | top values | near-duplicate spellings |")
    md.append("|---|---|---|---|---|---|---|---|---|")
    tcols = {}
    data_rows = [cells[r] for r in range(h + depth, len(cells))]
    for c, lab in enumerate(labels):
        vals = [row[c] if c < len(row) else None for row in data_rows]
        if all(N.is_blank(v) for v in vals) and lab.startswith("column_"):
            continue
        typ = guess_type(vals)
        strs = [v for v in vals if isinstance(v, str)]
        ph = sum(1 for v in strs if v.strip().casefold() in N.PLACEHOLDERS)
        fwc = sum(1 for v in strs if N.nfkc(v) != v)
        moj = sum(1 for v in strs if N.repair_mojibake(v))
        sp = sum(1 for v in strs if v != v.strip() or "  " in v or "\u200b" in v)
        cnt = Counter(N.normalize_text(v).value for v in vals if not N.is_blank(v))
        top = ", ".join(f"{k!s}×{n}" for k, n in cnt.most_common(5))[:120]
        cl = clusters(cnt) if typ in ("category", "text") else []
        md.append(f"| {lab} | {typ} | {sum(N.is_blank(v) for v in vals)} | {ph} | {fwc} | {moj} | {sp} | {top} | "
                  + "; ".join("/".join(g_) for g_ in cl[:4])[:160] + " |")
        key = re.sub(r"\W+", "_", lab).strip("_").lower() or f"col{c + 1}"
        spec = {"type": typ, "aliases": [lab.replace(" ", "")]}
        if typ == "category:ko_region":
            spec = {"type": "category", "aliases": spec["aliases"], "vocab_builtin": "ko_region"}
        elif typ == "category":
            spec["vocab"] = {k: [] for k, _ in cnt.most_common(12) if isinstance(k, str)}
        if typ == "code":
            spec = {"type": "text", "aliases": spec["aliases"]}   # keeps leading zeros; use id + '{n:0Nd}' for fixed-width codes
        if typ == "id":
            spec.update({"regex": r"(?i)[a-z]{0,3}[-_ ]?0*(?P<n>\d{1,8})", "format": "X{n:04d}"})
        tcols[key] = spec
    draft["tables"][re.sub(r"\W+", "_", name).strip("_").lower() or "table"] = {
        "file": g.source, "sheet": g.sheet, "key": next(iter(tcols), None), "columns": tcols}
    md.append("")


LAYOUT_INSTR = (
    "DATA is a preview of one spreadsheet sheet: each row is [row_number, cell1, cell2, ...] (1-based, blank cells are ''). "
    "Find every table in it. For each table give: header_rows (row numbers of its header, 1 or 2 rows), first_data_row, "
    "last_data_row (data rows only: not titles, notes, subtotals or blank rows at the end), a short snake_case name, and its columns "
    "(header = the header text exactly as in the cells, joined with a space for 2-row headers; name = snake_case English; type). "
    "evidence_quote = copy one header cell exactly."
)


def llm_layout(llm, g, cells) -> tuple[list[dict], list[str]]:
    from cleankit.llm import LAYOUT_SCHEMA, quoted, squash
    n = len(cells)
    prev = [[r + 1] + [("" if N.is_blank(v) else str(v)[:25]) for v in row[:14]] for r, row in enumerate(cells[:60])]
    ans = llm.ask("layout", LAYOUT_INSTR, {"sheet": g.sheet or Path(g.source).stem, "rows": prev}, LAYOUT_SCHEMA)
    ok, bad = [], []
    for t in (ans or {}).get("tables", []):
        hr = sorted(t["header_rows"])
        hdr_text = " ".join(squash(c) for r in hr if 1 <= r <= n for c in cells[r - 1] if not N.is_blank(c))
        why = None
        if not hr or hr[0] < 1 or hr[-1] > n or hr != list(range(hr[0], hr[-1] + 1)) or len(hr) > 2:
            why = f"header rows {hr} are not 1-2 consecutive rows of the sheet"
        elif not (hr[-1] < t["first_data_row"] <= t["last_data_row"] <= n):
            why = f"data rows {t['first_data_row']}..{t['last_data_row']} do not follow the header inside the sheet"
        elif not quoted(t["evidence_quote"], hdr_text):
            why = "evidence is not a header cell"
        else:
            missing = [c["header"] for c in t["columns"] if not all(w in hdr_text for w in squash(c["header"]).split())]
            if missing:
                why = f"column headers not found in the header rows: {missing[:3]}"
        (bad if why else ok).append({**t, **({"rejected": why} if why else {})})
    return ok, bad


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--draft", type=Path)
    ap.add_argument("--llm", choices=["off", "cache", "live"], default="off")
    ap.add_argument("--llm-provider", default="auto")
    ap.add_argument("--llm-model")
    ap.add_argument("--llm-cache", type=Path)
    a = ap.parse_args()
    from cleankit.llm import LLM
    llm = LLM(a.llm, a.llm_provider, a.llm_model, a.llm_cache or (a.files[0].parent.parent / "llm_cache"))
    md = ["# Profile (no contract; guesses to review)\n"]
    draft = {"dataset": "draft", "tables": {}}
    for f in a.files:
        for g in read_any(f):
            if g.cells:
                profile_grid(g, md, draft)
                if llm.on:
                    cells, _ = fill_merges(g)
                    ok, bad = llm_layout(llm, g, cells)
                    md.append(f"### LLM layout read ({llm.label}), validated against the grid\n")
                    for t in ok:
                        md.append(f"- table `{t['name']}`: header row(s) {t['header_rows']}, data rows {t['first_data_row']}-{t['last_data_row']}, "
                                  f"columns: " + ", ".join(f"{c['header']}→{c['name']}:{c['type']}" for c in t["columns"]))
                        draft.setdefault("llm_layout", []).append({"file": g.source, "sheet": g.sheet, "name": t["name"], "header_rows": t["header_rows"],
                                                                   "data_rows": [t["first_data_row"], t["last_data_row"]],
                                                                   "columns": {c["name"]: {"type": c["type"], "aliases": [c["header"]]} for c in t["columns"]}})
                    for t in bad:
                        md.append(f"- rejected read `{t['name']}`: {t['rejected']}")
                    md.append("")
    text = "\n".join(md)
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(text, encoding="utf-8")
    else:
        print(text)
    if a.draft:
        a.draft.write_text("# DRAFT: fix types, keys, id regex/format, vocab canonicals and synonyms before use\n"
                           + yaml.safe_dump(draft, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
