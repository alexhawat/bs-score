---
name: bs_score
description: >-
  Use when auditing a repo, PR, branch, PR review, AI skill, or agent config
  for claims vs truth and real defects: follow the canonical bs_score SKILL.md,
  emit findings JSON, then run score.py (higher = more bullshit).
---

# Bullshit Score (`bs_score`) — Hermes

Install: drop this folder into the Hermes skills path. Instruction-only wrapper — run `score.py` from a clone (`BS_SCORE_ROOT`); do not vendor `.py` into Hermes packs.

## Canonical pack

This wrapper lives in [alexhawat/bs_score](https://github.com/alexhawat/bs_score).

1. Read **`SKILL.md` at the repository root** (full two-pass workflow, checklists, prompts).
2. Emit findings JSON matching `findings.schema.json` (no `score` / `points` fields).
3. Score:

```bash
export BS_SCORE_ROOT="${BS_SCORE_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
# If this file was copied out of the repo, set BS_SCORE_ROOT to your clone:
# export BS_SCORE_ROOT="$HOME/bs_score"
python3 "$BS_SCORE_ROOT/score.py" findings.json
```

## What it audits

| `target_kind` | Scope |
|---------------|--------|
| `repo` / `pr` / `branch` | Docs claims **and** deep code |
| `review` | PR review vs diff |
| `skill` | Skill MD + related code |
| `agent` | Agent / persona configs |

## Fixture examples

```bash
python3 "$BS_SCORE_ROOT/score.py" "$BS_SCORE_ROOT/examples/findings.valid.json"   # → 17
python3 "$BS_SCORE_ROOT/score.py" "$BS_SCORE_ROOT/examples/findings.review.json"  # → 8
python3 "$BS_SCORE_ROOT/score.py" "$BS_SCORE_ROOT/examples/findings.skill.json"   # → 5
python3 "$BS_SCORE_ROOT/score.py" "$BS_SCORE_ROOT/examples/findings.agent.json"   # → 4
```

Never invent the score — only report `score.py` output.
