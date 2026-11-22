#!/usr/bin/env bash
# End-to-end proof: generate messy data -> profile -> clean -> clean again (idempotency) -> score -> LLM ablation -> report.
set -euo pipefail
cd "$(dirname "$0")"
SK=../skill/messy-data-cleanup/scripts
python3 make_messy_data.py
sha256sum input/* > output/.inputs.before
python3 $SK/profile.py input/*.xlsx input/*.csv --out output/profile.md --draft output/contract.draft.yaml
PYTHONHASHSEED=1 python3 $SK/clean_pipeline.py --contract contract.yaml --input-dir input --out output --name haru
sha_files() { (cd output && sha256sum haru-cleaned.xlsx run_summary.json audit.json csv/*.csv); }
sha_files > output/.run1.sha
PYTHONHASHSEED=2 python3 $SK/clean_pipeline.py --contract contract.yaml --input-dir input --out output --name haru >/dev/null
sha_files > output/.run2.sha
if diff -q output/.run1.sha output/.run2.sha >/dev/null; then echo "IDEMPOTENT: run 2 is byte-identical to run 1 ($(wc -l < output/.run1.sha) files)"; else echo "NOT IDEMPOTENT"; diff output/.run1.sha output/.run2.sha; exit 1; fi
sha256sum input/* | diff -q - output/.inputs.before >/dev/null && echo "ORIGINALS UNTOUCHED"
python3 fixed_point.py | tee output/fixed_point.txt
python3 score.py output/haru-cleaned.xlsx
# held-out dataset
(cd ../blind && python3 make_blind_data.py && python3 $SK/clean_pipeline.py --contract contract.yaml --input-dir input --out output --name blind >/dev/null \
  && python3 ../demo/score.py output/blind-cleaned.xlsx ground_truth.json | head -1)
python3 fixed_point.py ../blind | tee ../blind/output/fixed_point.txt
python3 $SK/selftest.py
# LLM layer: rules-only vs rules+LLM on 4 sets. Default replays the shipped llm_cache (no key, no cost);
# ABL_LLM=live calls the provider for anything not cached yet.
LLM_MODE=${ABL_LLM:-cache}
ABL_LLM=$LLM_MODE python3 ablation.py
for d in demo blind semantic; do
  (cd ../$d && python3 $SK/profile.py input/* --out output_llm/profile.md --draft output_llm/contract.draft.yaml \
     --llm $LLM_MODE --llm-provider openrouter --llm-cache llm_cache >/dev/null)
done
python3 ../gemini/sync_from_skill.py --check
python3 make_report.py
