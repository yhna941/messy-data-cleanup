"""Pure value-level parsers. Each returns an Outcome; none touch global state."""
from __future__ import annotations

import datetime as dt
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Step:
    rule: str
    before: Any
    after: Any
    confidence: float
    evidence: str


@dataclass(slots=True)
class Outcome:
    value: Any
    steps: list[Step] = field(default_factory=list)
    flag: tuple[str, str, str] | None = None   # (flag, suggestion, question)

    def step(self, rule: str, after: Any, conf: float, evidence: str) -> "Outcome":
        if after != self.value or type(after) is not type(self.value):
            self.steps.append(Step(rule, self.value, after, conf, evidence))
            self.value = after
        return self


def is_blank(v: Any) -> bool:
    return v is None or (isinstance(v, str) and v.strip() == "")


# ---------------------------------------------------------------- text
ZERO_WIDTH = re.compile("[\u200b\u200c\u200d\u2060\ufeff\u00ad]")
CONTROL = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
MOJIBAKE_HINT = re.compile("[ÃÂâ€ìíêëåäðÐ¤¸™˜ˆ‰]")
HANGUL = re.compile("[\uac00-\ud7a3]")
PLACEHOLDERS = {"-", "--", "—", "n/a", "na", "#n/a", "null", "none", "nan", "?", "없음", "미입력", "해당없음", "x", "#value!", "#ref!", "#div/0!"}
EXCEL_ERRORS = {"#n/a", "#value!", "#ref!", "#div/0!", "#name?", "#num!", "#null!"}


def _cp1252_bytes(s: str) -> bytes | None:
    out = bytearray()
    for ch in s:
        try:
            out += ch.encode("cp1252")
        except UnicodeEncodeError:
            if ord(ch) < 256:
                out.append(ord(ch))   # latin-1 fallback for bytes cp1252 leaves undefined
            else:
                return None
    return bytes(out)


def repair_mojibake(s: str) -> tuple[str, str] | None:
    """Return (fixed, how) when re-decoding gives clean text with more Hangul/accents, else None."""
    if MOJIBAKE_HINT.search(s):
        b = _cp1252_bytes(s)
        if b is not None:
            try:
                fixed = b.decode("utf-8")
                if fixed != s and not MOJIBAKE_HINT.search(fixed):
                    return fixed, "UTF-8 bytes had been read as cp1252/latin-1"
            except UnicodeDecodeError:
                pass
    # UTF-8 bytes read as cp949 produce rare Hangul/Hanja soup; re-encoding gives valid UTF-8.
    if any(ord(c) > 0x2e80 for c in s):
        try:
            fixed = s.encode("cp949").decode("utf-8")
            if fixed != s and HANGUL.search(fixed) and len(fixed) < len(s) * 1.2:
                return fixed, "UTF-8 bytes had been read as cp949"
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    return None


def nfkc(s: str) -> str:
    """NFKC per character, except where it changes meaning or makes broken text: Hangul compatibility
    jamo (ㅋㅋ, ㄹ, ㆍ) would become conjoining jamo, superscripts (m², m³) would become plain digits, and
    spacing accents (˙ ˝) would become a space plus a combining mark."""
    return "".join(ch if _keep(ch) else unicodedata.normalize("NFKC", ch) for ch in s)


def _keep(ch: str) -> bool:
    if ch.isascii() or "\u3131" <= ch <= "\u318e":
        return True
    d = unicodedata.decomposition(ch)
    return d.startswith(("<super>", "<sub>")) or (d.startswith("<compat> 0020") and len(d.split()) > 2)


def normalize_text(v: Any, freetext: bool = False) -> Outcome:
    o = Outcome(v)
    if not isinstance(v, str):
        return o
    s = v
    cleaned = CONTROL.sub("", ZERO_WIDTH.sub("", s)).replace("\u00a0", " ").replace("\u3000", " ")
    if cleaned != s:
        o.step("T1-WS", cleaned, 1.0, "removed zero-width/control/NBSP characters")
        s = cleaned
    m = repair_mojibake(s)
    if m:
        o.step("T1-MOJIBAKE", m[0], 0.95, m[1])
        s = m[0]
    n = nfkc(s)
    if n != s:
        o.step("T1-NFKC", n, 1.0, "full-width/compatibility characters -> half-width")
        s = n
    if freetext:
        t = "\n".join(re.sub(r"[ \t]+", " ", line).strip() for line in s.strip().splitlines())
    else:
        t = re.sub(r"\s+", " ", s).strip()
    if t != s:
        o.step("T1-WS", t, 1.0, "trimmed / collapsed whitespace")
    return o


def placeholder(o: Outcome) -> Outcome:
    v = o.value
    if isinstance(v, str) and v.strip().casefold() in PLACEHOLDERS:
        o.step("M1-PLACEHOLDER", None, 1.0, f"placeholder {v!r} means 'no value'")
        if v.strip().casefold() in EXCEL_ERRORS:
            o.flag = ("R2-NUMBER", "", f"Excel error {v!r} in the source: what was the real value?")
    elif isinstance(v, str) and v == "":
        o.value = None
    return o


# ---------------------------------------------------------------- numbers
NATIVE_COUNT = {"한": 1, "하나": 1, "두": 2, "둘": 2, "세": 3, "셋": 3, "석": 3, "네": 4, "넷": 4, "다섯": 5,
                "여섯": 6, "일곱": 7, "여덟": 8, "아홉": 9, "열": 10}
COUNT_SUFFIX = re.compile(r"\s*(개|ea|pcs|pc|건|잔|병|박스|box|set|세트)$", re.I)
CURRENCY = re.compile(r"(₩|\\|krw|won|원|\$|usd)", re.I)
KUNIT = re.compile(r"^(?:(?P<eok>\d+(?:\.\d+)?)억)?(?:(?P<man>\d+(?:\.\d+)?)만)?(?:(?P<cheon>\d+(?:\.\d+)?)천)?(?P<rest>\d+)?$")
COMMA_DECIMAL_HINT = re.compile(r"^-?\d{1,3}(\.\d{3})+,\d+$|^-?\d+,\d{1,2}$")
LEADING_ZERO = re.compile(r"0\d+")
POINT_DECIMAL_HINT = re.compile(r"^-?\d{1,3}(,\d{3})+\.\d+$|^-?\d+\.\d{1,2}$")


def decide_decimal(values: list[Any]) -> tuple[str, str]:
    """Per column: ',' if some value can only be read with a decimal comma, else '.'."""
    comma = point = 0
    for v in values:
        if isinstance(v, str):
            s = CURRENCY.sub("", v).replace(" ", "").strip("()-")
            comma += bool(COMMA_DECIMAL_HINT.match(s))
            point += bool(POINT_DECIMAL_HINT.match(s))
    if comma and not point:
        return ",", f"{comma} value(s) only readable with decimal comma (e.g. 13.500,00)"
    if comma and point:
        return ".", f"mixed decimal marks ({comma} comma-style, {point} point-style); point assumed"
    return ".", "decimal point (default)"


def _num(x: float, digits: int | None = None) -> int | float:
    """45000.0 -> 45000. Only arithmetic results (Korean units) are rounded; a parsed or stored float is kept exactly."""
    x = float(x) if digits is None else round(float(x), digits)
    return int(x) if x.is_integer() else x


def parse_number(v: Any, decimal: str = ".", allow_percent: bool = False) -> Outcome:
    o = Outcome(v)
    if isinstance(v, bool) or is_blank(v):
        return o
    if isinstance(v, (int, float)):
        o.value = _num(v)  # 45000.0 -> 45000 is a representation detail, not a value change
        return o
    s = str(v).strip()
    neg = False
    if re.fullmatch(r"\(.*\)", s):
        neg, s = True, s[1:-1]
    if s[:1] in ("-", "△", "−"):   # △ is the Korean accounting minus sign
        neg, s = True, s[1:].strip()
    if s.endswith("-") and not s.startswith("-"):
        neg, s = True, s[:-1]
    s = s.replace(" ", "")
    if allow_percent and s.endswith("%"):
        try:
            num = float(s[:-1].replace(",", "."))
            return o.step("N1-PERCENT", _num(-num if neg else num), 1.0, f"{v!r}: percent sign removed")
        except ValueError:
            pass
    # native Korean counts: 두개, 세 개
    word = COUNT_SUFFIX.sub("", s)
    standalone = ("하나", "둘", "셋", "넷", "다섯", "여섯", "일곱", "여덟", "아홉")
    if word in NATIVE_COUNT and (word != s or word in standalone):
        return o.step("N1-KCOUNT", NATIVE_COUNT[word], 0.9, f"{v!r}: native Korean number")
    stripped = COUNT_SUFFIX.sub("", s)
    unit_rule = "N1-KCOUNT" if stripped != s else None
    s2 = CURRENCY.sub("", stripped)
    m = KUNIT.match(s2.replace(",", ""))
    if m and any(m.group(g) for g in ("eok", "man", "cheon")):
        total = sum(float(m.group(g) or 0) * mult for g, mult in (("eok", 1e8), ("man", 1e4), ("cheon", 1e3))) + float(m.group("rest") or 0)
        return o.step("N1-KUNIT", _num(-total if neg else total, 10), 0.95, f"{v!r}: Korean magnitude units applied")
    t = s2.replace(".", "").replace(",", ".") if decimal == "," else s2.replace(",", "")
    if LEADING_ZERO.fullmatch(t):   # 06164, 000123: a code (zip, account, industry) - a number would lose the zeros
        o.flag = ("R2-NUMBER", "", f"{v!r} has a leading zero, so it looks like a code, not a number: keep it as text "
                                   f"(type text/id in the contract)? (not converted)")
        return o
    try:
        num = float(t)
    except ValueError:
        o.flag = ("R2-NUMBER", "", f"{v!r} is not a number: what value was meant?")
        return o
    rule = unit_rule or "N1-NUMBER"
    return o.step(rule, _num(-num if neg else num), 1.0 if decimal == "." else 0.9,
                  f"{v!r}: text number" + (" (decimal comma column)" if decimal == "," else ""))


# ---------------------------------------------------------------- dates
EXCEL_EPOCH = dt.date(1899, 12, 30)
RE_YMD = re.compile(r"^(\d{4})\s*[.\-/년]\s*(\d{1,2})\s*[.\-/월]\s*(\d{1,2})\s*일?\.?"
                    r"(?:(?:\s+|T)(\d{1,2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?$")   # ISO 2024-01-05T13:22:08.000
RE_COMPACT = re.compile(r"^(\d{4})(\d{2})(\d{2})$")
RE_SHORT3 = re.compile(r"^(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{1,2})$")      # 24/03/05
RE_XXY4 = re.compile(r"^(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})$")          # 05/03/2024
RE_MD = re.compile(r"^(\d{1,2})\s*월\s*(\d{1,2})\s*일?$")
MONTHS = {m: i for i, ms in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1) for m in (ms,)}
RE_MON_DY = re.compile(r"^([a-z]{3})[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})$", re.I)        # Feb 16, 2024
RE_D_MON_Y = re.compile(r"^(\d{1,2})[\s\-]([a-z]{3})[a-z]*\.?[\s\-,]+(\d{2}|\d{4})$", re.I)  # 16 Feb 2024, 16-Feb-24


def _mk(y: int, m: int, d: int) -> dt.date | None:
    try:
        return dt.date(y, m, d)
    except ValueError:
        return None


def date_candidates(v: Any, year_hint: int | None) -> tuple[list[tuple[str, dt.date]], str]:
    """All valid readings of v as (order, date). Pure; ordering decided by caller."""
    if isinstance(v, dt.datetime):
        return [("cell", v.date())], "date cell"
    if isinstance(v, dt.date):
        return [("cell", v)], "date cell"
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        if 20000 <= v <= 80000:
            return [("serial", EXCEL_EPOCH + dt.timedelta(days=int(v)))], f"Excel serial {v}"
        s = str(int(v)) if float(v).is_integer() else str(v)
    else:
        s = str(v).strip()
    if m := RE_YMD.match(s):
        d = _mk(*map(int, m.groups()[:3]))
        return ([("YMD", d)] if d else []), s
    if m := RE_COMPACT.match(s):
        d = _mk(*map(int, m.groups()))
        return ([("YMD", d)] if d else []), s
    if m := RE_SHORT3.match(s):
        a, b, c = map(int, m.groups())
        out = [(o, d) for o, d in (("YMD", _mk(2000 + a, b, c)), ("DMY", _mk(2000 + c, b, a)), ("MDY", _mk(2000 + c, a, b))) if d]
        return out, s
    if m := RE_XXY4.match(s):
        a, b, y = map(int, m.groups())
        out = [(o, d) for o, d in (("DMY", _mk(y, b, a)), ("MDY", _mk(y, a, b))) if d]
        return out, s
    if (m := RE_MON_DY.match(s)) and m.group(1).lower() in MONTHS:
        d = _mk(int(m.group(3)), MONTHS[m.group(1).lower()], int(m.group(2)))
        return ([("YMD", d)] if d else []), s
    if (m := RE_D_MON_Y.match(s)) and m.group(2).lower() in MONTHS:
        y = int(m.group(3))
        d = _mk(y + 2000 if y < 100 else y, MONTHS[m.group(2).lower()], int(m.group(1)))
        return ([("YMD", d)] if d else []), s
    if (m := RE_MD.match(s)) and year_hint:
        d = _mk(year_hint, *map(int, m.groups()))
        return ([("MD", d)] if d else []), s
    return [], s


def time_of_day(v: Any) -> dt.time | None:
    """The non-midnight time carried by a datetime cell or a 'YYYY-MM-DD hh:mm[:ss]' string, else None."""
    if isinstance(v, dt.datetime):
        t = v.time().replace(microsecond=0)
    elif isinstance(v, str) and (m := RE_YMD.match(v.strip())) and m.group(4) is not None:
        try:
            t = dt.time(int(m.group(4)), int(m.group(5)), int(m.group(6) or 0))
        except ValueError:
            return None
    else:
        return None
    return None if t == dt.time(0) else t


def parse_date(v: Any, order_pref: list[str], year_hint: int | None,
               window: tuple[dt.date, dt.date] | None) -> Outcome:
    o = Outcome(v)
    if is_blank(v):
        return o
    cands, src = date_candidates(v, year_hint)
    if not cands:
        o.flag = ("R1-DATE", "", f"{v!r} is not a valid date (impossible day/month or unknown format): what date was meant?")
        return o
    order = {k: i for i, k in enumerate(["cell", "serial", "MD"] + order_pref)}
    cands.sort(key=lambda x: order.get(x[0], 99))
    distinct = {d for _, d in cands}
    plausible = [d for d in distinct if window is None or window[0] <= d <= window[1]]
    chosen_order, chosen = next(((k, d) for k, d in cands if window is None or window[0] <= d <= window[1]), cands[0])
    conf, ev = 1.0, f"{src} read as {chosen_order}"
    rule = "D1-DATE"
    if chosen_order == "MD":
        rule, conf, ev = "D1-YEAR", 0.85, f"{src}: no year, used column's dominant year {year_hint}"
    elif len(distinct) > 1 and len(plausible) > 1:
        rule, conf = "D1-ORDER", 0.5
        alt = ", ".join(f"{k}={d.isoformat()}" for k, d in cands)
        ev = f"{src} is ambiguous ({alt}); used contract order {chosen_order}"
        o.flag = ("R1-DATE", chosen.isoformat(), f"{src!r} could be {alt}: which one?")
    elif len(cands) > 1:
        ev += " (other readings fall outside the column's date range)"
    if isinstance(v, dt.datetime) and v.time() == dt.time(0):
        o.value = chosen  # same date, just drop the 00:00 time: not a value change
        return o
    day = chosen
    tod = time_of_day(v)
    if tod is not None:   # keep the time: 2024-01-05 13:22 must not silently become 2024-01-05
        chosen = dt.datetime.combine(chosen, tod)
        ev += f" (time {tod.isoformat()} kept)"
        if isinstance(v, dt.datetime) and v == chosen:
            return o
    o.step(rule, chosen, conf, ev)
    if window and not (window[0] <= day <= window[1]) and o.flag is None:
        o.flag = ("R1-DATE", "", f"{day.isoformat()} is outside the expected range {window[0]}..{window[1]}")
    return o


# ---------------------------------------------------------------- ids, phones, emails
def parse_id(v: Any, regex: str, fmt: str) -> Outcome:
    o = Outcome(v)
    if is_blank(v):
        return o
    s = str(int(v)) if isinstance(v, float) and v.is_integer() else str(v).strip()
    m = re.fullmatch(regex, s)
    if not m:
        o.flag = ("R5-INVALID", "", f"ID {v!r} does not match the expected pattern: which record is it?")
        return o
    groups = {k: int(x) if x and x.isdigit() else x for k, x in m.groupdict().items()}
    out = fmt.format(**groups)
    return o.step("I1-ID", out, 1.0 if s.upper().replace(" ", "") == out.upper() else 0.95, f"{v!r} parsed as {groups}")


def parse_phone(v: Any) -> Outcome:
    o = Outcome(v)
    if is_blank(v):
        return o
    digits = re.sub(r"\D", "", str(v))
    if digits.startswith("82") and len(digits) in (11, 12):
        digits = "0" + digits[2:]
    if re.fullmatch(r"010\d{8}|01[16789]\d{7,8}", digits):   # 010 numbers always have 11 digits
        out = f"{digits[:3]}-{digits[3:-4]}-{digits[-4:]}"
    elif re.fullmatch(r"02\d{7,8}", digits):
        out = f"02-{digits[2:-4]}-{digits[-4:]}"
    elif re.fullmatch(r"0[3-6]\d\d{7,8}", digits):
        out = f"{digits[:3]}-{digits[3:-4]}-{digits[-4:]}"
    else:
        hint = " (looks like a leading 0 was lost; not rebuilt)" if re.fullmatch(r"10\d{8}|1[16789]\d{7,8}", digits) else ""
        o.flag = ("R5-INVALID", "0" + digits if hint else "", f"phone {v!r} is not a valid Korean number{hint}")
        return o
    return o.step("P1-PHONE", out, 1.0, f"{v!r}: digits {digits}")


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$")


def parse_email(v: Any) -> Outcome:
    o = Outcome(v)
    if is_blank(v):
        return o
    s = str(v).strip().lower()
    o.step("E1-EMAIL", s, 1.0, "lower-cased")
    if not EMAIL_RE.match(s):
        o.flag = ("R5-INVALID", "", f"email {v!r} is malformed: what is the right address?")
    return o
