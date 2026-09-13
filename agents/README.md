# Agent wrappers

Canonical recipe: [`../SKILL.md`](../SKILL.md). Scorer: [`../score.py`](../score.py).

Each subdirectory is a drop-in skill folder for that runtime. They do **not** vendor `score.py` — clone or set `BS_SCORE_ROOT` to this repository root.

```bash
export BS_SCORE_ROOT="/path/to/bs_score"   # this repo
python3 "$BS_SCORE_ROOT/score.py" findings.json
```
