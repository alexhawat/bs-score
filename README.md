# bs_score

**Bullshit Score** — a portable audit skill (`@bs_score`) for any coding agent.

The LLM **finds** defects and quotes the evidence. `bs-score` **verifies every
quote against the artifact it names**, then scores what survived. Higher = more
bullshit. The number comes from the scorer, never from prose.

A fabricated audit scores **0**, because none of its quotes exist:

```bash
uv run bs-score examples/findings.hallucinated.json --repo-root examples/fixture-repo
# → score 0 — 4 rejected: quote_not_found ×3, path_not_found ×1
```

Works with Claude Code, Cursor, Codex, Grok Bot, OpenCode, Hermes, OpenClaw, and
anything else that can follow a skill file and run a command.

## Install

No clone needed to score:

```bash
uvx --from git+https://github.com/alexhawat/bs_score bs-score findings.json --repo-root .
```

Once the package is published, `uvx bs-score findings.json --repo-root .` is the
short form.

For the skill itself, point your agent at [`SKILL.md`](SKILL.md), or copy a
per-runtime wrapper from [`agents/`](agents/) into your skills library
(`~/.claude/skills/bs_score`, a Cursor skills path, …).

From a clone:

```bash
git clone https://github.com/alexhawat/bs_score.git && cd bs_score
uv sync --extra dev
uv run bs-score examples/findings.valid.json --repo-root examples/fixture-repo
```

`python3 score.py findings.json` still works from a checkout.

## What it audits

| `target_kind` | What you point it at | Checklist |
|---------------|----------------------|-----------|
| `repo` | README claims **and** a deep code pass | [repo](checklists/repo.md) |
| `pr` / `branch` | A diff and its callers | [pr](checklists/pr.md) |
| `review` | An existing PR review, graded against the diff | [review](checklists/review.md) |
| `skill` | A skill pack: `SKILL.md` + every script it names | [skill](checklists/skill.md) |
| `agent` | Agent/persona configs (`.cursor/`, `.claude/`, `AGENTS.md`, …) | [agent](checklists/agent.md) |
| `prompt` | One or many prompts — system, developer, tool, persona | [prompt](checklists/prompt.md) |

## How the score is made honest

| Mechanism | What it stops |
|-----------|---------------|
| **Evidence verification** | Findings whose quote is not in the named artifact are rejected before scoring. Hallucinating costs points instead of earning them. |
| **Content-addressed dedupe** | The key is `(type, canonical file, quote fingerprint)`. `src/a.py:10`, `./src/a.py:11` and `src/a.py` are one finding, not three. |
| **Cross-path clustering** | One copy-pasted defect in seven files is one finding with seven `occurrences`. |
| **Full schema enforcement** | Types, enums, `minLength`, and numeric bounds — not just required keys. Cross-checked against `jsonschema` in CI. |
| **Pinned weights** | `--scoring` needs `--allow-custom-scoring`; weights must be non-negative integers. Every report carries `scoring_sha256` and `schema_sha256`. |
| **Per-finding rejection** | One malformed finding is rejected on its own; it no longer discards the whole audit. |
| **Exit codes** | `--fail-over N` exits 1 so a CI job can gate on a score. |

## Scoring

One score. Start at **0**, unbounded sum, **higher = worse**. The five finding
types are fixed; the weights depend on the review type, because the same defect
does not cost the same everywhere.

| type | meaning | `repo` | `pr` `branch` | `review` | `skill` | `agent` | `prompt` |
|------|---------|-------:|--------------:|---------:|--------:|--------:|---------:|
| `breaking_bug` | Crash, wrong result, data loss, dead workflow | 5 | 6 | 6 | 5 | 4 | 4 |
| `security_issue` | Auth, injection, secrets, unsafe instructions | 4 | 5 | 5 | 4 | 5 | 5 |
| `missing_feature` | Asserted capability with no implementation | 3 | 2 | 3 | 4 | 3 | 2 |
| `bug` | Incorrect behaviour, not catastrophic | 3 | 3 | 4 | 3 | 2 | 3 |
| `wrong_claim` | A claim the artifact contradicts | 2 | 2 | 3 | 3 | 3 | 3 |

Why they differ: a `pr` is a gate, so landing defects outweigh doc drift. A
`review` is graded on its claims, and a real defect it missed costs more than a
mislabelled one. A `skill` that advertises a capability it does not have is the
defining skill failure. An `agent` or a `prompt` is an instruction surface, so
unsafe instructions weigh most.

Weights live in [`scoring.json`](scoring.json). `confidence` is display-only.

## Worked examples

Every number below is produced by the committed fixtures and asserted in CI.
The artifacts the quotes point at live in `examples/fixture-*`, so verification
has something real to check.

| example | review type | score | shows |
|---------|-------------|------:|-------|
| `findings.valid.json` | `repo` | **17** | README lies + real bugs; one duplicate merged, one blank-evidence finding rejected |
| `findings.review.json` | `review` | **10** | False claim, hollow "verified", a defect the review missed |
| `findings.skill.json` | `skill` | **7** | SKILL.md names a script that does not exist; documents the wrong flag |
| `findings.agent.json` | `agent` | **6** | Phantom skill; "never push" next to "auto-push to main" |
| `findings.prompt.json` | `prompt` | **18** | Injection surface, a token in the prompt, two self-contradictions, unspecified output |
| `findings.hallucinated.json` | `repo` | **0** | Four confident fabrications, all rejected |

```bash
uv run bs-score examples/findings.valid.json  --repo-root examples/fixture-repo
uv run bs-score examples/findings.review.json --repo-root examples/fixture-repo \
    --sources examples/fixture-review/review.json
uv run bs-score examples/findings.skill.json  --repo-root examples/fixture-repo
uv run bs-score examples/findings.agent.json  --repo-root examples/fixture-repo
uv run bs-score examples/findings.prompt.json --repo-root . --sources examples/fixture-prompts
uv run bs-score examples/findings.hallucinated.json --repo-root examples/fixture-repo
```

Each writes the same report as the committed `examples/score.*.json` receipt.

## Auditing prompts

`--sources` makes non-file evidence addressable, so prompts get verified like
code. Point it at a directory of prompt files, a `{"sources": [{"id", "text"}]}`
manifest, a `.jsonl` stream, or a single file:

```bash
uvx --from git+https://github.com/alexhawat/bs_score bs-score findings.json --sources prompts/
```

Findings then use `prompt:<id>` or `prompt:<id>:<line>` locators, where `<id>` is
the file's relative path (or its stem, when unambiguous). The same mechanism
carries PR review bodies, which are not files either.

## CLI

```text
bs-score FINDINGS [--repo-root DIR] [--sources PATH ...] [--no-verify]
                  [--require-evidence] [--strict-lines] [--line-window N]
                  [--fail-over N] [--format json|md] [-o FILE]
                  [--scoring FILE --allow-custom-scoring] [-v|-q]
```

| flag | effect |
|------|--------|
| `--repo-root` | Tree that file locators resolve against (default: `.`) |
| `--sources` | Prompt files, review bodies — anything not in the tree. Repeatable |
| `--no-verify` | Skip verification; the report is stamped `skipped` |
| `--require-evidence` | Also reject findings that could not be checked at all |
| `--strict-lines` | Reject a real quote filed at the wrong line |
| `--fail-over N` | Exit 1 when the score exceeds N |
| `--format md` | Print a Markdown summary instead of JSON |

Exit codes: `0` scored and within threshold · `1` over `--fail-over` · `2`
unusable input.

## Agent workflow

1. Map the claims the artifact makes.
2. Deep-read the implementation (required for `repo` / `pr` / `branch` / `skill`).
3. Cross-check, and quote the evidence **verbatim and contiguously**.
4. Emit findings JSON only — [`findings.schema.json`](findings.schema.json), no
   `score`, no `points`.
5. `bs-score findings.json --repo-root .`
6. Report only what the script printed.

Full recipe and hard rules: [`SKILL.md`](SKILL.md). Per-review-type checklists:
[`checklists/`](checklists/).

## Layout

```text
.
├── SKILL.md              # canonical agent recipe
├── checklists/           # one per review type
├── scoring.json          # review type → weights
├── findings.schema.json  # findings contract, enforced in full
├── src/bs_score/         # the scorer
├── score.py              # `python3 score.py` shim for clones
├── examples/             # findings, receipts, and the artifacts they quote
├── agents/               # per-runtime wrappers (generated)
└── scripts/              # wrapper generator
```

## Agents

| Runtime | Folder |
|---------|--------|
| Claude Code | [`agents/claude`](agents/claude/) |
| Cursor | [`agents/cursor`](agents/cursor/) |
| Codex | [`agents/codex`](agents/codex/) |
| Grok Bot | [`agents/grok`](agents/grok/) |
| Hermes | [`agents/hermes`](agents/hermes/) |
| OpenClaw | [`agents/openclaw`](agents/openclaw/) |
| OpenCode | [`agents/opencode`](agents/opencode/) |

Wrappers are generated by [`scripts/gen_agent_wrappers.py`](scripts/gen_agent_wrappers.py);
CI fails if a committed wrapper drifts from the template.

## Development

```bash
uv sync --extra dev
uv run pytest
uv run ruff check .
uv run python scripts/gen_agent_wrappers.py --check   # wrappers are generated
uv run python scripts/check_receipts.py               # receipts reproduce exactly
```

Releasing: `uv build && uv publish`. Until then, the git form above is the
install-free command.

## License

MIT
