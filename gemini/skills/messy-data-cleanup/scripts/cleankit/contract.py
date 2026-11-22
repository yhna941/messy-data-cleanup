"""Boundary: load and validate the YAML contract once; everything downstream trusts it."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

TYPES = {"id", "text", "freetext", "category", "date", "number", "money", "percent", "count", "phone", "email"}
NUMERIC = {"number", "money", "percent", "count"}


@dataclass
class Column:
    name: str
    type: str
    aliases: list[str]
    required: bool = False
    regex: str | None = None
    format: str | None = None
    vocab: dict[str, list[str]] | None = None
    vocab_builtin: str | None = None
    vocab_from: str | None = None          # "table.column"
    min: float | None = None
    max: float | None = None
    decimal: str = "auto"


@dataclass
class Table:
    name: str
    file: str
    sheet: str
    block: int
    key: str | None
    columns: dict[str, Column]
    exact_dups: str = "drop"               # drop | flag
    suspect_keys: list[list[str]] = field(default_factory=list)
    contact_keys: list[str] = field(default_factory=list)
    checks: list[dict] = field(default_factory=list)
    date_order: list[str] = field(default_factory=lambda: ["YMD", "MDY", "DMY"])
    date_window: tuple[str, str] | None = None
    extract: list[dict] = field(default_factory=list)   # LLM: [{column, fields: {name: {type, description, vocab}}}]


@dataclass
class JoinStep:
    right: list[str]
    on: tuple[str, str]
    prefix: str
    fallback: tuple[str, str] | None = None
    compare: list[tuple[str, str]] = field(default_factory=list)
    expect: str = "many_to_one"


@dataclass
class Join:
    name: str
    left: str
    steps: list[JoinStep]


@dataclass
class Contract:
    dataset: str
    base: Path
    tables: dict[str, Table]
    joins: list[Join]
    fuzzy_auto: float = 0.78
    fuzzy_margin: float = 0.08
    overrides: list[dict] = field(default_factory=list)   # user decisions: {table, column, before, after}
    llm: dict = field(default_factory=dict)               # {min_confidence, entity_min_confidence, tasks, cache_dir}


class ContractError(SystemExit):
    pass


def _need(d: dict, k: str, where: str) -> Any:
    if k not in d:
        raise ContractError(f"contract: {where} is missing '{k}'")
    return d[k]


def load(path: Path) -> Contract:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    tables: dict[str, Table] = {}
    for tname, t in _need(raw, "tables", "root").items():
        cols = {}
        for cname, c in _need(t, "columns", tname).items():
            ctype = _need(c, "type", f"{tname}.{cname}")
            if ctype not in TYPES:
                raise ContractError(f"contract: {tname}.{cname} type {ctype!r} not in {sorted(TYPES)}")
            if ctype == "id" and not (c.get("regex") and c.get("format")):
                raise ContractError(f"contract: id column {tname}.{cname} needs regex and format")
            if ctype == "category" and not (c.get("vocab") or c.get("vocab_builtin") or c.get("vocab_from")):
                raise ContractError(f"contract: category column {tname}.{cname} needs vocab, vocab_builtin or vocab_from")
            vocab = c.get("vocab")
            if isinstance(vocab, list):
                vocab = {v: [] for v in vocab}
            cols[cname] = Column(cname, ctype, [str(a) for a in c.get("aliases", [cname])], bool(c.get("required", False)),
                                 c.get("regex"), c.get("format"), vocab, c.get("vocab_builtin"), c.get("vocab_from"),
                                 c.get("min"), c.get("max"), str(c.get("decimal", "auto")))
        key = t.get("key")
        if key and key not in cols:
            raise ContractError(f"contract: {tname}.key {key!r} is not a column")
        dd = t.get("dedup", {})
        for ks in dd.get("suspect_keys", []):
            for k in ks:
                if k not in cols:
                    raise ContractError(f"contract: {tname}.dedup.suspect_keys has unknown column {k!r}")
        win = t.get("date_window")
        tables[tname] = Table(tname, str(_need(t, "file", tname)), str(t.get("sheet", "")), int(t.get("block", 1)), key, cols,
                              dd.get("exact", "drop"), dd.get("suspect_keys", []), dd.get("contact_keys", []),
                              t.get("checks", []), t.get("date_order", ["YMD", "MDY", "DMY"]), tuple(win) if win else None,
                              _extract(t.get("extract", []), cols, tname))
    for t in tables.values():
        for c in t.columns.values():
            if c.vocab_from:
                ft, _, fc = c.vocab_from.partition(".")
                if ft not in tables or fc not in tables[ft].columns:
                    raise ContractError(f"contract: {t.name}.{c.name} vocab_from {c.vocab_from!r} not found")
                if list(tables).index(ft) > list(tables).index(t.name):
                    raise ContractError(f"contract: {t.name}.{c.name} vocab_from must point to a table listed earlier")
    joins = []
    for j in raw.get("joins", []):
        left = _need(j, "left", "join")
        if left not in tables:
            raise ContractError(f"contract: join {j.get('name')} left {left!r} unknown")
        steps = []
        for s in _need(j, "steps", f"join {j.get('name')}"):
            right = s["right"] if isinstance(s["right"], list) else [s["right"]]
            for r in right:
                if r not in tables:
                    raise ContractError(f"contract: join right table {r!r} unknown")
            steps.append(JoinStep(right, tuple(_need(s, "keys", "join step")), s.get("prefix", right[0] + "_"),
                                  tuple(s["fallback"]) if s.get("fallback") else None,
                                  [tuple(x) for x in s.get("compare", [])], s.get("expect", "many_to_one")))
        joins.append(Join(_need(j, "name", "join"), left, steps))
    d = raw.get("defaults", {})
    llm = {"min_confidence": 0.8, "entity_min_confidence": 0.85, "tasks": list(LLM_TASKS), "cache_dir": "llm_cache", **(raw.get("llm") or {})}
    bad = set(llm["tasks"]) - LLM_TASKS
    if bad:
        raise ContractError(f"contract: llm.tasks has unknown task(s) {sorted(bad)}; known: {sorted(LLM_TASKS)}")
    return Contract(str(raw.get("dataset", path.stem)), path.parent, tables, joins,
                    float(d.get("fuzzy_auto", 0.78)), float(d.get("fuzzy_margin", 0.08)), raw.get("overrides", []) or [], llm)


LLM_TASKS = {"synonym", "resolve", "extract", "entity"}
FIELD_TYPES = {"bool", "text", "number", "date", "phone", "category"}


def _extract(specs: list, cols: dict, tname: str) -> list[dict]:
    out = []
    for sp in specs or []:
        src = _need(sp, "column", f"{tname}.extract")
        if src not in cols:
            raise ContractError(f"contract: {tname}.extract column {src!r} is not a column")
        fields = _need(sp, "fields", f"{tname}.extract")
        for fname, f in fields.items():
            if f.get("type") not in FIELD_TYPES:
                raise ContractError(f"contract: {tname}.extract.{fname} type must be one of {sorted(FIELD_TYPES)}")
            if f["type"] == "category" and not f.get("vocab"):
                raise ContractError(f"contract: {tname}.extract.{fname} category needs vocab")
        out.append({"column": src, "fields": fields})
    return out
