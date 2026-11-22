# Contract schema

```yaml
dataset: <label>
defaults:
  fuzzy_auto: 0.78      # min jamo similarity to auto-map a category
  fuzzy_margin: 0.08    # best must beat the runner-up canonical by this much
tables:                 # order matters: vocab_from must point to an earlier table
  <table>:
    file: <file name in --input-dir>
    sheet: <sheet name>     # omit for CSV
    block: 1                # n-th table on the sheet (a header preceded by a blank row starts a new block)
    key: <column>           # primary key: uniqueness check, key conflicts, dedup policy
    date_order: [YMD, MDY, DMY]      # preference for undecidable dates (column votes override)
    date_window: [2024-01-01, 2024-03-31]   # optional; else derived from unambiguous dates +-31 days
    columns:
      <column>:
        type: id | text | freetext | category | date | number | money | percent | count | phone | email
        aliases: [header text, ...]     # matched after removing spaces/case; 2-row headers match "parent+child" or child
        required: false
        regex: '(?i)c?[-_ ]?0*(?P<n>\d{1,4})'   # id only: named groups...
        format: 'C{n:04d}'                     # ...rendered here (digit groups become ints)
        vocab: {canonical: [synonym, ...]}     # category; a plain list means no synonyms
        vocab_builtin: ko_region               # category; built-in Korean regions (서울/경기/...)
        vocab_from: <table>.<column>           # category; canonical values come from a cleaned master column
        min: 0                                 # numeric bounds (also used to spot shifted rows)
        max: 100
        decimal: auto | "." | ","              # auto decides per column from values only one reading fits
    dedup:
      exact: drop | flag                       # rows identical after normalization
      suspect_keys: [[col, col, ...]]          # same values on all => suspected duplicate (never merged)
      contact_keys: [phone, email]             # two shared contacts, or one plus a similar name => suspected
    checks:
      - name: <label>
        column: <column the flag goes on>
        expr: abs(amount - round(qty * unit_price * (1 - nz(discount_pct) / 100))) <= 10
        expected: round(qty * unit_price * (1 - nz(discount_pct) / 100))   # shown as the suggestion
        message: <question for the owner>
joins:
  - name: <join>
    left: <table>
    steps:                     # applied in order to the growing left table
      - right: <table> | [<table>, <table>]   # several tables are searched together (e.g. products + discontinued)
        keys: [left_col, right_col]           # not "on": YAML reads `on` as true
        fallback: [left_col, right_col]       # optional second key (exact after folding) when the first is blank or unmatched
        prefix: cust_
        compare: [[left_col, right_col]]      # flag rows where these disagree (name in orders vs master)
overrides:                     # owner decisions, applied after typing; remove the matching review item
  - {table: orders, column: payment, before: 카느, after: 카드}
  - {table: orders, column: order_date, row: 25, before: 2024-03-02, after: 2024-02-03}
```

Types decide parsing and the strict check:

| type | parsed by | conforms when |
|---|---|---|
| id | regex + format | text equal to its canonical rendering |
| date | serials, Y.M.D, YYYYMMDD, YY/MM/DD, DD.MM.YYYY, Feb 16 2024, 3월 5일 | a date |
| number, money, count | ₩/원/,/spaces, 천/만/억, (1,200), △, 두개, 3개, 2 EA, decimal comma | a number inside min/max |
| percent | as number, `10%` → 10 | 0..100 (fractions in a 0-100 column are flagged) |
| category | synonym → fold → jamo fuzzy | in the canonical vocab |
| phone | Korean mobile/landline digits, +82 | 010-1234-5678 shape |
| email | trim + lower | `x@y.tld` |
| text / freetext | whitespace, NFKC, mojibake | already normalized |

## LLM layer keys (optional; ignored when the run uses `--llm off`)

```yaml
tables:
  orders:
    extract:                   # llm:extract: free-text cell -> new columns <column>.<field> (never overwrites a column)
      - column: note           # must be a contract column (usually type freetext)
        fields:
          gift_wrap: {type: bool, description: "true if they ask for wrapping, false if they say no"}
          contact_phone: {type: phone}
          requested_date: {type: date, year: 2024}   # year comes from here when the text says only 3월 8일 / 3/15
          candles: {type: number}
          lettering: {type: text}                     # text values must be copied verbatim from the cell
          channel: {type: category, vocab: [전화, 방문, 앱]}
llm:
  min_confidence: 0.8          # below this an answer only becomes a suggestion in Needs human review
  entity_min_confidence: 0.85  # join entity resolution
  tasks: [synonym, resolve, extract, entity]   # drop a task to switch it off for this dataset
  cache_dir: llm_cache         # relative to the contract; ship it to reproduce a run offline (--llm cache)
```

Entity resolution (`llm:entity`) uses the join step's `compare` pairs: a match is applied only if at least one compare column of type email, phone or id is equal in both rows. Add `[email, email]` or `[phone, phone]` to `compare` or the LLM can never match.
