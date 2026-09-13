# Agent wrappers

Canonical recipe: [`../SKILL.md`](../SKILL.md). Scorer: [`../score.py`](../score.py)
or the packaged `bs-score` command.

Each subdirectory is a drop-in skill folder for one runtime. None of them vendor
the scorer, and none of them need to — it runs without a clone:

```bash
uvx --from git+https://github.com/alexhawat/bs_score bs-score findings.json --repo-root .
```

These files are **generated** by [`../scripts/gen_agent_wrappers.py`](../scripts/gen_agent_wrappers.py).
Edit the template there, not the wrappers; `tests/test_wrappers.py` fails on drift.
