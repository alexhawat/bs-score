---
name: bs_score
description: >-
  Use when auditing a repo, PR, branch, PR review, AI skill (SKILL.md + related
  code), or agent config (.cursor / .claude / similar) for claims vs truth and
  real defects: emit findings JSON, then run score.py (higher = more bullshit).
---

# Bullshit Score (`bs_score`)

Portable **Bullshit Score** eval (`bs_score`) for Grok Bot, Claude, Cursor, OpenCode, ChatGPT, and similar
agents. The LLM **finds** problems; a script **scores** them. Never invent a
score in prose — always run `score.py`.

## Layout

```text
skills/bs_score/
├── SKILL.md              # this recipe
├── scoring.json          # type → points (source of truth for weights)
├── findings.schema.json  # LLM output contract; score.py validates against it
├── score.py              # deterministic scorer
└── examples/             # sample findings + expected usage
```

Canonical publish: [alexhawat/bs_score](https://github.com/alexhawat/bs_score) (this repo).
Thin pointers for Grok Bot / Hermes / OpenClaw live in
[alexhawat/bots-agents-skills](https://github.com/alexhawat/bots-agents-skills)
under `grok_bots/bs_score/`, `hermes/bs_score/`, `openclaw/bs_score/` and
run `score.py` from a clone of **this** repo (no `.py` under hermes/openclaw).

## Score rules (locked)

- Start at **0**. Unbounded sum. **Higher = worse**.
- Points come only from `scoring.json` (v1):

| type | points |
|------|-------:|
| `breaking_bug` | 5 |
| `security_issue` | 4 |
| `missing_feature` | 3 |
| `bug` | 3 |
| `wrong_claim` | 2 |

- Dedupe key: `(type, path)` — first kept, later dropped as `deduped`.
- `confidence` is **display-only** (0–1); does not change points.
- Evidence required: non-empty `path` and `quote`. Missing → `rejected`, not scored.
- Same finding types for every `target_kind`.

## When to use

| `target_kind` | What you audit |
|---------------|----------------|
| `repo` | README/docs **and** a deep pass over primary implementation for real bugs |
| `pr` / `branch` | Diff-focused deep pass; still flag contradicted docs |
| `review` | Existing PR review (body + comments) vs PR diff/code |
| `skill` | An AI skill pack: `SKILL.md` (or equivalent) **and** related scripts/code/helpers it names |
| `agent` | Agent/persona configs under `.cursor/`, `.claude/`, `.codex/`, `AGENTS.md`, `.github/agents/`, Grok Bot profiles, etc. |

## Agent workflow

**The LLM finds; `score.py` scores. Never invent, estimate, or soft-score a
number in prose.** Report only what `score.py` prints.

1. **Map claims** — README/docs/skill/agent/review text: list concrete claims
   (features, paths, CLIs, triggers, guarantees).
2. **Deep code pass (required for repo/pr/branch/skill)** — read the primary
   implementation (not docs alone). Hunt high-evidence defects:
   - logic / state / race bugs
   - missing rollback after side effects (e.g. checkout then cancel)
   - error handling that hides failure
   - security (injection, secrets, unsafe instructions)
   - control-flow that breaks advertised workflows (e.g. finish command unarmed)
3. **Cross-check** — claim vs code → `wrong_claim` / `missing_feature`; pure
   code defects → `bug` / `breaking_bug` / `security_issue`.
4. Emit **only** findings JSON matching `findings.schema.json` — **no `score`
   field**, no `points` on findings.
5. Write the file (e.g. `findings.json`).
6. Run:

```bash
# From this repository (or a clone):
python3 score.py findings.json
# Or with an absolute path:
# python3 /path/to/bs_score/score.py findings.json
```

7. Report **only** the script’s `score`, `by_type`, `kept` / `rejected` /
   `deduped`, plus a short summary of kept findings (paths). If you did a
   docs-only skim, you are not done — go back to step 2.

## Finding object

Required: `id`, `type`, `title`, `path`, `quote`, `target`.

Optional: `claim`, `confidence`.

`target` (where the quote lives): `readme` | `code` | `diff` | `review` | `skill` | `agent` | `other`.

`path`: repo-relative file (`SKILL.md:40`, `scripts/run.py:12`, `.cursor/agents/foo.md`),
diff hunk id, or review locator (`pull/<n>/reviews/<id>[#suffix]`).

## Prompt sketches

### Repo

```text
Audit this repository in TWO passes, then emit findings JSON only.

Pass A — Claims: README/docs/marketing vs implementation (wrong_claim,
missing_feature).

Pass B — Deep code (required): read primary source (entrypoints, core modules).
Look for real bugs with path+quote: state/session bugs, side effects without
rollback on cancel, broken advertised finish flows, error swallowing,
security issues. Do NOT stop after Pass A.

Return JSON only: { "version": 1, "target_kind": "repo", "target_ref": "<name>",
"findings": [ ... ] } matching findings.schema.json.
Types: breaking_bug, security_issue, missing_feature, wrong_claim, bug.
Every finding needs path + quote. NO score or points fields — score.py scores.
```

### PR / branch

Same schema with `"target_kind": "pr"` or `"branch"`. Same two passes; Pass B
focuses on the changed files and their callers. Still flag contradicted docs.

### PR review

```text
Evaluate this pull-request review against the PR diff and code.
Inputs: review body + inline comments, plus the PR files/diff (name-only list).
Return JSON only: { "version": 1, "target_kind": "review",
"target_ref": "<owner/repo#pr review:id>", "findings": [ ... ] }
matching findings.schema.json.

Checklist (high-evidence only):
1) Scope labels — "change-scoped" / "in this PR" vs PR file list; out-of-diff
   .venv/runner paths → wrong_claim.
2) Severity inflation — "never read"/coverage as Critical/Major → wrong_claim.
3) Internal contradictions — e.g. analyzer "passed" vs findings of that class.
4) Hollow verification / false findings / missed real defects (hard evidence).
5) Do NOT score accurate findings the review got right.

Volume: one finding per failure mode; exemplar quote + count in title/claim.
Distinct path suffixes (#change-scoped, #never-read, #analyzer-contradiction).
Types allowed: breaking_bug, security_issue, missing_feature, wrong_claim, bug.
Every finding needs path + quote. No score field.
```

### AI skill

```text
Audit this AI skill pack. Read SKILL.md (or skill.md / recipe MD) and every
script, tool wrapper, schema, or helper it references.
Return JSON only: { "version": 1, "target_kind": "skill",
"target_ref": "<path-or-name>", "findings": [ ... ] }.

Checklist:
1) wrong_claim — skill MD asserts a step, path, CLI, tool, or outcome the
   related code does not do (or does differently).
2) missing_feature — skill advertises a capability with no implementation
   (missing script, stub, dead link, empty handler).
3) bug / breaking_bug / security_issue — real defects in skill-related code
   the MD implies is safe/correct.
4) Hollow "always" / "never" / "automatically" claims without code support.
5) Frontmatter description vs body vs code — contradictions count.
6) Do not invent missing files; if a referenced path is absent, that is
   missing_feature or wrong_claim with quote from the MD reference.

Use target "skill" for MD quotes, "code" for scripts. Prefer fewer
high-evidence findings. No score field.
```

### Agent config (.cursor / .claude / similar)

```text
Audit this agent (or a directory of agents). Typical roots:
  .cursor/agents/, .cursor/rules/, .claude/agents/, .claude/, AGENTS.md,
  .codex/, .github/agents/, grok bot profile.md / persona files.
Return JSON only: { "version": 1, "target_kind": "agent",
"target_ref": "<path-or-name>", "findings": [ ... ] }.

Checklist:
1) wrong_claim — persona claims tools, skills, connectors, repos, or powers
   not wired (missing skill files, wrong paths, tools not in allowlist).
2) missing_feature — "owns X" / "always does Y" with no routine, skill, or
   script backing it.
3) Internal contradictions — agent A forbids what agent B requires; same file
   says both "never push" and "auto-push".
4) security_issue — instructs exfiltrating secrets, bypassing auth, or
   disabling safety without a documented human gate (quote the line).
5) Phantom dependencies — references skills/MCPs/paths that do not exist in
   the workspace.
6) When scoring a folder, one finding per failure mode per agent file unless
   a shared root config is the single source; use distinct paths.

Use target "agent" for persona/config quotes, "skill"/"code" when the
contradiction is in a linked skill or script. No score field.
```

## Hard rules

- Do not add finding types that are absent from `scoring.json`.
- Do not soft-score, rescale, or invent a numeric score — **only `score.py`**.
- Findings JSON must not contain `score` or `points` (`score.py` rejects them).
- Do not treat rejected findings as scored.
- Prefer fewer high-evidence findings over speculative noise — but **docs-only
  audits are incomplete** for `repo` / `pr` / `branch` / `skill`.
- For `review`: one finding per failure mode; never score a verified-true review finding.
- For `skill` / `agent`: always read the MD **and** related code/config graph.
