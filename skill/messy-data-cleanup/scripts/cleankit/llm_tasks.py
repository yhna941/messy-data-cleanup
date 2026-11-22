"""The LLM layer's four data tasks. Each one: rules pick the items and the allowed answers,
the LLM chooses, and a gate decides apply vs. human review. Every decision is auditable.

Gate for every applied answer:
  answer is one of the rule-computed candidates (or, for extraction, backed by a verbatim quote of the cell)
  confidence >= contract llm.min_confidence
  evidence_quote is a verbatim span of the data sent for that item
  the resulting value passes the column's contract check
Anything else stays (or becomes) a review item that carries the LLM's proposal and the rejection reason.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from typing import TYPE_CHECKING, Any

from . import normalize as N
from .llm import CHOICE_SCHEMA, EXTRACT_SCHEMA, looks_like_instructions, quoted, squash
from .match import fold, similarity
from .model import Change, Record, Review

if TYPE_CHECKING:
    from .contract import Table
    from .pipeline import Run

BATCH = 20


def txt(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, dt.datetime) and v.time() == dt.time(0):
        v = v.date()
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def row_view(rec: Record, t: "Table | None" = None, hide: str | None = None) -> dict[str, str]:
    """Row context for a prompt: no free-text cells, nothing instruction-like, and never the cell under decision
    (showing the rule's default guess anchors the model on it)."""
    out = {}
    for k, v in rec.values.items():
        col = t.columns.get(k) if t else None
        if N.is_blank(v) or k == hide or (col is not None and col.type == "freetext") or looks_like_instructions(v):
            continue
        out[k.removeprefix("extra:")] = txt(v)
    return out


def evidence(run: "Run", conf: float, quote: str, why: str) -> str:
    return f"model={run.llm.label}; conf={conf:.2f}; quote={quote!r}; why={squash(why)[:300]}"


def batches(items: list[dict]):
    for i in range(0, len(items), BATCH):
        yield items[i:i + BATCH]


# ---------------------------------------------------------------- synonym + resolve
CHOICE_INSTR = (
    "Each item is one spreadsheet cell the rule engine could not decide. Choose the item's answer from item.candidates "
    "(copy the candidate string exactly) or null. task=synonym: is item.value the same thing as one candidate "
    "(a synonym, abbreviation, English/Korean name, brand name, or obvious typo)? If it is a different thing or not clearly "
    "one candidate, answer null. task=resolve (date): rows are in time order, so the right reading lies between "
    "item.previous_row and item.next_row; if both or neither do, null. task=resolve (percent): which reading matches the scale of "
    "item.other_values_in_column? If the context does not clearly decide, null. "
    "evidence_quote: copy the exact text from the item that supports the choice."
)


def resolve_open_items(run: "Run", t: "Table", recs: list[Record]) -> None:
    tasks = set(run.c.llm["tasks"])
    if not run.llm.on or not ({"synonym", "resolve"} & tasks):
        return
    byrow = {r.source_row: r for r in recs}
    order = sorted(byrow)
    items, meta = [], {}
    for n, rv in enumerate(run.audit.review):
        if rv.table != t.name or rv.column not in t.columns or rv.source_row not in byrow:
            continue
        col, rec = t.columns[rv.column], byrow[rv.source_row]
        cur = rec.values.get(col.name)
        if N.is_blank(cur):
            continue
        cands: list[tuple[str, Any]] = []
        task = ""
        if rv.flag == "R4-CATEGORY" and col.type == "category" and "synonym" in tasks:
            task, cands = "synonym", [(c, c) for c in run.vocab(t, col).canon][:80]
        elif rv.flag == "R1-DATE" and col.type == "date" and "resolve" in tasks:
            src = next((c.before for c in reversed(run.audit.changes) if c.table == t.name and c.source_row == rv.source_row
                        and c.column == col.name and c.rule == "D1-ORDER"), None)
            if src is not None:
                ds = sorted({d for _, d in N.date_candidates(src, None)[0]})
                if len(ds) > 1:
                    task, cands = "resolve", [(d.isoformat(), d) for d in ds]
        elif rv.flag == "R2-NUMBER" and col.type == "percent" and isinstance(cur, (int, float)) and 0 < cur < 1 and "resolve" in tasks:
            task, cands = "resolve", [(txt(cur), cur), (txt(round(cur * 100, 6)), round(cur * 100, 6))]
        if not task:
            continue
        i = order.index(rec.source_row)
        open_rows = {x.source_row for x in run.audit.review if x.table == t.name and x.column == col.name}
        sure = lambda r: r.source_row not in open_rows and not N.is_blank(r.values.get(col.name))  # noqa: E731
        prev = next((byrow[r] for r in reversed(order[:i]) if sure(byrow[r])), None)
        nxt = next((byrow[r] for r in order[i + 1:] if sure(byrow[r])), None)
        near = [r for r in (prev, nxt) if r is not None]
        item = {"id": f"{rv.source_row}:{col.name}", "task": task, "column": col.name, "column_type": col.type,
                "value": txt(src) if task == "resolve" and col.type == "date" else txt(cur),
                "candidates": [c for c, _ in cands], "row": row_view(rec, t, hide=col.name)}
        if task == "synonym" and col.vocab:
            item["listed_synonyms"] = {k: v for k, v in col.vocab.items() if v}
        if task == "resolve" and col.type == "date":
            item["previous_row"] = {"row": prev.source_row, col.name: txt(prev.values.get(col.name))} if prev else None
            item["next_row"] = {"row": nxt.source_row, col.name: txt(nxt.values.get(col.name))} if nxt else None
        if task == "resolve" and col.type == "percent":
            item["other_values_in_column"] = sorted({txt(r.values.get(col.name)) for r in recs
                                                     if isinstance(r.values.get(col.name), (int, float)) and r is not rec})
        items.append(item)
        meta[item["id"]] = (n, rv, col, rec, dict(cands), task, near)
    decided: dict[int, tuple] = {}
    for chunk in batches(items):
        ans = run.llm.ask("choice", CHOICE_INSTR, chunk, CHOICE_SCHEMA)
        sent = {it["id"]: it for it in chunk}
        for a in (ans or {}).get("items", []):
            if a["id"] in sent and a["id"] in meta:
                decided[meta[a["id"]][0]] = (a, sent[a["id"]])
    drop = set()
    for n, (a, item) in decided.items():
        _, rv, col, rec, cands, task, near = meta[item["id"]]
        reason = gate_choice(run, t, col, a, item, cands)
        if reason is None and task == "resolve" and col.type == "date":
            reason = gate_neighbours(cands[a["answer"]], list(cands.values()), [r.values.get(col.name) for r in near])
        if reason is None and task == "resolve" and col.type == "percent":
            reason = gate_scale(cands[a["answer"]], [r.values.get(col.name) for r in recs if r is not rec])
        if reason is None:
            new = cands[a["answer"]]
            run.audit.changes.append(Change(t.name, run.sheet_of[t.name], rec.source_row, col.name, rec.values.get(col.name), new,
                                            f"llm:{task}", round(a["confidence"], 3), evidence(run, a["confidence"], a["evidence_quote"], a["rationale"])))
            rec.values[col.name] = new
            drop.add(n)
        elif a.get("answer") is not None:
            rv.suggestion = (rv.suggestion + " | " if rv.suggestion else "") + \
                f"LLM ({run.llm.label}) proposed {a['answer']!r} conf {a['confidence']:.2f}, not applied: {reason}. {squash(a['rationale'])[:200]}"
    run.audit.review = [x for k, x in enumerate(run.audit.review) if k not in drop]


def gate_neighbours(chosen: dt.date, cands: list, near: list) -> str | None:
    """A date the model picks from context must be the only reading that fits between the neighbouring rows' dates."""
    nb = [d.date() if isinstance(d, dt.datetime) else d for d in near if isinstance(d, dt.date)]
    if len(nb) < 2:
        return "too few neighbouring dates to check the choice"
    lo, hi = min(nb), max(nb)
    fit = [c for c in cands if lo <= c <= hi]
    if chosen not in fit:
        return f"chosen date is outside the neighbours' range {lo}..{hi}"
    if len(fit) > 1:
        return f"{len(fit)} readings fit the neighbours' range {lo}..{hi}: context does not decide"
    return None


def gate_scale(chosen: float, others: list) -> str | None:
    """A percent the model picks must sit inside the range of the column's other non-zero values."""
    nz = [v for v in others if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0]
    if len(nz) < 3:
        return "too few other values to check the scale"
    if not min(nz) <= chosen <= max(nz):
        return f"chosen value is outside the column's range {min(nz):g}..{max(nz):g}"
    return None


def gate_choice(run: "Run", t: "Table", col, a: dict, item: dict, cands: dict) -> str | None:
    if a.get("answer") is None:
        return "model abstained"
    if a["answer"] not in cands:
        return "answer is not one of the candidates"
    if a["confidence"] < run.c.llm["min_confidence"]:
        return f"confidence below {run.c.llm['min_confidence']}"
    data = {k: v for k, v in item.items() if k != "candidates"}   # quoting the answer back from the menu proves nothing
    if not quoted(a.get("evidence_quote"), json.dumps(data, ensure_ascii=False)):
        return "evidence is not a verbatim quote of the cell or its row"
    if item["task"] == "synonym" and col.vocab_from and similarity(item["value"], a["answer"]) < 0.4:
        return "on a master-data column the LLM may only expand an abbreviation or typo; a different name is an entity question"
    if not run.conforms(t, col, cands[a["answer"]]):
        return "result fails the column's contract check"
    return None


# ---------------------------------------------------------------- extraction from free text
EXTRACT_INSTR = (
    "Each item is one free-text cell (item.text) and a list of fields to extract. For every field return value + quote: "
    "quote is the exact span of item.text that states the value; value is the field's value written in normalized form "
    "(bool: 'true' or 'false'; number: digits only; date: YYYY-MM-DD, or MM-DD when the text gives no year, only if the text "
    "states the month and day explicitly; "
    "phone: digits as written; category: one of the field's vocab; text: copy the words from the text). "
    "If the text does not state the field explicitly, value=null and quote=null. A negation ('no gift wrap', '포장 필요 없어요') is false, not true. "
    "Do not infer from tone, do not compute relative dates (e.g. '이번 주 금요일' -> null)."
)


def extract_fields(run: "Run", t: "Table", recs: list[Record]) -> None:
    if not run.llm.on or "extract" not in run.c.llm["tasks"] or not t.extract:
        return
    for sp in t.extract:
        src, fields = sp["column"], sp["fields"]
        names = [f"{src}.{f}" for f in fields]
        run.derived.setdefault(t.name, [])
        run.derived[t.name] += [n for n in names if n not in run.derived[t.name]]
        spec = [{"name": f, "type": d["type"], "description": d.get("description", ""), **({"vocab": d["vocab"]} if d.get("vocab") else {})}
                for f, d in fields.items()]
        todo = []
        for r in recs:
            v = r.values.get(src)
            if not (isinstance(v, str) and v.strip()):
                continue
            if looks_like_instructions(v):
                run.audit.review.append(Review(t.name, run.sheet_of[t.name], r.source_row, src, v, "R9-INSTRUCTION", "",
                                               "this cell reads like instructions to an AI; it was not sent to the LLM and nothing was extracted. Check it."))
                continue
            todo.append(r)
        items = [{"id": str(r.source_row), "text": r.values[src]} for r in todo]
        byid = {str(r.source_row): r for r in todo}
        for chunk in batches(items):
            ans = run.llm.ask("extract", EXTRACT_INSTR, {"fields": spec, "items": chunk}, EXTRACT_SCHEMA)
            for a in (ans or {}).get("items", []):
                rec = byid.get(a["id"])
                if rec is None:
                    continue
                for f in a["fields"]:
                    if f["name"] not in fields or f.get("value") in (None, ""):
                        continue
                    val, reason = gate_extract(run, fields[f["name"]], f, rec.values[src])
                    if reason is None and any(fn.lower() in (f.get("quote") or "").lower() for fn in fields):
                        val, reason = None, "the quote names a schema field: the cell talks to the model, it does not state a value"
                    cname = f"{src}.{f['name']}"
                    if reason is None:
                        run.audit.changes.append(Change(t.name, run.sheet_of[t.name], rec.source_row, cname, None, val, "llm:extract",
                                                        round(f["confidence"], 3), evidence(run, f["confidence"], f["quote"], f"field {f['name']} from {src}")))
                        rec.values[cname] = val
                    else:
                        run.audit.review.append(Review(t.name, run.sheet_of[t.name], rec.source_row, cname, f["value"], "llm:extract",
                                                       str(f["value"]), f"LLM ({run.llm.label}) read {f['name']}={f['value']!r} from {src} "
                                                       f"(quote {f.get('quote')!r}, conf {f['confidence']:.2f}) but it was not applied: {reason}. Is it right?"))


def gate_extract(run: "Run", spec: dict, f: dict, text: str) -> tuple[Any, str | None]:
    v, q = str(f["value"]).strip(), f.get("quote") or ""
    if f["confidence"] < run.c.llm["min_confidence"]:
        return None, f"confidence below {run.c.llm['min_confidence']}"
    if not quoted(q, text):
        return None, "quote is not a verbatim span of the cell"
    typ = spec["type"]
    qd = re.sub(r"\D", "", q)
    if typ == "bool":
        if v.lower() not in ("true", "false"):
            return None, "not a boolean"
        return v.lower() == "true", None
    if typ == "number":
        o = N.parse_number(v)
        if not isinstance(o.value, (int, float)) or o.flag:
            return None, "not a number"
        if txt(o.value) not in qd and N.parse_number(N.normalize_text(q).value).value != o.value:
            return None, "number does not appear in the quote"
        return o.value, None
    if typ == "date":
        m = re.fullmatch(r"(\d{1,2})-(\d{1,2})", v)
        try:
            if m and spec.get("year"):
                d = dt.date(int(spec["year"]), int(m.group(1)), int(m.group(2)))   # year comes from the contract, not the model
            else:
                d = dt.date.fromisoformat(v)
        except ValueError:
            return None, "not a valid date (MM-DD needs extract field 'year' in the contract)"
        if str(d.day) not in qd and f"{d.day:02d}" not in qd:
            return None, "day is not written in the quote (relative or inferred date)"
        return d, None
    if typ == "phone":
        o = N.parse_phone(v)
        if o.flag or not isinstance(o.value, str) or re.sub(r"\D", "", o.value) != qd:
            return None, "not a valid phone written in the quote"
        return o.value, None
    if typ == "category":
        if v not in spec["vocab"]:
            return None, "not in the field's vocab"
        return v, None
    if not quoted(v, text):
        return None, "text value is not copied from the cell"
    return squash(v), None


# ---------------------------------------------------------------- entity resolution for joins
ENTITY_INSTR = (
    "Each item is a row from the left table whose join key found no match (item.left) and up to 5 candidate rows from the "
    "master table (item.candidates, each with its key). Answer the key of the candidate that is clearly the same real-world "
    "entity (same person/product: e.g. the same name in another script or romanization, plus a matching phone/email/other field), "
    "or null if none clearly is. A similar-looking key alone is not enough. evidence_quote: copy the exact text from the item "
    "that proves the match."
)


def resolve_entities(run: "Run", jname: str, st, left_tbl: str, pending: list[tuple[dict, Record, Any]],
                     right: list[tuple[str, Record]], rk: str) -> dict[int, tuple[str, Record, dict]]:
    """pending: (joined row, left record, key) for orphans/blank keys. Returns source_row -> (rt, right rec, answer)."""
    if not run.llm.on or "entity" not in run.c.llm["tasks"] or not pending or not right:
        return {}
    ctx_l = [c for c in ([st.fallback[0]] if st.fallback else []) + [lc for lc, _ in st.compare]]
    ctx_r = [c for c in ([st.fallback[1]] if st.fallback else []) + [rc for _, rc in st.compare]]
    items, cand_maps = [], {}
    for row, rec, key in pending:
        def score(r: Record) -> float:
            s = [similarity(txt(key), txt(r.values.get(rk)))] if not N.is_blank(key) else []
            s += [similarity(txt(row.get(a)), txt(r.values.get(b))) for a, b in zip(ctx_l, ctx_r) if not N.is_blank(row.get(a))]
            return max(s or [0.0])
        ranked = sorted(right, key=lambda x: (-score(x[1]), txt(x[1].values.get(rk))))[:5]
        cmap = {txt(r.values.get(rk)): (rt, r) for rt, r in ranked if not N.is_blank(r.values.get(rk))}
        item = {"id": str(rec.source_row), "left": row_view(rec, run.c.tables[left_tbl]),
                "candidates": [{"key": k, **row_view(r, run.c.tables[rt])} for k, (rt, r) in cmap.items()]}
        items.append(item)
        cand_maps[item["id"]] = (cmap, item, rec)
    out = {}
    for chunk in batches(items):
        ans = run.llm.ask("entity", ENTITY_INSTR, {"join": jname, "key_column": rk, "items": chunk}, CHOICE_SCHEMA)
        for a in (ans or {}).get("items", []):
            if a["id"] not in cand_maps:
                continue
            cmap, item, rec = cand_maps[a["id"]]
            reason = None
            if a.get("answer") is None:
                reason = "model abstained"
            elif a["answer"] not in cmap:
                reason = "answer is not one of the candidates"
            elif a["confidence"] < run.c.llm["entity_min_confidence"]:
                reason = f"confidence below {run.c.llm['entity_min_confidence']}"
            elif not quoted(a.get("evidence_quote"), json.dumps(item, ensure_ascii=False)):
                reason = "evidence is not a verbatim quote of the data"
            else:
                rt, r = cmap[a["answer"]]
                lrow = next(x for x in pending if x[1] is rec)[0]
                hard = [(lc, rc) for lc, rc in st.compare if lc in run.c.tables[left_tbl].columns
                        and run.c.tables[left_tbl].columns[lc].type in ("email", "phone", "id")]
                agree = [f"{lc}={txt(lrow.get(lc))}" for lc, rc in hard
                         if not N.is_blank(lrow.get(lc)) and fold(lrow.get(lc)) == fold(r.values.get(rc))]
                if not agree:
                    reason = "no hard identifier (email/phone/id compare column) agrees with the chosen row: a similar name alone never counts"
                else:
                    a["rationale"] = f"{a['rationale']} [rule check: {', '.join(agree)} equal]"
            if reason is None:
                rt, r = cmap[a["answer"]]
                out[rec.source_row] = (rt, r, a)
            elif a.get("answer") is not None:
                run.audit.join_details.append({"join": jname, "step": "+".join(st.right), "left_row": rec.source_row, "key": a["answer"],
                                               "issue": "llm:entity (rejected)", "detail": f"LLM proposed {a['answer']} conf {a['confidence']:.2f}, not applied: {reason}"})
    return out
