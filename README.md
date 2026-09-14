# bs-score

[![ci](https://github.com/alexhawat/bs_score/actions/workflows/ci.yml/badge.svg)](https://github.com/alexhawat/bs_score/actions/workflows/ci.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![python: 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](pyproject.toml)

**An LLM finds the defects and quotes the evidence. The `bs-score` CLI verifies
every quote against the artifact it names, then scores what survived.** Higher =
more bullshit. A fabricated audit is **NOT_VALID** (not a clean 0), because none of its quotes verified.

Point it at a repo (README vs code), a PR, a PR review, a skill, an agent config,
or a prompt.

## Install

Two pieces: the **skill** (the recipe your agent follows) and the **`bs-score`
command** (what verifies and scores what it emits).

**1. The command** — one line, every runtime:

```bash
uv tool install git+https://github.com/alexhawat/bs_score   # puts bs-score on PATH
```

**2. The skill** — clone this repository into your runtime's skills folder, so
the root `SKILL.md` and the `checklists/` it links to land together. The folder
name is the skill's name, so keep it `bs-score`:

```bash
git clone --depth 1 https://github.com/alexhawat/bs_score ~/.claude/skills/bs-score
```

| Runtime | Personal (every project) | Project (checked in) |
|---------|--------------------------|----------------------|
| Claude Code | `~/.claude/skills/bs-score` | `.claude/skills/bs-score` |
| Cursor | `~/.cursor/skills/bs-score` | `.cursor/skills/bs-score` |
| Codex | `~/.codex/skills/bs-score` | `.agents/skills/bs-score` |
| OpenCode | `~/.config/opencode/skills/bs-score` | `.opencode/skills/bs-score` |
| Grok Build | `~/.grok/skills/bs-score` | `.grok/skills/bs-score` |
| OpenClaw | `~/.openclaw/skills/bs-score` | `<workspace>/skills/bs-score` |
| Hermes | `~/.hermes/skills/bs-score` | `skills/bs-score` |
| Anything else | `~/.agents/skills/bs-score` | `.agents/skills/bs-score` |

`.agents/skills/` is the cross-runtime convention — Codex, OpenCode, Grok Build
and OpenClaw all read it, so one clone there covers the four at once. Per-runtime
wrapper folders live under [`agents/`](agents/) for anyone who keeps the clone
elsewhere; they point back at the root `SKILL.md` rather than duplicating it.

Or skip all of it and paste this at your agent:

```text
Add the bs-score skill from https://github.com/alexhawat/bs_score and learn how to use it.
```

<details>
<summary>Other ways to get the command</summary>

- `uvx --from git+https://github.com/alexhawat/bs_score bs-score …` — no install,
  resolved per run. CI runs that exact command against every commit
  (`uvx-install` job), so it is proven, not promised.
- From a clone: `uv sync`, then `uv run bs-score …` — or `python3 score.py …`,
  which needs no uv and no network.
- `uvx bs-score` (no `--from`) will work after the planned PyPI release; today it
  has nothing to fetch.

</details>

LLM-facing context files: [`llms.txt`](llms.txt) (index) and
[`llms-full.txt`](llms-full.txt) (the whole recipe, weights, and schema in one
fetch).

## 30-second demo

An auditor that made everything up, scored from a clone
(`git clone https://github.com/alexhawat/bs_score bs-score && cd bs-score && uv sync`):

```console
$ bs-score examples/findings.hallucinated.json --repo-root examples/fixture-repo --format md
## Bullshit Score: **NOT_VALID** (NOT_VALID)

- review type: `repo` (profile `repo`)
- target: `examples/fixture-repo (fabricated audit)`
- kept 0 · rejected 4 · deduped 0 · baselined 0
- evidence: verified (path_not_found 1, quote_not_found 3)
- depth: **unreported** — no `audit.files_read` block, so depth is unverifiable
- blast radius: 0 file(s) affected across 10 scanned
- scoring `30ad8b532c34` · schema `991705a46093`

### Rejected (not scored)

- `h1` — unverified_evidence: quote_not_found: quote is not present in src/api.py
- `h2` — unverified_evidence: path_not_found: src/config.py does not exist
- `h3` — unverified_evidence: quote_not_found: quote is not present in README.md
- `h4` — unverified_evidence: quote_not_found: quote is not present in src/users.py
```

Hallucinating earns nothing: a finding whose quote is not there is rejected, not
scored — four confident fabrications add up to zero. For what a *real* report
looks like, run `bs-score examples/findings.valid.json --repo-root
examples/fixture-repo --format md` (it scores 17).

## What it catches

**Wrong information first** — that is the focus:

- **README lies** — features, paths, flags, and version requirements the
  project does not have.
- **Phantom features** — capabilities asserted with no implementation behind
  them.
- **Stale docs** — quick-starts that cannot run as printed, drifted numbers,
  dead links.
- **Fabricated review claims** — "verified, no secrets" that nobody checked;
  praise for code that does the opposite.

Then the classics: logic and state bugs, injection and secrets, broken
control flow, unsafe instructions in agent configs and prompts.

The `bs-score claims <doc>` subcommand catches the mechanical slice of this
**with no LLM at all** — paths, entry points, CLI flags, version strings,
Markdown links, and fenced code blocks are checked deterministically, and
`--emit-findings` turns each failure into a pre-verified `wrong_claim`.

## What it audits

| `target_kind` | What you point it at | Checklist |
|---------------|----------------------|-----------|
| `repo` | README claims **and** a deep code pass | [repo](checklists/repo.md) |
| `pr` / `branch` | A diff and its callers | [pr](checklists/pr.md) |
| `review` | An existing PR review, graded against the diff | [review](checklists/review.md) |
| `skill` | A skill pack: `SKILL.md` + every script it names | [skill](checklists/skill.md) |
| `agent` | Agent/persona configs (`.cursor/`, `.claude/`, `AGENTS.md`, …) | [agent](checklists/agent.md) |
| `prompt` | One or many prompts — system, developer, tool, persona | [prompt](checklists/prompt.md) |
| `docs` | A single document — claims vs what exists, no code pass | [docs](checklists/docs.md) |

## Why you can trust the number

| Mechanism | What it stops |
|-----------|---------------|
| **Evidence verification** | A quote not present in the named artifact is rejected before scoring. If findings were submitted but **nothing verified**, the run is **NOT_VALID** — not a clean score of 0. |
| **Content-addressed dedupe** | `(type, canonical file, quote fingerprint)` is one finding, whether filed as `src/a.py:10`, `./src/a.py:11`, or copy-pasted into seven files. |
| **Pinned weights** | Custom weights need `--allow-custom-scoring`; every report carries `scoring_sha256` + `schema_sha256`, and receipts reproduce byte-for-byte in CI. |
| **Full schema enforcement** | Types, enums, `minLength`, numeric bounds — cross-checked against `jsonschema`; one malformed finding is rejected on its own. |
| **Root-cause clustering** | Findings sharing a `cluster` id collapse into one charge even when the wording differs in each place, so one defect cannot be filed three ways for triple the points. |
| **Measured blast radius** | Every verified quote is swept across the tree, so `files_affected` is counted by the scorer rather than claimed by the model. |
| **Audit-depth check** | `audit.files_read` is checked against the tree: a docs-only pass is stamped `shallow`, and a listed file that does not exist earns no credit. |

## Counting, clustering, and depth

Three mechanisms keep the score from depending on how hard the model looked.
Every verified quote is **swept across the tree**, so `files_affected` is
measured rather than claimed — file the defect once and the report says it is in
twenty-six files. Findings sharing a `cluster` id **collapse into one charge**,
so a root cause worded three ways costs its points once. And a payload's
`audit.files_read` is **checked against the tree**, so a docs-only pass is
stamped `shallow` and a listed file that does not exist earns no credit;
`--require-depth` turns that into a non-zero exit.

Details, including the `--require-depth` truth table:
[`docs/counting-and-depth.md`](docs/counting-and-depth.md).

## Scoring

One score. Start at **0**, unbounded sum, **higher = worse**. The five finding
types are fixed; the weights depend on the review type, because the same defect
does not cost the same everywhere.

| type | meaning | `repo` | `pr` `branch` | `review` | `skill` | `agent` | `prompt` | `docs` |
|------|---------|-------:|--------------:|---------:|--------:|--------:|---------:|-------:|
| `breaking_bug` | Crash, wrong result, data loss, dead workflow | 5 | 6 | 6 | 5 | 4 | 4 | 2 |
| `security_issue` | Auth, injection, secrets, unsafe instructions | 4 | 5 | 5 | 4 | 5 | 5 | 3 |
| `missing_feature` | Asserted capability with no implementation | 3 | 2 | 3 | 4 | 3 | 2 | 3 |
| `bug` | Incorrect behaviour, not catastrophic | 3 | 3 | 4 | 3 | 2 | 3 | 1 |
| `wrong_claim` | A claim the artifact contradicts | 2 | 2 | 3 | 3 | 3 | 3 | 5 |

Weights live in [`scoring.json`](scoring.json), with the rationale for each
column in its `type_notes`. `confidence` is display-only, and so is the band the
report prints: 0 clean · 1–5 minor drift · 6–15 misleading · 16+ bullshit.

## Examples

Every number here comes from a committed fixture and is asserted in CI; the
artifacts the quotes point at live under `examples/`.

| example | review type | score | shows |
|---------|-------------|------:|-------|
| `findings.valid.json` | `repo` | **17** | README lies + real bugs; one duplicate merged, one blank-evidence finding rejected |
| `findings.blast.json` | `repo` | **5** | One root cause reported three ways — merged, then counted across every file it reaches |
| `findings.shallow.json` | `repo` | **2** | A docs-only pass that also claims to have read a file that does not exist |
| `findings.hallucinated.json` | `repo` | **NOT_VALID** | Four confident fabrications, all rejected |

```bash
bs-score examples/findings.valid.json   --repo-root examples/fixture-repo
bs-score examples/findings.blast.json   --repo-root examples/fixture-repo
bs-score examples/findings.shallow.json --repo-root examples/fixture-repo --require-depth
```

Eight more — `review`, `skill`, `agent`, `prompt`, `docs`, two in-the-wild
repositories, and a French/Japanese pair proving quotes verify verbatim in any
language — are documented with their commands in
[`examples/README.md`](examples/README.md). Each writes the same report as its
committed `examples/score.*.json` receipt.

## CLI

```text
bs-score FINDINGS [--repo-root DIR] [--sources PATH ...] [--no-verify]
                  [--require-evidence] [--strict-lines] [--line-window N]
                  [--no-scan] [--require-depth]
                  [--fold-case] [--fail-over N] [--format json|md|sarif]
                  [--baseline FILE] [--write-baseline FILE] [-o FILE]
                  [--scoring FILE --allow-custom-scoring] [-v|-q]

bs-score claims DOC [--repo-root DIR] [--check-links] [--emit-findings]
                    [--ignore GLOB ...]
```

Highlights:

| flag | effect |
|------|--------|
| `--sources` | Register non-file evidence (prompt files, review bodies) so their quotes verify too |
| `--fold-case` | Case-insensitive quote matching (str.casefold); exact is the default |
| `--fail-over N` | Exit 1 when the score exceeds N — the CI gate |
| `--require-depth` | Fail when a review type that needs a code pass cannot prove one |
| `--no-scan` | Skip the blast-radius sweep (the count is then unreported) |
| `--format sarif` | SARIF 2.1.0 for GitHub code scanning |
| `--baseline` / `--write-baseline` | Accept known findings once; gate only on new ones |
| `claims` | LLM-free claim checks on a document; `--emit-findings` for a scorable payload |
| `--ignore` | Spans that are not claims about this tree — a file a command writes, a version a changelog records. Reported as `skip` naming the pattern, never dropped |

Exit codes: `0` scored and within threshold · `1` over `--fail-over` (or
`claims` found a provably false claim) · `2` unusable input.

## Integrations

**GitHub Action** (composite, [`action.yml`](action.yml)):

```yaml
- uses: alexhawat/bs_score@main
  with:
    findings: findings.json
    fail-over: "10"
```

It writes the report as a file in the format you ask for and exposes `score`,
`band` and `report` outputs. [`docs/github-action.md`](docs/github-action.md)
has the PR-comment and code-scanning recipes.

**SARIF** — `bs-score findings.json --format sarif -o report.sarif`, then the
codeql-action upload-sarif step puts findings into code scanning.

**pre-commit** — hook id `bs-score` (see [`.pre-commit-hooks.yaml`](.pre-commit-hooks.yaml)).

**MCP server (experimental)** — `uv pip install 'bs-score[mcp]'`, then
`bs-score-mcp` exposes `audit` and `score` tools over stdio.

**Self-audit** — the v1 audit of this repository (`examples/findings.self.json`)
is replayed as a CI gate on every PR (`scripts/check_dogfood.py`, which asserts
the score is 0): all eight defects it documented must stay fixed — reintroduce
one, its quote verifies again, and CI goes red.

## Development

```bash
uv sync --extra dev
uv run pytest
uv run ruff check .
uv run python scripts/gen_agent_wrappers.py --check   # wrappers are generated
uv run python scripts/check_receipts.py               # receipts reproduce exactly
uv run python scripts/gen_llms_txt.py --check         # llms.txt files are generated
```

Contributor rules for agents: [`AGENTS.md`](AGENTS.md). Releasing (owner-only):
[`RELEASING.md`](RELEASING.md).

## FAQ

**Is the score objective?**
No — it's *verifiable*. An LLM still chooses what to look for and how bad it
is. What bs-score removes is the unverifiable part: every point traces to a
quote that provably exists in the artifact, under pinned weights, with a
sha256 receipt for the weights, the schema, and the findings. You can replay
any score and get the same number.

**What stops the agent gaming it?**
Three things. *Rejection*: an invented quote is rejected, so padding the
findings list with fabrications scores zero. *Dedupe*: the same defect filed
five ways is one finding. *Pinned weights*: the agent can't propose its own
points — findings JSON containing `score` or `points` is rejected outright,
and custom weight files require an explicit `--allow-custom-scoring` flag that
the report discloses.

**Why does higher mean worse?**
Because it counts bullshit, not quality. A 0 means everything the auditor
said checked out — or the auditor said nothing verifiable, which the report
shows separately (`rejected`, `not_verifiable`). Read the band, then read the
kept findings.

## License

MIT
