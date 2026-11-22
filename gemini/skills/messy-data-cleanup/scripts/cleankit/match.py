"""Category vocabulary matching: alias -> canonical fold -> Hangul-jamo fuzzy with a margin."""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any

from .normalize import Outcome, is_blank

PUNCT = re.compile(r"[\s.\-_/·,()\[\]'\"]+")

# Built-in vocabulary: Korean first-level regions. Generic domain knowledge, not dataset tuning.
BUILTIN_VOCAB: dict[str, dict[str, list[str]]] = {
    "ko_region": {
        "서울": ["서울특별시", "서울시", "seoul"], "부산": ["부산광역시", "부산시", "busan", "pusan"],
        "대구": ["대구광역시", "daegu"], "인천": ["인천광역시", "incheon"], "광주": ["광주광역시", "gwangju"],
        "대전": ["대전광역시", "daejeon"], "울산": ["울산광역시", "ulsan"], "세종": ["세종특별자치시", "sejong"],
        "경기": ["경기도", "gyeonggi", "kyunggi"], "강원": ["강원도", "강원특별자치도", "gangwon"],
        "충북": ["충청북도", "chungbuk"], "충남": ["충청남도", "chungnam"], "전북": ["전라북도", "전북특별자치도", "jeonbuk"],
        "전남": ["전라남도", "jeonnam"], "경북": ["경상북도", "gyeongbuk"], "경남": ["경상남도", "gyeongnam"],
        "제주": ["제주특별자치도", "제주도", "jeju"],
    },
}


def fold(s: Any) -> str:
    return PUNCT.sub("", unicodedata.normalize("NFKC", str(s)).casefold())


def jamo(s: str) -> str:
    """Decompose Hangul syllables into jamo so 서을/서울 differ by one symbol, not one syllable."""
    return unicodedata.normalize("NFD", unicodedata.normalize("NFKC", s))   # NFKC maps compatibility ㄹ to conjoining ᄅ


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, jamo(fold(a)), jamo(fold(b))).ratio()


class Vocab:
    def __init__(self, canon: dict[str, list[str]], auto: float = 0.78, margin: float = 0.08, review: float = 0.5):
        self.canon = list(canon)
        self.exact = {c: c for c in canon}
        self.alias: dict[str, str] = {}
        for c, syns in canon.items():
            self.alias[fold(c)] = c
            for s in syns:
                self.alias[fold(s)] = c
        self.auto, self.margin, self.review = auto, margin, review

    def contains(self, v: Any) -> bool:
        return v in self.exact

    def match(self, v: Any) -> Outcome:
        o = Outcome(v)
        if is_blank(v) or v in self.exact:
            return o
        f = fold(v)
        if f in self.alias:
            c = self.alias[f]
            if fold(c) == f:
                return o.step("C1-CANON", c, 1.0, f"{v!r} equals {c!r} after case/space/punctuation folding")
            return o.step("C1-ALIAS", c, 1.0, f"{v!r} is a listed synonym of {c!r}")
        scored = sorted(((similarity(f, k), c, k) for k, c in self.alias.items()), reverse=True)
        best: dict[str, tuple[float, str]] = {}
        for sc, c, k in scored:
            best.setdefault(c, (sc, k))
        ranked = sorted(((sc, c, k) for c, (sc, k) in best.items()), reverse=True)
        if not ranked:
            return o
        top, c, k = ranked[0]
        second = ranked[1][0] if len(ranked) > 1 else 0.0
        variant = variant_difference(f, k)
        if len(f) >= 2 and top >= self.auto and top - second >= self.margin and not variant:
            return o.step("C1-FUZZY", c, round(top, 3),
                          f"{v!r} ~ {k!r} (jamo similarity {top:.2f}; next best {ranked[1][1] if len(ranked) > 1 else '-'} {second:.2f})")
        sugg = c if top >= self.review else ""
        why = f"closest {c!r} at {top:.2f}" + (f", runner-up {ranked[1][1]!r} at {second:.2f}" if len(ranked) > 1 else "")
        if variant:
            why += f"; not auto-mapped because {variant}"
        o.flag = ("R4-CATEGORY", sugg, f"{v!r} is not in the vocabulary ({why}): map it, or add it as a new value?")
        return o


def variant_difference(a: str, b: str) -> str:
    """Why two near-identical strings may be different things (sizes, models, A/B variants), or ''."""
    da, db = re.findall(r"\d+", a), re.findall(r"\d+", b)
    if da != db:
        return f"numbers differ ({'/'.join(da) or '-'} vs {'/'.join(db) or '-'})"
    if len(a) == len(b) and a[:-1] == b[:-1] and a[-1:].isascii() and b[-1:].isascii() and a[-1:].isalnum() and b[-1:].isalnum():
        return f"only the variant suffix differs ({a[-1]} vs {b[-1]})"
    return ""
