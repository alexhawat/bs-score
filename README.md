# bs_score

**Bullshit Score** — portable eval skill (`@bs_score`). The LLM finds problems; `score.py` scores them. Higher score = more bullshit. Never invent the number — always run the scorer.

## Install

```bash
git clone https://github.com/alexhawat/bs_score.git
cd bs_score
```

Point your agent at `SKILL.md`, or copy this folder into your skills library.

## Score

```bash
# LLM writes findings.json (schema in findings.schema.json — no score field)
python3 score.py findings.json
```

Weights live in `scoring.json` (v1): `breaking_bug` 5, `security_issue` 4, `missing_feature` 3, `bug` 3, `wrong_claim` 2.

## What it audits

| `target_kind` | Scope |
|---------------|--------|
| `repo` / `pr` / `branch` | Docs claims **and** a deep code pass for real bugs |
| `review` | A PR review vs the PR diff |
| `skill` | An AI skill (`SKILL.md` + related code) |
| `agent` | Agent configs (`.cursor/`, `.claude/`, …) |

Repo/PR audits are **two-pass**: claims first, then deep implementation review. Docs-only is incomplete. `score.py` rejects any model-supplied `score` / `points`.

## Layout

```text
.
├── SKILL.md              # agent recipe
├── scoring.json          # type → points
├── findings.schema.json  # findings contract (validated by score.py)
├── score.py              # deterministic scorer
└── examples/             # sample findings
```

## Related

Canonical bots/skills monorepo (pointers): [alexhawat/bots-agents-skills](https://github.com/alexhawat/bots-agents-skills).

## License

MIT
