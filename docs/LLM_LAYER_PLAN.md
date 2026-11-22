# LLM layer: plan (written before the code)

## Premise
The rule engine stays the backbone and the audit trail. The LLM only works on what rules already **isolated** and could not decide. It never touches a cell the rules did not hand it, and it never writes a value that is not either (a) one of a candidate set the rules computed, or (b) a span quoted from the same cell (extraction).

## Where it sits in the pipeline
```
structure -> text -> shift -> types -> categories -> owner overrides -> [L] LLM resolve -> required check -> dedup -> checks -> joins -> [L] LLM entity -> reconcile
profile.py --llm : [L] layout draft (spec only, never data)
```
Owner overrides run first, so a human decision always wins; the LLM only sees what is still open.

## Tasks (each one JSON-schema output)
| task (rule id) | input the rules hand over | allowed answers | applied when |
|---|---|---|---|
| `llm:synonym` | open R4 category value + row context + vocab | one vocab value or `null` | conf >= min, answer in vocab, quote found in input |
| `llm:resolve` | open R1 ambiguous date (2+ parse candidates) or R2 0.1-vs-10% scale + neighbour rows | one of the rule candidates or `null` | same, plus the column's contract check passes |
| `llm:extract` | a free-text cell + contract `extract:` field spec | per field: value + verbatim quote from the cell, or null | quote is a substring of the cell, value is typed/vocab-valid, number digits appear in the quote |
| `llm:entity` | join orphan + top-k right rows by similarity | one candidate key or `null` | conf >= entity min, candidate in list, quoted evidence matches the row |
| `llm:layout` | grid preview (profile) | tables with header/data row ranges + column map | validated against the grid (rows exist, header text equals the cell), then written into the **draft** contract only |

## Data shapes
- `LLMItem` = {id, task, payload(dict), candidates(list|None)} -> request
- `LLMAnswer` = {id, answer, confidence 0..1, evidence_quote, rationale} (schema enforced, re-validated at the boundary)
- `Decision` = applied | rejected(reason) -> applied becomes a `Change(rule="llm:<task>", evidence="model=...; conf=...; quote=...; why=...")`; rejected stays a `Review` with `LLM suggests ... (rejected: reason)` in the suggestion column.

## Boundaries
- Provider adapters (OpenRouter chat/completions with json_schema; Gemini generateContent with responseJsonSchema) live in one module. Everything downstream sees validated `LLMAnswer`s only.
- Mode: `off` (rules only, default when no key), `live` (cache first, then call), `cache` (cache only; a miss = no answer). Selected by `--llm` or env `CLEANKIT_LLM`.
- Cache: `<cache_dir>/<task>/<sha256(task, prompt_version, model, payload)>.json`, request + response + usage stored. Same input -> same file -> same output, so reruns stay byte-identical and offline.
- Cell text is data: the prompt says so, and nothing in an answer can name a new target (only an index into candidates or a span of the given cell).
- Cost: batch items per (table, task), temperature 0, small model by default; usage tokens are summed into run_summary.

## Proof plan
- Ablation on demo + blind + a new `semantic/` set: rules-only vs rules+LLM, same scorer, numbers: handled %, auto-resolved %, wrong, missed, cell accuracy, join rates, review-queue size, LLM changes, LLM wrong-change rate.
- `semantic/` plants issues only an LLM can resolve (synonyms outside the vocab, notes to extract, romanised names for entity resolution, context-resolvable dates) **and traps** it must not apply (no-equivalent category, negated note, orphan with no real match, date with no context).
- Idempotency with LLM on: second run reads the cache -> byte-identical; `--llm cache` reproduces offline.
