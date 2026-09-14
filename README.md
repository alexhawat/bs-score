# bs_score

[![ci](https://github.com/alexhawat/bs_score/actions/workflows/ci.yml/badge.svg)](https://github.com/alexhawat/bs_score/actions/workflows/ci.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![python: 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](pyproject.toml)

**AI lies, sometimes people. bs_score catches it — every claim is quoted, every quote
is verified, and the score comes from code, not prose. Use it to catch bullshit in repo (readme vs code), PR, PR review, skills, agents and more.**

The LLM *finds* defects and quotes the evidence. The `bs-score` CLI *verifies
every quote against the artifact it names*, then scores what survived. Higher =
more bullshit. A fabricated audit scores **0**, because none of its quotes
exist.

## Use with your agent — one line

Paste this into your Claude, Cursor, Grok , Grok bot, Opencode, chatgpt agents:

```text
Add the bs_score skill from https://github.com/alexhawat/bs_score and learn how to use it. 
```

Or wire it up per runtime:

| Runtime | One-line setup |
|---------|----------------|
| Claude Code | `git clone https://github.com/alexhawat/bs_score ~/.claude/skills/bs_score` |
| Cursor | Clone anywhere, then `@` the root `SKILL.md` — or copy `agents/cursor/` into your skills path |
| Codex | Append the root `SKILL.md` to your `AGENTS.md` |
| Grok | Attach the root `SKILL.md` as the bot skill, or copy `agents/grok/` |
| Hermes | Register `agents/hermes/` as a skill, or load the root `SKILL.md` |
| OpenClaw | Register `agents/openclaw/` as a skill, or load the root `SKILL.md` |
| OpenCode | Register `agents/opencode/` as a skill, or load the root `SKILL.md` |
| **Any agent** | The paste line above — anything that can follow a skill file and run a command works |

Either way the agent needs the `bs-score` CLI at scoring time; the git one-liner
covers that. The PyPI release will make the scorer plain `uvx bs-score`,
no clone at all.

LLM-facing context files: [`llms.txt`](llms.txt) (index) and
[`llms-full.txt`](llms-full.txt) (the whole recipe, weights, and schema in one
fetch).

## 30-second demo

```bash
uvx --from git+https://github.com/alexhawat/bs_score bs-score --help
```

Then, from a clone (`git clone https://github.com/alexhawat/bs_score && cd bs_score && uv sync`):

```console
$ uv run bs-score examples/findings.valid.json --repo-root examples/fixture-repo --format md
## Bullshit Score: **17** (bullshit)

- kept 5 · rejected 1 · deduped 1 · baselined 0
- evidence: verified (verified 6)

| `wrong_claim`     | 2 | README claims OAuth; only API keys exist |
| `missing_feature` | 3 | Streaming API documented but absent      |
| `bug`             | 3 | Off-by-one in pagination                 |
| `security_issue`  | 4 | SQL built with f-string                  |
| `breaking_bug`    | 5 | delete_user ignores ownership            |
```

Same CLI, an auditor that made everything up:

```console
$ uv run bs-score examples/findings.hallucinated.json --repo-root examples/fixture-repo --format md
## Bullshit Score: **0** (clean)

- kept 0 · rejected 4
- evidence: verified (path_not_found 1, quote_not_found 3)

### Rejected (not scored)
- `h1` — unverified_evidence: quote_not_found: quote is not present in src/api.py
- `h2` — unverified_evidence: path_not_found: src/config.py does not exist
```

Hallucinating earns nothing: a finding whose quote is not there is rejected,
not scored — four confident fabrications add up to zero.

<details>
<summary>Install caveats</summary>

- The one-liner above installs the default branch straight from git — no
  clone, no virtualenv, thanks to `uv`. CI runs that exact command against
  every commit (`uvx-install` job), so it is proven, not promised.
- `uvx bs-score` (no `--from`) will work after the planned PyPI release;
  today it has nothing to fetch.
- From a clone, `uv run bs-score …` and `python3 score.py …` do the same
  thing with no network at all.

</details>



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
| **Evidence verification** | A quote not present in the named artifact is rejected before scoring — fabricated findings contribute 0, so padding an audit with hallucinations earns nothing. |
| **Content-addressed dedupe** | `(type, canonical file, quote fingerprint)` is one finding, whether filed as `src/a.py:10`, `./src/a.py:11`, or copy-pasted into seven files. |
| **Pinned weights** | Custom weights need `--allow-custom-scoring`; every report carries `scoring_sha256` + `schema_sha256`, and receipts reproduce byte-for-byte in CI. |
| **Full schema enforcement** | Types, enums, `minLength`, numeric bounds — cross-checked against `jsonschema`; one malformed finding is rejected on its own. |
| **Root-cause clustering** | Findings sharing a `cluster` id collapse into one charge even when the wording differs in each place, so one defect cannot be filed three ways for triple the points. |
| **Measured blast radius** | Every verified quote is swept across the tree, so `files_affected` is counted by the scorer rather than claimed by the model. |
| **Audit-depth check** | `audit.files_read` is checked against the tree: a docs-only pass is stamped `shallow`, and a listed file that does not exist earns no credit. |

## Counting, clustering, and depth

Three things that stop an audit being graded on how hard the model looked.

**The count is measured.** Once a quote is verified, the scorer searches the
whole tree for it and reports every file it lands in. You file the defect once;
the report says it is in twenty-six files. Filing it twenty-six times earns
nothing. The sweep reads tracked text files once — about 1.4s over a 2,300-file
repository — skips binaries and anything over 1 MB, and caps at 200 occurrences
per quote. `--no-scan` opts out; `--fold-case` is honoured so the sweep always
matches the way verification did.

**A root cause is charged once.** The same defect is often worded differently in
each place, which defeats quote-based dedupe. Give those findings the same
`cluster` id and they collapse into one scored finding whose blast radius is the
union of all their quotes:

```bash
uv run bs-score examples/findings.blast.json --repo-root examples/fixture-repo --format md
# one root cause reported three ways → 1 finding, 3 points, 3 files affected
```

**A shallow audit says so.** A payload can carry what it actually opened:

```json
{
  "audit": {
    "files_read": ["README.md", "src/cli.py", "src/api.py"],
    "notes": "Docs claims plus every module under src/."
  }
}
```

For `repo`, `pr`, `branch` and `skill` the report is stamped `shallow` when that
list holds no implementation file and `unreported` when the block is missing.

A path in the list that does not exist earns **no credit**: it is excluded from
`files_read`, `code_files_read` and `coverage`, and named in `missing_files`. It
cannot turn a shallow pass into a deep one on its own — but if the audit also
read a real implementation file, the `status` under `depth` is still `deep`. The
field that accounts for the phantom is `sufficient`, and that is what
`--require-depth` gates on:

| audit block | `status` | `sufficient` | `--require-depth` |
|---|---|---|---|
| docs only | `shallow` | `false` | exit 1 |
| docs + a phantom "code" file | `shallow` | `false` | exit 1 |
| real code + a phantom file | `deep` | `false` | exit 1 |
| real code, all paths exist | `deep` | `true` | exit 0 |

```console
$ bs-score examples/findings.shallow.json --repo-root examples/fixture-repo --format md
- depth: **shallow** — 2 file(s) read, 0 of them implementation (20% of the tree); **1 listed file(s) do not exist**
- blast radius: 1 file(s) affected across 10 scanned
```

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

Why they differ: a `pr` is a gate, so landing defects outweigh doc drift. A
`review` is graded on its claims. A `skill` that advertises a capability it
does not have is the defining skill failure. An `agent` or a `prompt` is an
instruction surface, so unsafe instructions weigh most. A `docs` audit is
claims-only, so a wrong claim weighs most.

Weights live in [`scoring.json`](scoring.json). `confidence` is display-only.

**Score bands** (display-only; the raw sum is the score):

| score | band |
|------:|------|
| 0 | clean |
| 1–5 | minor drift |
| 6–15 | misleading |
| 16+ | bullshit |

## Examples

Every number below is produced by committed fixtures and asserted in CI; the
artifacts the quotes point at live under `examples/`.

| example | review type | score | shows |
|---------|-------------|------:|-------|
| `findings.valid.json` | `repo` | **17** | README lies + real bugs; one duplicate merged, one blank-evidence finding rejected |
| `findings.review.json` | `review` | **10** | False claim, hollow "verified", a defect the review missed |
| `findings.skill.json` | `skill` | **7** | SKILL.md names a script that does not exist; documents the wrong flag |
| `findings.agent.json` | `agent` | **6** | Phantom skill; "never push" next to "auto-push to main" |
| `findings.prompt.json` | `prompt` | **18** | Injection surface, a token in the prompt, self-contradictions |
| `findings.docs.json` | `docs` | **15** | A guide's three provable lies (Python floor, config path, phantom flag) |
| `findings.i18n.json` | `docs` | **10** | French and Japanese READMEs — quotes verify verbatim in any language |
| `findings.wild-tinycache.json` | `repo` | **8** | In-the-wild pattern: a 0.9 README promising 1.0 features |
| `findings.wild-greetcli.json` | `docs` | **10** | In-the-wild pattern: phantom flag, understated Python floor |
| `findings.blast.json` | `repo` | **5** | One root cause reported three ways — merged, then counted across every file it reaches |
| `findings.shallow.json` | `repo` | **2** | A docs-only pass that also claims to have read a file that does not exist |
| `findings.hallucinated.json` | `repo` | **0** | Four confident fabrications, all rejected |

```bash
uv run bs-score examples/findings.valid.json  --repo-root examples/fixture-repo
uv run bs-score examples/findings.docs.json   --repo-root examples/fixture-docs
uv run bs-score examples/findings.prompt.json --repo-root examples/fixture-prompts \
    --sources examples/fixture-prompts
uv run bs-score examples/findings.blast.json  --repo-root examples/fixture-repo
uv run bs-score examples/findings.shallow.json --repo-root examples/fixture-repo --require-depth
```

Each writes the same report as the committed `examples/score.*.json` receipt.
Details: [`examples/README.md`](examples/README.md).

## CLI

```text
bs-score FINDINGS [--repo-root DIR] [--sources PATH ...] [--no-verify]
                  [--require-evidence] [--strict-lines] [--line-window N]
                  [--no-scan] [--require-depth]
                  [--fold-case] [--fail-over N] [--format json|md|sarif]
                  [--baseline FILE] [--write-baseline FILE] [-o FILE]
                  [--scoring FILE --allow-custom-scoring] [-v|-q]

bs-score claims DOC [--repo-root DIR] [--check-links] [--emit-findings]
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

Post the Markdown report as a PR comment:

```yaml
- uses: alexhawat/bs_score@main
  with: { findings: findings.json, format: md }
- uses: actions/github-script@v7
  if: always()
  with:
    script: |
      const fs = require('fs');
      await github.rest.issues.createComment({
        owner: context.repo.owner, repo: context.repo.repo,
        issue_number: context.issue.number,
        body: fs.readFileSync('report.md', 'utf8'),
      });
```

**SARIF** — `bs-score findings.json --format sarif -o report.sarif`, then the
codeql-action upload-sarif step puts findings into code scanning.

**pre-commit** — hook id `bs-score` (see [`.pre-commit-hooks.yaml`](.pre-commit-hooks.yaml)).

**MCP server (experimental)** — `uv pip install 'bs-score[mcp]'`, then
`bs-score-mcp` exposes `audit` and `score` tools over stdio.

**Self-audit** — the v1 audit of this repository (`examples/findings.self.json`)
is replayed as a CI gate on every PR (`--fail-over 0`): all eight defects it
documented must stay fixed — reintroduce one, its quote verifies again, and CI
goes red.

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
is. What bs_score removes is the unverifiable part: every point traces to a
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
