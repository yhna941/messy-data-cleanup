"""Find the real table inside a sheet: merged cells, header rows, blocks, row kinds, shifted rows."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable

from .match import fold
from .model import Grid, RowKind
from .normalize import is_blank

SUBTOTAL_RE = re.compile(r"(소\s*계|합\s*계|총\s*계|누\s*계|^계$|sub\s*total|grand\s*total|^total|summe|^평\s*균$|^average$|^avg\.?$|^mean$|^최대$|^최소$|^max$|^min$)", re.I)
SUM_RE = re.compile(r"(소\s*계|합\s*계|총\s*계|누\s*계|^계$|total|summe)", re.I)   # aggregates that are sums (reconcilable)
GRAND_RE = re.compile(r"(합\s*계|총\s*계|grand|^total$)", re.I)
NOTE_RE = re.compile(r"^\s*(※|\*|#|주\)|참고|비고\s*:|note)", re.I)


def fill_merges(g: Grid) -> tuple[list[list[Any]], dict[tuple[int, int], tuple[int, int]]]:
    """Copy each merged range's top-left value into every cell. Returns cells and {filled cell: origin}."""
    cells = [list(r) for r in g.cells]
    origin: dict[tuple[int, int], tuple[int, int]] = {}
    for r1, c1, r2, c2 in g.merges:
        v = cells[r1][c1]
        for r in range(r1, r2 + 1):
            for c in range(c1, c2 + 1):
                if (r, c) != (r1, c1):
                    cells[r][c] = v
                    origin[(r, c)] = (r1, c1)
    return cells, origin


@dataclass
class Header:
    start: int                    # 0-based first header row
    depth: int                    # 1 or 2 rows
    mapping: dict[str, int]       # contract column -> grid column
    labels: dict[int, str]        # grid column -> combined label
    extras: dict[int, str]        # labelled grid columns not in the contract


def _labels(cells: list[list[Any]], r: int, depth: int) -> dict[int, list[str]]:
    width = max(len(x) for x in cells)
    out: dict[int, list[str]] = {}
    for c in range(width):
        parent = cells[r][c] if c < len(cells[r]) else None
        if depth == 1:
            cands = [parent]
        else:
            child = cells[r + 1][c] if r + 1 < len(cells) and c < len(cells[r + 1]) else None
            cands = [child, f"{parent or ''}{child or ''}", parent] if child != parent else [parent]
        out[c] = [str(x) for x in cands if not is_blank(x)]
    return out


def _match(labels: dict[int, list[str]], aliases: dict[str, list[str]]) -> dict[str, int]:
    folded = {col: {fold(a) for a in al} for col, al in aliases.items()}
    mapping: dict[str, int] = {}
    for c, cands in labels.items():
        for cand in cands:
            hit = next((col for col, al in folded.items() if col not in mapping and fold(cand) in al), None)
            if hit:
                mapping[hit] = c
                break
    return mapping


def find_headers(cells: list[list[Any]], aliases: dict[str, list[str]], min_share: float = 0.6) -> list[Header]:
    """Every row (or row pair) whose labels cover >= min_share of the contract columns."""
    need = max(2, int(len(aliases) * min_share + 0.999))
    found: list[Header] = []
    def try_at(r: int, depth: int) -> Header | None:
        if r + depth > len(cells):
            return None
        labs = _labels(cells, r, depth)
        mp = _match(labs, aliases)
        # [child, parent+child, parent] -> "parent child"; single label otherwise
        joined = {c: f"{v[2]} {v[0]}" if len(v) == 3 else v[0] for c, v in labs.items() if v}
        return Header(r, depth, mp, joined, {c: joined[c] for c in joined if c not in mp.values()})

    r = 0
    while r < len(cells):
        one, two, nxt = try_at(r, 1), try_at(r, 2), try_at(r + 1, 1)
        n1, n2, nn = (len(h.mapping) if h else 0 for h in (one, two, nxt))
        # a 2-row header must beat both of its rows read alone (else it is a title row + a header)
        best = two if n2 > max(n1, nn) and n2 >= need else one if n1 >= need else None
        if best:
            found.append(best)
            r += best.depth
        else:
            r += 1
    return found


def is_blank_row(row: list[Any]) -> bool:
    return all(is_blank(v) for v in row)


def block_starts(cells: list[list[Any]], headers: list[Header]) -> list[Header]:
    """A header starts a new table block if it is the first one or a blank row sits within 2 rows above it."""
    out = []
    for i, h in enumerate(headers):
        above = cells[max(0, h.start - 2):h.start]
        if i == 0 or any(is_blank_row(r) for r in above):
            out.append(h)
    return out


def classify(row: list[Any], header_labels: set[str], key_ok: Callable[[Any], bool], key_value: Any) -> RowKind:
    nonblank = [v for v in row if not is_blank(v)]
    if not nonblank:
        return RowKind.BLANK
    texts = [fold(v) for v in nonblank if isinstance(v, str)]
    if len(nonblank) >= 2 and sum(t in header_labels for t in texts) >= 0.6 * len(nonblank):
        return RowKind.REPEATED_HEADER
    if key_ok(key_value):
        return RowKind.DATA
    if any(isinstance(v, str) and SUBTOTAL_RE.search(v.strip()) for v in nonblank):
        return RowKind.SUBTOTAL
    if len(nonblank) == 1 or (isinstance(nonblank[0], str) and NOTE_RE.match(nonblank[0])):
        return RowKind.NOTE
    return RowKind.DATA


def best_shift(row: list[Any], fits: list[Callable[[Any], bool | None]]) -> tuple[list[Any], str, int, int] | None:
    """Try moving the tail of a row left/right by 1-2 cells; return (row, how, before, after) if clearly better.

    Only removes blank cells (never data) and only inserts blanks. fits[i] says whether a value suits
    column i (None = no opinion, e.g. free text). Cells beyond the last column are violations.
    """
    n = len(fits)

    def score(r: list[Any]) -> int:
        bad = sum(1 for i, v in enumerate(r[:n]) if not is_blank(v) and fits[i](v) is False)
        return bad + sum(1 for v in r[n:] if not is_blank(v))

    base = score(row)
    if base < 2:
        return None
    best = None
    for k in (1, -1, 2, -2):
        for s in range(n):
            if k > 0:
                if not all(is_blank(v) for v in row[s:s + k]):
                    continue
                cand = row[:s] + row[s + k:] + [None] * k
            else:
                cand = row[:s] + [None] * (-k) + row[s:]
            sc = score(cand)
            if best is None or sc < best[3]:
                best = (cand, f"shift {'left' if k > 0 else 'right'} by {abs(k)} from column #{s + 1}", base, sc)
    if best and best[3] <= 1 and base - best[3] >= 2:
        return best
    return None
