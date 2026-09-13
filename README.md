# bs_score

**Bullshit Score** — portable eval skill (`@bs_score`) for any coding agent.

The LLM **finds** problems (with path + quote). `score.py` **scores** them. Higher = more bullshit. Never invent the number in prose — always run the scorer.

Works with Grok Bot, Claude Code, Cursor, Codex, OpenCode, ChatGPT, Hermes, OpenClaw, and anything else that can follow a skill file and run Python.

## Install

```bash
git clone https://github.com/alexhawat/bs_score.git
cd bs_score
```

Point your agent at `SKILL.md`, or copy this folder into your skills library (`~/.claude/skills/`, Cursor skills, etc.).

Thin pointers for Grok / Hermes / OpenClaw live in
[alexhawat/bots-agents-skills](https://github.com/alexhawat/bots-agents-skills)
(`grok_bots/bs_score`, `hermes/bs_score`, `openclaw/bs_score`).

## What it does

- Audits a **whole repo** (README claims **and** a deep code pass)
- Audits a **PR** or **branch** (diff-focused, still flags contradicted docs)
- Audits a **PR review** vs the PR diff (scope labels, severity inflation, analyzer contradictions, hollow “verified”)
- Audits an **AI skill** (`SKILL.md` + every script/helper it names)
- Audits an **agent config** (`.cursor/`, `.claude/`, `.codex/`, `AGENTS.md`, Grok Bot personas, …)
- Emits findings JSON only — `score.py` is the sole source of the numeric score
- Rejects missing evidence, unknown keys, and any model-supplied `score` / `points`
- Dedupes on `(type, path)`; `confidence` is display-only

## Quick usage

```bash
# 1) Agent writes findings.json (schema: findings.schema.json — no score field)
# 2) Score it:
python3 score.py findings.json
```

Example (fixture in this repo):

```bash
python3 score.py examples/findings.valid.json
# → score 17  (breaking_bug 5 + security_issue 4 + missing_feature 3 + bug 3 + wrong_claim 2)
```

## Scoring (locked v1)

Starts at **0**. Unbounded sum. **Higher = worse.**

| type | points | meaning |
|------|-------:|---------|
| `breaking_bug` | 5 | Crash, wrong result, or data loss |
| `security_issue` | 4 | Auth, injection, secrets, privilege |
| `missing_feature` | 3 | Claimed in docs/skill but not implemented |
| `bug` | 3 | Incorrect behavior, not catastrophic |
| `wrong_claim` | 2 | Docs/review/agent claim contradicted by code |

Weights live in `scoring.json`. Evidence required: non-empty `path` + `quote`, or the finding is `rejected`.

## Target kinds

| `target_kind` | Two-pass claims + deep code? | Typical use |
|---------------|:----------------------------:|-------------|
| `repo` | **yes** | Open-source / product honesty audit |
| `pr` / `branch` | **yes** (diff-focused) | Pre-merge smell check |
| `review` | review vs diff | Grade an AI or human PR review |
| `skill` | **yes** (MD + related code) | Skill pack hygiene |
| `agent` | config + linked skills | Persona / agent-folder hygiene |

Docs-only for repo/pr/branch/skill is **incomplete**.

## Feature examples

### 1) Repo: README lies + real bugs

`examples/findings.valid.json` → `score` **17**

Kept findings include:

| type | example |
|------|---------|
| `wrong_claim` | README says “OAuth2 out of the box”; only API keys exist |
| `missing_feature` | Docs advertise `/v1/stream`; no implementation |
| `bug` | Off-by-one in pagination |
| `security_issue` | SQL built with an f-string |
| `breaking_bug` | `delete_user` ignores ownership |

One duplicate `(bug, path)` is **deduped**; a finding with empty path/quote is **rejected**.

```bash
python3 score.py examples/findings.valid.json
# compare to examples/score.valid.json
```

### 2) PR review: false / hollow review

`examples/findings.review.json` → `score` **8**

| type | example |
|------|---------|
| `wrong_claim` | Review claims NPE; call site always passes non-null |
| `missing_feature` | “Verified: no secrets” with no secret-related checks |
| `bug` | Review missed an off-by-one that is in the PR diff |

True findings the review got right are **not** scored (skill rule).

```bash
python3 score.py examples/findings.review.json
```

### 3) Skill pack: MD vs scripts

`examples/findings.skill.json` → `score` **5**

| type | example |
|------|---------|
| `missing_feature` | SKILL.md says run `scripts/deploy.sh`; file absent |
| `wrong_claim` | SKILL.md documents `--prod`; script only accepts `--environment` |

```bash
python3 score.py examples/findings.skill.json
```

### 4) Agent config: phantom skills / contradictions

`examples/findings.agent.json` → `score` **4**

| type | example |
|------|---------|
| `wrong_claim` | Agent says “always run `@deploy-prod`”; skill not in workspace |
| `wrong_claim` | Same file: “Never push” and “Auto-push to main” |

```bash
python3 score.py examples/findings.agent.json
```

## Agent workflow (summary)

1. Map claims (README / skill / agent / review text).
2. Deep-read primary implementation (required for repo/pr/branch/skill).
3. Cross-check → emit findings JSON only (`findings.schema.json`).
4. `python3 score.py findings.json`
5. Report **only** what the script printed: `score`, `by_type`, `kept` / `rejected` / `deduped`.

Full recipe, checklists, and prompt sketches: [`SKILL.md`](SKILL.md).

## Layout

```text
.
├── SKILL.md              # agent recipe (all runtimes)
├── scoring.json          # type → points
├── findings.schema.json  # findings contract (validated by score.py)
├── score.py              # deterministic scorer
└── examples/             # sample findings + score receipts
```

## Related

- Monorepo pointers: [alexhawat/bots-agents-skills](https://github.com/alexhawat/bots-agents-skills)
- Live skill in Grok Bot fleet: tag `bs_score` / [bs-score](https://github.com/alexhawat/bots-agents-skills)

## License

MIT
