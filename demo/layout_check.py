#!/usr/bin/env python3
"""Compare table-layout reads (rule profile vs LLM layout) with the header rows the cleaning run actually used.
usage: layout_check.py <dir with output/run_summary.json + contract.yaml> <profile.md with LLM section> <draft yaml>"""
import json
import re
import sys
from pathlib import Path

import yaml

d = Path(sys.argv[1])
summ = json.loads((d / "output" / "run_summary.json").read_text(encoding="utf-8"))
con = yaml.safe_load((d / "contract.yaml").read_text(encoding="utf-8"))
draft = yaml.safe_load(Path(sys.argv[3]).read_text(encoding="utf-8"))
prof = Path(sys.argv[2]).read_text(encoding="utf-8")
truth = []
for t, st in summ["tables"].items():
    c = con["tables"][t]
    truth.append((c["file"], c.get("sheet", ""), list(range(st["header_row"], st["header_row"] + st["header_depth"]))))
llm = [(x["file"], x["sheet"], sorted(x["header_rows"])) for x in draft.get("llm_layout", [])]
rule = []
for m in re.finditer(r"^## ([^\n]+?) / ([^\n]+?)\n.*?- likely header: row (\d+)(?:-(\d+))?", prof, re.S | re.M):
    f, sh, a, b = m.group(1), m.group(2), int(m.group(3)), m.group(4)
    rule.append((f, "" if f.endswith(".csv") else sh, list(range(a, int(b) + 1)) if b else [a]))
def hits(reads):
    return sum(1 for x in truth if x in reads)
out = {"tables": len(truth), "rule_profile_correct": hits(rule), "llm_layout_correct": hits(llm),
       "llm_extra_tables": len([x for x in llm if x not in truth]), "rule_tables_found": len(rule), "llm_tables_found": len(llm)}
print(json.dumps(out))
