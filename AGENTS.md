# AGENTS.md

Working agreement for agentic contributors to bs-score.

## Setup

```bash
uv sync --extra dev
```

## Verify before you commit

```bash
uv run pytest                                     # tests
uv run ruff check .                               # lint
uv run python scripts/gen_agent_wrappers.py --check   # wrappers are generated
uv run python scripts/check_receipts.py           # receipts reproduce exactly
uv run python scripts/gen_llms_txt.py --check     # llms.txt files are generated
```

All five run in CI; a red one blocks the merge.

## Rules that bite

- **`agents/*` wrappers are GENERATED.** Edit `scripts/gen_agent_wrappers.py`
  and re-run it — never edit `agents/<runtime>/SKILL.md` or `README.md` by hand.
  `tests/test_wrappers.py` fails on drift.
- **`llms.txt` and `llms-full.txt` are GENERATED** from `SKILL.md`,
  `scoring.json`, and `findings.schema.json` by `scripts/gen_llms_txt.py`.
- **Receipts must reproduce.** Every `examples/score.*.json` is the byte-exact
  output of its `findings.*.json`. When examples, weights, the schema, or
  report fields change, regenerate with
  `uv run python scripts/check_receipts.py --write` and eyeball the diff.
- **Docs are claims.** README/SKILL.md weight tables are parsed by
  `tests/test_scoring_profiles.py` and must equal `scoring.json`; every long
  option printed in docs must exist in the CLI (`tests/test_docs.py`);
  every relative link must resolve. If you add a `target_kind`, update
  `scoring.json`, `findings.schema.json`, both weight tables,
  `checklists/<kind>.md`, and the wrapper template together.
- **Deliberately broken fixtures stay broken.** `examples/fixture-*` contains
  lies and bugs on purpose — the examples quote them. Ruff excludes
  `examples/fixture-repo`; extend the exclude/ignore lists when adding
  fixtures, never "fix" them.

## Commits

- Logical chunks, imperative subject lines (`feat:`, `fix:`, `docs:` …).
- Run the five verification commands above before committing; CI reproduces them.
- Don't commit generated noise: `.venv`, `dist`, `__pycache__` are gitignored.

## Orientation

- Canonical recipe for *users'* agents: `SKILL.md`. Per-review-type checklists:
  `checklists/`. Weights: `scoring.json`. Findings contract:
  `findings.schema.json`.
- The scorer lives in `src/bs_score/`; `score.py` is a thin shim for clones.

## Naming

The product, the CLI, the skill and its folder are **`bs-score`**. Identifiers
stay snake_case because they have to: the Python package is `src/bs_score/`
(`import bs-score` is a syntax error), and so are the JSON keys it emits
(`bs_score_version`, the SARIF `bs_score` property). Don't "fix" those.
