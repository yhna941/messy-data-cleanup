# messy-data-cleanup

An Agent Skill that cleans badly broken Excel/CSV files and logs every change. A deterministic rule engine does the cleaning. An optional, gated LLM layer handles what rules cannot decide. Packaged for Cursor and for Gemini CLI from one engine.

## Layout

| path | what |
|---|---|
| `skill/messy-data-cleanup/` | **the one canonical skill**: SKILL.md, `reference/contract.md`, `templates/`, `scripts/` (engine `cleankit/`, `profile.py`, `clean_pipeline.py`, `selftest.py`) |
| `.cursor/rules/messy-data-cleanup.mdc` | Cursor rule that points the agent at the skill for xlsx/csv work |
| `gemini/` | Gemini CLI extension: `gemini-extension.json`, `GEMINI.md`, `skills/messy-data-cleanup/` (a byte-identical copy made by `gemini/sync_from_skill.py`, with `--check` to detect drift) |
| `demo/`, `blind/` | messy datasets with planted ground truth, scorer, report generator |
| `semantic/`, `semantic_blind/` | planted semantic/unstructured problems and traps for the LLM layer |
| `docs/LLM_LAYER_PLAN.md` | the LLM-layer design, written before the code |
| `REPORT.md` | Korean report with every number generated from the outputs |
| `ablation.json` | rules-only vs rules+LLM on 4 datasets (`ablation_live_run.json` = the live run with usage) |

Needs Python 3.9+, `openpyxl`, `pyyaml`. LLM layer: env `OPENROUTER_API_KEY` or `GEMINI_API_KEY` (optional; without one it runs rules only).

## Install in Cursor

Copy `skill/messy-data-cleanup/` to `.cursor/skills/messy-data-cleanup/` (project) or `~/.cursor/skills/messy-data-cleanup/` (personal). Optionally copy `.cursor/rules/messy-data-cleanup.mdc` into the project's `.cursor/rules/`.

## Install in Gemini CLI

Pick one:

```bash
# 1) as an extension (skill + GEMINI.md context), user-wide
gemini extensions install /path/to/messy-data-cleanup/gemini      # or: gemini extensions link <path> while developing
gemini extensions validate /path/to/messy-data-cleanup/gemini

# 2) as a bare skill, user-wide (~/.gemini/skills/)
gemini skills install /path/to/messy-data-cleanup/gemini/skills/messy-data-cleanup

# 3) as a workspace skill (the folder must be trusted: /trust)
mkdir -p .gemini/skills && cp -r /path/to/messy-data-cleanup/gemini/skills/messy-data-cleanup .gemini/skills/
```

Check with `gemini skills list` (or `/skills list` in a session, then `/skills reload`). Once installed, ask Gemini to "clean these spreadsheets". The skill activates from its description and runs the bundled `scripts/` with `python3`.

After you edit the canonical skill, run `python3 gemini/sync_from_skill.py`. `demo/run_demo.sh` fails if the Gemini copy drifted.

Format references (checked 2026-11-21):
- Skills: discovery tiers and folders: https://geminicli.com/docs/cli/using-agent-skills/ ; SKILL.md frontmatter (`name`, `description`, first thing in the file), `/skills list`, trust: https://geminicli.com/docs/cli/tutorials/skills-getting-started/ ; layout `scripts/ references/ assets/`: https://geminicli.com/docs/cli/skills-best-practices/
- Extensions: `gemini-extension.json` (`name`, `version`, `description`, `contextFileName`), `skills/<name>/SKILL.md` inside an extension, GEMINI.md context: https://geminicli.com/docs/extensions/reference/ and https://geminicli.com/docs/extensions/writing-extensions/

## Run

```bash
python3 skill/messy-data-cleanup/scripts/profile.py data/*.xlsx --out profile.md --draft contract.draft.yaml [--llm live]
python3 skill/messy-data-cleanup/scripts/clean_pipeline.py --contract contract.yaml --input-dir data --out data/cleaned [--llm live]
bash demo/run_demo.sh          # full proof: all sets, idempotency, scores, LLM ablation (replays llm_cache: no key, no cost)
ABL_LLM=live bash demo/run_demo.sh   # call the provider for anything not cached
```

`--llm off|cache|live`, `--llm-provider auto|openrouter|gemini`, `--llm-model`. Answers are cached by input hash in `llm_cache/` next to the contract. Reruns and `--llm cache` replays give byte-identical outputs.

## Credits

The ideas come from these skills:
- JuicyAgents data-cleaning-plan: fix table, review flags, reconciling totals, a rerunnable script.
- Anthropic clean-data-xls: profile first, propose before destructive ops.
- gaasher tabular-cleanup: the contract as binary checks, keep a transform only if violations drop.
- genspark genoffice data-cleaning: the Raw/Cleaned/Rules/Log/Suspected duplicates workbook, no fuzzy auto-merge, no unit guessing.
- mohitagw15856 data-cleaning-pass: normalize before dedupe, three kinds of blanks, join match rate before and after.
- magnus919 data-cleaning and dathere qsv data-clean: grain, quarantine, validate twice.
