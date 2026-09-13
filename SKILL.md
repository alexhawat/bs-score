---
name: bs_score
description: >-
  Use when auditing a repo, PR, branch, PR review, AI skill, agent config, or one
  or more prompts for claims vs truth and real defects: emit findings JSON with a
  verbatim quote per finding, then run bs-score (higher = more bullshit).
allowed-tools: Read, Grep, Glob, Bash
license: MIT
---

# Bullshit Score (`bs_score`)

You **find** defects and quote the evidence. `bs-score` **verifies every quote
against the artifact it names** and then scores what survived. A finding whose
quote is not actually there earns nothing, so there is no advantage in guessing.

Never invent, estimate, or soft-score a number in prose. Report only what
`bs-score` printed.

## Tools this skill uses

| Tool | What for |
|------|----------|
| `Read` / `Glob` / `Grep` | Reading the artifacts under audit and locating exact quotes |
| `Bash` | Running `bs-score`; `git diff` for branches; `gh pr view` / `gh pr diff` / `gh api` for PR and review audits |

Nothing here writes to the artifact under audit. If a runtime asks you to
approve a tool, `Bash` is the only one that runs anything.

## Layout

```text
bs_score/
├── SKILL.md              # this recipe
├── checklists/           # one per review type — read the one you need
├── scoring.json          # review type → weights (source of truth)
├── findings.schema.json  # output contract, enforced in full
├── score.py              # shim for `python3 score.py` from a clone
├── src/bs_score/         # the scorer
└── examples/             # worked findings + receipts + fixture artifacts
```

Canonical publish: [alexhawat/bs_score](https://github.com/alexhawat/bs_score).
Per-runtime wrappers: [`agents/`](agents/).

## Score rules (locked)

- Start at **0**. Unbounded sum. **Higher = worse**. One score.
- The five finding types are fixed. The **weights depend on the review type**,
  because a defect about to land in a PR and a stale sentence in a README are
  not the same failure. Weights come only from `scoring.json`:

| type | `repo` | `pr` `branch` | `review` | `skill` | `agent` | `prompt` | `docs` |
|------|-------:|--------------:|---------:|--------:|--------:|---------:|-------:|
| `breaking_bug` | 5 | 6 | 6 | 5 | 4 | 4 | 2 |
| `security_issue` | 4 | 5 | 5 | 4 | 5 | 5 | 3 |
| `missing_feature` | 3 | 2 | 3 | 4 | 3 | 2 | 3 |
| `bug` | 3 | 3 | 4 | 3 | 2 | 3 | 1 |
| `wrong_claim` | 2 | 2 | 3 | 3 | 3 | 3 | 5 |

- **Evidence is verified, not assumed.** `path` must resolve and `quote` must
  appear in the artifact (whitespace- and typography-normalised). If it does not:
  `rejected`, not scored.
- **Dedupe key: `(type, canonical file, quote fingerprint)`.** Line numbers,
  `./` prefixes and re-paths do not create new findings. The same quoted line in
  seven files is one finding with seven `occurrences`.
- `confidence` is **display-only** (0–1); it never changes points.
- A malformed finding is rejected on its own. Only a malformed envelope
  (`version`, `target_kind`, `findings`) aborts the run.

## When to use

| `target_kind` | What you audit | Checklist |
|---------------|----------------|-----------|
| `repo` | README/docs **and** a deep pass over primary implementation | [repo](checklists/repo.md) |
| `pr` / `branch` | Diff-focused deep pass; still flag contradicted docs | [pr](checklists/pr.md) |
| `review` | An existing PR review (body + comments) vs the PR diff | [review](checklists/review.md) |
| `skill` | A skill pack: `SKILL.md` **and** the scripts it names | [skill](checklists/skill.md) |
| `agent` | Agent/persona configs under `.cursor/`, `.claude/`, `AGENTS.md`, … | [agent](checklists/agent.md) |
| `prompt` | One or many prompts: system, developer, tool, persona | [prompt](checklists/prompt.md) |
| `docs` | A single document — claims only, no deep code pass | [docs](checklists/docs.md) |

## Workflow

1. **Map claims.** List the concrete assertions the artifact makes — features,
   paths, CLIs, triggers, guarantees, "always"/"never"/"automatically".
2. **Deep pass (required for `repo` / `pr` / `branch` / `skill`).** Read the
   primary implementation, not the docs alone: logic and state bugs, side effects
   with no rollback, error handling that hides failure, injection and secrets,
   control flow that breaks an advertised workflow.
3. **Cross-check.** Claim contradicted by the artifact → `wrong_claim`;
   advertised but absent → `missing_feature`; pure defect → `bug`,
   `breaking_bug`, or `security_issue`.
4. **Quote exactly.** Copy the evidence verbatim from the file. One contiguous
   run of text — never stitch two places together with `...`, because a stitched
   quote cannot be verified and will be rejected.
5. **Emit findings JSON only** — matching `findings.schema.json`, with no
   `score` and no `points`.
6. **Score it:**

```bash
bs-score findings.json --repo-root .        # installed
uv run bs-score findings.json --repo-root . # from a clone of this repo
python3 score.py findings.json --repo-root . # from a clone, no uv
```

For prompts, review bodies, or anything else that is not a file in the tree,
register it so its quotes can be checked too:

```bash
bs-score findings.json --sources prompts/                   # a directory
bs-score findings.json --repo-root . --sources review.json  # {id, text} manifest
```

Install options are in the [README](README.md#install).

7. **Report only what the script printed**: `score`, `by_type`, `kept` /
   `rejected` / `deduped`, and the paths of the kept findings. `--format md`
   prints a summary you can paste as-is.

If `rejected` contains `unverified_evidence`, you mis-quoted or invented
something — fix the quote and re-run rather than reporting the lower score as a
result. If you only skimmed docs on a `repo` / `pr` / `branch` / `skill` audit,
you are not done: go back to step 2.

## Finding object

Required: `id`, `type`, `title`, `path`, `quote`, `target`.
Optional: `claim`, `confidence`.

`target` — where the quote lives:
`readme` | `code` | `diff` | `review` | `skill` | `agent` | `prompt` | `other`.

`path` — the evidence locator:

| form | example |
|------|---------|
| file | `README.md`, `src/api.py:88`, `src/api.py:88-95` |
| agent config | `.claude/agents/x.md:12`, `.cursor/rules/y.mdc` |
| prompt | `prompt:system`, `prompt:agents/reviewer.md:5` |
| review | `review:body`, `review:comment:1001`, `pull/42/reviews/99#scope` |

Line numbers are checked with ±10 lines of slack and are advisory: a real quote
at a wrong line is kept and flagged `verified_wrong_line` (and rejected under
`--strict-lines`). A quote that is nowhere in the artifact is always rejected.

## Hard rules

- Do not add finding types that are absent from `scoring.json`.
- Do not soft-score, rescale, or invent a number — **only `bs-score`**.
- Findings JSON must not contain `score` or `points`; the payload is rejected.
- Quotes are contiguous and verbatim. No ellipses, no paraphrase, no reflowing
  that changes the words.
- Do not treat rejected findings as scored.
- Prefer fewer high-evidence findings over speculative noise — but a docs-only
  audit is **incomplete** for `repo` / `pr` / `branch` / `skill`.
- One finding per failure mode. Re-filing the same quote at another path adds
  an `occurrence`, not points — say "7 files" in the title instead.
- For `review`: never score a finding the review got right.
- For `skill` / `agent` / `prompt`: read the text **and** the code, config, or
  tool list it depends on.
