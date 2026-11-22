"""Boundary: read files into Grids without changing a single value."""
from __future__ import annotations

import csv
import io
from pathlib import Path

from .model import Grid

ENCODINGS = ("utf-8-sig", "cp949", "euc-kr", "cp1252")


def detect_encoding(data: bytes) -> str:
    for enc in ENCODINGS:
        try:
            data.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    try:
        from charset_normalizer import from_bytes
        best = from_bytes(data).best()
        if best:
            return best.encoding
    except ImportError:
        pass
    return "latin-1"


def sniff_delimiter(sample: str) -> str:
    """csv.Sniffer, checked: free text full of commas fools it on tab/semicolon files (the Powerhouse TSV
    sniffs as ','). Prefer the candidate that splits the most sample lines into the header's width."""
    try:
        sniffed = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        sniffed = ","

    def fit(d: str) -> float:
        widths = [len(r) for r in csv.reader(io.StringIO(sample), delimiter=d)]
        if len(widths) < 2 or widths[0] < 2:
            return 0.0
        return sum(w == widths[0] for w in widths[1:]) / (len(widths) - 1)

    best = max(",;\t|", key=lambda d: (fit(d), d == sniffed))
    return best if fit(best) > fit(sniffed) else sniffed


def read_csv(path: Path) -> list[Grid]:
    data = path.read_bytes()
    enc = detect_encoding(data)
    text = data.decode(enc)
    delim = "\t" if path.suffix.lower() == ".tsv" else sniff_delimiter("\n".join(text.splitlines()[:30]))
    del data
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    del text
    rows, starts, line = [], [], 1
    # Repeated values ('Closed', 'NYPD', '11201') share one string object: on a 1M-row file this is
    # the difference between ~14M and a few hundred thousand string objects. Values are unchanged.
    pool: dict[str, str] = {"": None}  # type: ignore[dict-item]
    for rec in reader:
        rows.append([pool.setdefault(v, v) for v in rec])
        starts.append(line)
        line = reader.line_num + 1   # next record starts after the physical lines consumed so far
    width = max((len(r) for r in rows), default=0)
    for r in rows:
        if len(r) < width:
            r.extend([None] * (width - len(r)))
    return [Grid(source=path.name, sheet="", cells=rows, encoding=enc, row_numbers=starts)]


def read_xlsx(path: Path) -> list[Grid]:
    """Values (not formulas), number formats and merges, streamed: openpyxl's read-only mode keeps one row
    of cell objects alive instead of the whole workbook (the full model needs ~1 KB per cell, so a 14 MB
    workbook with 3.6M cells did not fit in 2 GB). Merges are not exposed in read-only mode, so they are
    read straight from each sheet's XML."""
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    grids = []
    try:
        for ws in wb.worksheets:
            merges = sorted(xlsx_merges(wb, ws))
            cells, fmts, width = [], {}, 0
            for r, row in enumerate(ws.iter_rows()):
                out = []
                for c, cell in enumerate(row):
                    v = getattr(cell, "value", None)
                    out.append(v)
                    if v is not None and cell.number_format != "General":
                        fmts[(r, c)] = cell.number_format
                cells.append(out)
                width = max(width, len(out))
            # the full-model reader returned a rectangle reaching the last merge too; keep that shape
            height = max([len(cells)] + [m[2] + 1 for m in merges])
            width = max([width] + [m[3] + 1 for m in merges])
            cells += [[] for _ in range(height - len(cells))]
            for out in cells:
                out.extend([None] * (width - len(out)))
            g = Grid(source=path.name, sheet=ws.title, cells=cells, merges=merges, number_formats=fmts)
            g.hidden = ws.sheet_state != "visible"  # type: ignore[attr-defined]
            grids.append(g)
    finally:
        wb.close()
    return grids


def xlsx_merges(wb, ws) -> list[tuple[int, int, int, int]]:
    from xml.etree.ElementTree import iterparse
    from openpyxl.utils.cell import range_boundaries
    out = []
    with wb._archive.open(ws._worksheet_path) as f:  # noqa: SLF001 - read-only sheets do not parse mergeCells
        for _, el in iterparse(f):
            if el.tag.endswith("}mergeCell"):
                c1, r1, c2, r2 = range_boundaries(el.get("ref"))
                out.append((r1 - 1, c1 - 1, r2 - 1, c2 - 1))
            elif el.tag.endswith("}row") or el.tag.endswith("}c"):
                el.clear()
    return out


def read_any(path: Path) -> list[Grid]:
    suffix = path.suffix.lower()
    if suffix in (".xlsx", ".xlsm"):
        return read_xlsx(path)
    if suffix in (".csv", ".tsv", ".txt"):
        return read_csv(path)
    raise SystemExit(f"unsupported file type: {path}")
