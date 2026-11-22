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


def read_csv(path: Path) -> list[Grid]:
    data = path.read_bytes()
    enc = detect_encoding(data)
    text = data.decode(enc)
    sample = "\n".join(text.splitlines()[:30])
    try:
        delim = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        delim = ","
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
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=True)  # values, not formulas
    grids = []
    for ws in wb.worksheets:
        cells, fmts = [], {}
        for r, row in enumerate(ws.iter_rows(min_row=1, max_row=ws.max_row, max_col=ws.max_column)):
            out = []
            for c, cell in enumerate(row):
                out.append(cell.value)
                if cell.value is not None and cell.number_format != "General":
                    fmts[(r, c)] = cell.number_format
            cells.append(out)
        merges = [(m.min_row - 1, m.min_col - 1, m.max_row - 1, m.max_col - 1) for m in ws.merged_cells.ranges]
        g = Grid(source=path.name, sheet=ws.title, cells=cells, merges=sorted(merges), number_formats=fmts)
        g.hidden = ws.sheet_state != "visible"  # type: ignore[attr-defined]
        grids.append(g)
    return grids


def read_any(path: Path) -> list[Grid]:
    suffix = path.suffix.lower()
    if suffix in (".xlsx", ".xlsm"):
        return read_xlsx(path)
    if suffix in (".csv", ".tsv", ".txt"):
        return read_csv(path)
    raise SystemExit(f"unsupported file type: {path}")
