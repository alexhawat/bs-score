---
name: bs_score
description: >-
  Use when auditing a repo, PR, branch, PR review, AI skill, agent config, or one
  or more prompts for claims vs truth and real defects: follow the canonical
  bs_score SKILL.md, emit findings JSON, then run bs-score (higher = more
  bullshit).
allowed-tools: Read, Grep, Glob, Bash
license: MIT
---

# Bullshit Score (`bs_score`) — Claude Code

Copy or symlink this folder to `~/.claude/skills/bs_score` (personal) or `.claude/skills/bs_score` (project). The slash command comes from the directory name, so keep it `bs_score`.

## Canonical pack

This wrapper belongs to [alexhawat/bs_score](https://github.com/alexhawat/bs_score).

1. Read **`SKILL.md` at the repository root** — the two-pass workflow, the
   per-review-type checklists, and the hard rules live there.
2. Emit findings JSON matching `findings.schema.json` (no `score` / `points`).
3. Score it. No clone and no `PYTHONPATH` required:

```bash
uvx --from git+https://github.com/alexhawat/bs_score bs-score findings.json --repo-root .
```

(Once the package is published, `uvx bs-score …` is the short form.)

Quotes are verified against the files they name before anything is scored, so
`--repo-root` must point at the tree you audited. For prompts and review bodies,
add `--sources` (`bs-score` below is the same command):

```bash
bs-score findings.json --sources prompts/                    # prompt audit
bs-score findings.json --repo-root . --sources review.json   # review audit
```

From a clone, `python3 score.py findings.json` and `uv run bs-score …` do the same thing.

## What it audits

| `target_kind` | Scope | Weight profile |
|---------------|-------|----------------|
| `repo` | Docs claims **and** deep code | baseline |
| `pr` / `branch` | The diff and its callers | landing defects weigh more |
| `review` | A PR review vs the diff | false claims and misses weigh more |
| `skill` | Skill MD + the code it names | unimplemented claims weigh more |
| `agent` | Agent / persona configs | unsafe instructions weigh most |
| `prompt` | One or more prompts | injection and secrets weigh most |

## Fixture examples

Run from a clone of the repo:

```bash
uv run bs-score examples/findings.valid.json  --repo-root examples/fixture-repo   # 17
uv run bs-score examples/findings.review.json --repo-root examples/fixture-repo \
    --sources examples/fixture-review/review.json                                # 10
uv run bs-score examples/findings.skill.json  --repo-root examples/fixture-repo   # 7
uv run bs-score examples/findings.agent.json  --repo-root examples/fixture-repo   # 6
uv run bs-score examples/findings.prompt.json --sources examples/fixture-prompts  # 18
uv run bs-score examples/findings.hallucinated.json \
    --repo-root examples/fixture-repo                                            # 0
```

That last one is the point: a fabricated audit scores zero because none of its
quotes exist.

Never invent the score — report only what `bs-score` printed.
