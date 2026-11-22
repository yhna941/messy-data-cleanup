"""Core data shapes. Everything else is pure functions over these."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RowKind(str, Enum):
    TITLE = "title"            # text above the header
    HEADER = "header"
    REPEATED_HEADER = "repeated_header"
    SUBTOTAL = "subtotal"      # 소계/합계/Total rows
    NOTE = "note"              # ※ comments, single free-text cells
    BLANK = "blank"
    DATA = "data"


@dataclass
class Grid:
    """One sheet (or one CSV) exactly as read. rows are 1-based in spreadsheet terms."""
    source: str                     # file name
    sheet: str                      # sheet name ("" for csv)
    cells: list[list[Any]]          # cells[r][c], 0-based storage
    merges: list[tuple[int, int, int, int]] = field(default_factory=list)  # (r1,c1,r2,c2) 0-based inclusive
    encoding: str | None = None
    number_formats: dict[tuple[int, int], str] = field(default_factory=dict)
    row_numbers: list[int] | None = None   # CSV: physical line where each record starts (multi-line fields)

    def row_no(self, r: int) -> int:
        return self.row_numbers[r] if self.row_numbers else r + 1


@dataclass
class Record:
    """One data row of a table. values keyed by contract column name."""
    table: str
    source_row: int                 # 1-based row number as the spreadsheet/CSV shows it
    values: dict[str, Any]
    raw: dict[str, Any]             # values as they were mapped from the grid (before any fix)


@dataclass
class Change:
    table: str
    sheet: str
    source_row: int
    column: str
    before: Any
    after: Any
    rule: str
    confidence: float
    evidence: str


@dataclass
class Dropped:
    table: str
    sheet: str
    source_row: int
    kind: str
    reason: str
    evidence: str
    raw_values: str


@dataclass
class Review:
    table: str
    sheet: str
    source_row: int
    column: str
    value: Any
    flag: str
    suggestion: str
    question: str


@dataclass
class DupGroup:
    group: str
    table: str
    kind: str               # exact | suspected
    rows: list[int]
    kept: int | None
    similarity: float
    evidence: str


@dataclass
class Audit:
    changes: list[Change] = field(default_factory=list)
    dropped: list[Dropped] = field(default_factory=list)
    review: list[Review] = field(default_factory=list)
    dups: list[DupGroup] = field(default_factory=list)
    joins: list[dict] = field(default_factory=list)       # join report rows
    join_details: list[dict] = field(default_factory=list)
    checks: list[dict] = field(default_factory=list)      # contract check before/after
    reconcile: list[dict] = field(default_factory=list)   # subtotal reconciliation
    notes: list[str] = field(default_factory=list)


# Rule registry: id -> (stage, description). The Rules sheet is generated from this,
# so every rule id used in the log must exist here (enforced in pipeline).
RULES: dict[str, tuple[str, str]] = {
    "S1-TITLE": ("structure", "Title/caption rows above the header are dropped (kept in Dropped rows)."),
    "S1-HEADER2": ("structure", "Multi-row header: parent (merged) label + child label combined, then matched to contract aliases."),
    "S1-REPHEADER": ("structure", "Header row repeated inside the data block is dropped."),
    "S1-SUBTOTAL": ("structure", "소계/합계/Total rows are dropped and reconciled against the cleaned sum."),
    "S1-NOTE": ("structure", "Note rows (※, single free-text cell without a valid key) are dropped."),
    "S1-BLANK": ("structure", "Completely empty rows are dropped."),
    "S2-MERGE": ("structure", "Merged cell value is filled into every cell of its range."),
    "S3-SHIFT": ("structure", "Row whose values sit k columns off is shifted back when that removes the type violations."),
    "T1-WS": ("text", "Trim, collapse repeated spaces, remove zero-width/control chars, NBSP -> space."),
    "T1-NFKC": ("text", "Unicode NFKC: full-width digits/letters/punctuation -> half-width (２０２４ -> 2024)."),
    "T1-MOJIBAKE": ("text", "Garbled text repaired by re-decoding (UTF-8 read as cp1252/latin-1, or as cp949)."),
    "M1-PLACEHOLDER": ("blanks", "Placeholders (-, N/A, 없음, 미입력, #N/A, null, ?) become blank. Blanks are never filled."),
    "N1-NUMBER": ("types", "Text numbers -> numbers: ₩/원/,/spaces removed, (1,200) -> -1200, decimal comma decided per column."),
    "N1-KUNIT": ("types", "Korean magnitude units written in the value are applied: 천원 x1,000, 만원 x10,000, 4만5천 = 45,000."),
    "N1-KCOUNT": ("types", "Native Korean counts: 한개/두개/세 개 -> 1/2/3; 3개, 2EA -> 3, 2."),
    "N1-PERCENT": ("types", "'10%' -> 10 in a percent (0-100) column."),
    "D1-DATE": ("types", "Dates -> ISO date. Handles datetime cells, Excel serials, 2024.3.5, 24/03/05, 20240305, 2024년 3월 5일, 3월5일."),
    "D1-YEAR": ("types", "Date without a year gets the column's dominant year (logged with lower confidence)."),
    "D1-ORDER": ("types", "Day/month order decided per column from values > 12; undecidable ones use the contract default and are flagged."),
    "I1-ID": ("types", "IDs parsed by the contract regex and re-rendered in the canonical format (c-1, C 0001, 0001 -> C0001). Kept as text."),
    "E1-EMAIL": ("types", "Emails trimmed and lower-cased."),
    "P1-PHONE": ("types", "Korean phone numbers re-formatted 010-1234-5678 only when the digits form a valid number."),
    "C1-ALIAS": ("categories", "Category value mapped through the contract synonym table (card -> 카드)."),
    "C1-CANON": ("categories", "Category matched to canonical vocab after case/space/suffix folding (서울특별시 -> 서울)."),
    "C1-FUZZY": ("categories", "Typo matched to canonical vocab by Hangul-jamo similarity >= threshold with a clear margin (서을 -> 서울)."),
    "O1-DECISION": ("decisions", "Owner decision from the contract's overrides list (wins over every built-in rule)."),
    "U1-EXACT": ("dedup", "Rows identical in every column after normalization: first kept, later copies dropped."),
    "U2-SUSPECT": ("dedup", "Rows sharing a contract suspect key (or the same contact) are listed, never merged."),
    "U3-KEYCONFLICT": ("dedup", "Same primary key with different values: all kept and flagged."),
    "R1-DATE": ("review", "Ambiguous, impossible or out-of-range date."),
    "R2-NUMBER": ("review", "Number that cannot be parsed, mixed scale (0.1 vs 10%), or outlier."),
    "R4-CATEGORY": ("review", "Category not confidently matched to the vocab (suggestion given, value unchanged)."),
    "R5-INVALID": ("review", "Invalid ID/phone/email; never padded, guessed or rebuilt."),
    "R6-CROSS": ("review", "Cross-column or cross-table conflict (amount != qty x price, name differs from master)."),
    "R7-REQUIRED": ("review", "Required value is blank (should-have-a-value blank; not imputed)."),
    "R8-SHIFT": ("review", "Row looks misaligned but no shift fixes it confidently."),
    "R9-INSTRUCTION": ("review", "Cell text reads like instructions to an AI model: it is never sent to the LLM and never acted on."),
    "llm:synonym": ("llm", "Open category value mapped to a vocab value by the LLM (semantic synonym). Only vocab values; gated by confidence + quoted evidence + contract check."),
    "llm:resolve": ("llm", "Open review item (ambiguous date, 0.1-vs-10% scale) resolved by the LLM choosing one of the rule-computed candidates, using row/neighbour context."),
    "llm:extract": ("llm", "Structured field extracted from a free-text cell by the LLM; value must be backed by a verbatim quote from that cell."),
    "llm:entity": ("llm", "Join orphan / blank key matched to one of the top-k rule-ranked candidates by the LLM (entity resolution). Joined sheet only; the key cell is not rewritten."),
    "J1-JOIN": ("join", "Join on normalized key; fallback fuzzy match on a name column is marked with its score."),
    "J2-ORPHAN": ("join", "Left key with no match in the right table."),
    "J3-AMBIG": ("join", "Left key matching more than one right row (would multiply rows)."),
}
