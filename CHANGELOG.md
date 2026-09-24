# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

### Changed
- All-unverified runs (findings present, nothing verified) are **NOT_VALID**
  (`score: null`, exit 3), not a clean score of 0. Empty `findings: []` stays 0.

## [Unreleased]

### Added

- **`bs-score find --jev`** — optional Jev-based finding discovery via TypeSafe
  System One. Collects claim-like candidate units deterministically from
  markdown, batches keep/type/confidence questions in one call per file,
  pins jev-1.13.0, logs model and token usage per call, and routes on both
  answer probabilities and confidence floors (`src/bs_score/jev_questions.py`).
  Emits a `findings.schema.json` payload with verbatim quotes and templated
  titles. Requires the optional `jev` extra (`typesafe-sdk`) and
  `TYPESAFE_API_KEY`. Implemented for `target_kind` `repo` and `docs`;
  `--score` chains the scorer in one process. Without `--jev`, behaviour is
  unchanged.

### Changed

- **The skill is named `bs-score`**, matching the CLI, the distribution and the
  convention every runtime's own examples follow. Its folder is
  `~/.claude/skills/bs-score` (and the equivalent elsewhere), and the `name:`
  frontmatter matches. Identifiers keep their underscore because they must: the
  Python package is `bs_score`, and so are the JSON keys it emits
  (`bs_score_version`, the SARIF `bs_score` property).
- `scoring.json` carries `"name": "bs-score"`, so `scoring_sha256` changes and
  every receipt is regenerated. Weights are untouched — no score moves.

### Added

- **`bs-score claims --ignore GLOB`** (repeatable) for spans that are not claims
  about the tree: a file a command writes at runtime, a version a changelog
  records, an install destination. Matched claims are reported as `skip` naming
  the pattern rather than dropped, and the report now carries each claim's
  `span` so there is something to point the pattern at.

### Fixed

- **`--write-baseline` writes everything the run accepted**, `kept` *and*
  `baselined`. It wrote only `kept`, so `--baseline b.json --write-baseline
  b.json` — the obvious way to refresh a baseline — truncated the file to
  nothing and the next run scored every finding again.
- **Dedupe applies under a baseline.** Merge targets were registered only for
  `kept`, so a payload that reports `kept 5 · deduped 1` reported
  `baselined 6` when a baseline covered it. `deduped` entries gained
  `merged_into_bucket`, naming which list the duplicate merged into.
- **The Action pins the scorer to its own ref.** `ref` defaulted to `main`, so
  `uses: alexhawat/bs-score@<sha>` ran that sha's `action.yml` and installed
  whatever `main` happened to be. It now defaults to `github.action_ref`.
- **`-q` keeps errors.** It removed every log sink, so an unusable payload
  exited 2 having printed nothing — and `-q` is what `action.yml` passes.
  Quiet now means ERROR and above; stdout is unchanged.
- **`claims` false positives.** `check_flags` matched `\s+` between tokens,
  which crosses newlines, so a flag on the next line was attributed to the
  previous line's command; `_check_anchor` counted `##` lines inside fenced
  code blocks as headings, resolving dead anchors.
- **The depth check no longer forces a full content index.** `paths()` read and
  NFKC-normalised every file to answer which paths exist — most of the cost of
  a `--no-scan` run. Split into a scan (stat plus an 8 KiB binary sniff) and
  the normalised index the sweep builds on demand.
- **Install paths per runtime** in the README and the generated wrappers, for
  both user and project scope, plus the `uv tool install` line that actually
  puts `bs-score` on `PATH`. Cloning into a skills folder never did.
- **Docs quoting output no runs produced.** Both README demo blocks showed
  invented tables; the console-block test only matched a bare `$ bs-score` and
  both were spelled `$ uv run bs-score`. The link test dropped `#anchor` before
  resolving, so fifteen files pointed at a `#install` section that never
  existed. Both guards are fixed and the blocks are live output.
- `.pre-commit-hooks.yaml` documented a `rev:` pinned to a release tag this repo
  has never had, and no `files:` filter — so pre-commit handed the hook every
  staged JSON and it failed with "unrecognized arguments".
- **`claims` counted version numbers inside URLs.** A link to
  `semver.org/spec/v2.0.0.html` was read as a claim that this project is at
  2.0.0. Versions inside a URL or a Markdown link target are addresses, not
  claims.
- **`claims` read a GitHub owner/repo slug as a repository path.** When the
  document itself addresses it as `github.com/owner/repo`, it is a repo, and the
  check is reported as `skip` with that as the evidence.
- **`claims` read a scheme-less URL as a path.** A backticked
  `semver.org/spec/...` is an address; a first segment shaped like a hostname is
  no longer a directory in this tree. A leading dot still marks a real path, so
  `.github/workflows/ci.yml` is checked as before.
- Together those two, plus `--ignore`, bring `CHANGELOG.md` into the claims
  dogfood test for the first time — it could not be checked at all before.

## [2.2.0] - 2026-09-14

Stops the score depending on how hard the model looked. Prompted by an audit of
PR #2 that reported one dead install command as three findings and implied that
was the inventory — it was in 26 places across 21 files, including all seven
runtime wrappers people actually install.

### Added

- **Measured blast radius.** Every verified quote is swept across the tree and
  the report says which files carry it: `files_affected`, `occurrences` with
  line numbers, and a top-level `blast_radius`. The score is unchanged — a
  defect is charged once — but the count is a measurement instead of a claim,
  so undercounting is no longer possible and re-filing earns nothing. One pass
  over the tree, roughly 1.4s for 2,300 files. `--no-scan` opts out, and the
  sweep honours `--fold-case` so it always matches the way verification did.
- **Root-cause clustering.** An optional `cluster` id on a finding collapses
  same-cause findings into one charge even when the wording differs in each
  place, which quote-identical dedupe could never do — that is exactly how one
  root cause scored three times. A cluster's blast radius is the union of its
  members' quotes.
- **Audit-depth checking.** A payload can carry `audit.files_read`. For `repo`,
  `pr`, `branch` and `skill` the report is stamped `shallow` when that list
  holds no implementation file and `unreported` when the block is absent; a
  listed path that does not exist earns no depth credit and is reported as a
  phantom read. `--require-depth` turns an insufficient audit into a non-zero
  exit. "Docs-only is incomplete" had been in `SKILL.md` since v1 with nothing
  enforcing it.
- `checklists/README.md` documents two failure modes that apply to every review
  type: **hollow verification** (a verb of proof with nothing behind it — the
  defect a PR #2 audit found in this project's own tests) and **counting by
  hand** (sweep before you file).
- `examples/findings.blast.json` and `findings.shallow.json`, with the fixture
  repo extended to carry one root cause worded three ways.
- `scripts/check_dogfood.py` runs the claims the README makes through the real
  CLI, in CI and in the test suite.
- `depth.sufficient` in the JSON report — the field `--require-depth` actually
  gates on. It differs from `depth.status` when a listed file does not exist,
  and was previously derivable only by reimplementing the rule.
- Documented `$ bs-score …` console blocks are executed in the test suite and
  checked against real output, after a README block stitched a depth line from
  one example to a blast-radius line from another.

### Changed

- **Breaking — `occurrences` changed meaning.** On a kept finding it now lists
  where the scorer *found* the quote, as `{path, line}` objects. The reports
  merged into it by dedupe — what `occurrences` used to hold — moved to
  `merged`. Anything reading `occurrences` as "how many duplicates were filed"
  reads a different thing now, and gets objects where it expected `{id, path}`.
  Nothing in this repository depends on the old shape: `baseline.py` keys on
  `(type, canonical_file, quote_fingerprint)` and is unaffected.
- The Markdown renderer gained a `files` column and depth / blast-radius lines.
- The `prompt` example scores against `examples/fixture-prompts` rather than the
  repository root, so its receipt does not change every time the repo gains a
  file; the self-audit runs with `--no-scan` for the same reason.
- `test_documented_flags_exist` inspects only fenced code blocks, and only the
  part of a line after the command name, so a flag invented for bs-score cannot
  hide beside a real `uvx --from` or `rg --fixed-strings`.

## [2.1.0] - 2026-09-13

Wrong info gets its own review type, and the mechanical slice of it no longer
needs an LLM at all.

### Added

- **`docs` review type.** A claims-only audit of a single document; the
  checklist walks every checkable assertion (paths, commands, flags, numbers,
  versions, guarantees) and the profile weights `wrong_claim` highest (5).
  `examples/findings.docs.json` scores a lying guide at 15.
- **Score bands** (display-only; the raw sum is unchanged): `0 clean ·
  1–5 minor drift · 6–15 misleading · 16+ bullshit`, in the JSON report and
  the `--format md` header.
- **`bs-score claims` — deterministic claim verification without an LLM.**
  Paths, declared entry points, CLI flags (read from the argparse definition),
  version strings, Markdown links/anchors, and fenced python/json/bash blocks
  are checked mechanically; `--check-links` fetches URLs, and
  `--emit-findings` wraps each failure as a pre-verified `wrong_claim` payload.
- **`--fold-case`.** Case-insensitive quote matching via `str.casefold()`,
  threaded through verification and the dedupe fingerprint. Exact matching
  stays the default.
- **`--format sarif`.** SARIF 2.1.0 output for GitHub code scanning, kept
  findings only, with quote fingerprints as partialFingerprints.
- **Baselines.** `--baseline FILE` suppresses known findings by dedupe key;
  `--write-baseline FILE` captures the current kept set. Only new findings
  score, so `--fail-over` gates on regressions.
- **GitHub Action** (`action.yml`, composite) with `score` / `band` / `report`
  outputs, a **pre-commit hook** (`bs-score`), and an **experimental MCP
  server** (`bs-score[mcp]` extra, `bs-score-mcp`, stdio) exposing `audit` and
  `score` tools.
- **Multilingual proof.** `examples/fixture-i18n/` — a French and a Japanese
  README, each with one deliberate wrong claim; quotes verify verbatim in the
  artifact's own language, and a translated quote is rejected.
- **`examples/in-the-wild/`**: two synthetic-but-realistic snapshots
  (tinycache@0.9, greetcli@1.2) of READMEs that drifted ahead of their code.
- **`AGENTS.md`** contributor contract; **`llms.txt` / `llms-full.txt`**
  generated from canonical sources by `scripts/gen_llms_txt.py` and
  drift-checked in CI; **`RELEASING.md`** with the exact `uv build && uv
  publish` steps.
- README rewrite: pitch-first, a 30-second demo with captured output, one-line
  install, a per-runtime agent setup table, FAQ, badges.

### Changed

- `findings.schema.json`: `target_kind` gains `docs`.
- Every report now carries `band`, `baselined_count`, `baselined`, and
  `evidence.fold_case`; all receipts regenerated.
- Docs may now print the unpinned one-line install
  (`uvx --from git+https://github.com/alexhawat/bs-score bs-score`) — true
  since v2.0.0 put `pyproject.toml` on the default branch. The regression test
  now guards the remaining false claim: `uvx bs-score` before the PyPI
  release.

## [2.0.0] - 2026-09-13

The score now measures what the model *proved*, not what it *asserted*.

### Added

- **Evidence verification.** Every `quote` is checked against the artifact its
  `path` names before any points are assigned; a quote that is not there is
  rejected. A fabricated audit that scored 14 under v1 now scores 0.
- **`prompt` review type.** Audit one prompt or a whole set — system, developer,
  tool, and persona prompts — with `prompt:<id>[:<line>]` locators and a
  dedicated checklist covering injection surface, secrets in prompts, unenforceable
  guarantees, phantom tools, and contradictions within and across prompts.
- **`--sources`.** Makes non-file evidence addressable (prompt files, review
  bodies) as a directory, a `{"sources": [{"id", "text"}]}` manifest, a `.jsonl`
  stream, or a single file — so `prompt` and `review` audits get verified too.
- **Per-review-type weights.** One score, but `scoring.json` now carries a weight
  profile per `target_kind`. A breaking bug about to land in a PR, a reviewer's
  false claim, and an unsafe line in an agent config no longer cost the same.
- **Packaging.** `pyproject.toml` (hatchling), a `bs-score` console script,
  `python -m bs_score`, and a committed `uv.lock`. `uvx --from
  "git+https://github.com/alexhawat/bs-score@<ref>"` installs without a clone
  once a ref carries the package; CI proves the commit under test is installable
  that way.
- **Loguru diagnostics** on stderr (`-v`, `-q`, `BS_SCORE_LOG_LEVEL`), leaving
  stdout a clean report.
- **CI gating.** `--fail-over N` exits 1 above a threshold; exit 2 for unusable
  input. `--format md` prints a pasteable summary.
- **`--require-evidence`** and **`--strict-lines`** for stricter audits.
- **Reproducibility receipts.** Every report carries `scoring_sha256`,
  `schema_sha256`, `findings_sha256`, the profile, and its weight table.
- Test suite, GitHub Actions CI on Python 3.10–3.13, and `scripts/check_receipts.py`.
- `examples/fixture-repo`, `fixture-prompts`, `fixture-review`: real artifacts for
  the examples to quote. `examples/findings.self.json` keeps v1's eight defects as
  a regression gate.
- `checklists/` — per-review-type audit checklists, split out of `SKILL.md`.

### Fixed

- **Wrapper install snippet was broken in all seven runtimes.** `$(dirname "$0")`
  inside a Markdown code block resolves against the operator's shell, so
  `BS_SCORE_ROOT` became `/` and the documented command ran `python3 //score.py`.
  Wrappers are now generated from one template by
  `scripts/gen_agent_wrappers.py`, checked in CI, and document a command that runs.
- **Schema validation was partial.** v1 checked required keys and two enums;
  `minLength`, field types, and `confidence` bounds went unchecked, so
  `{"id": 123, "title": "", "confidence": "very high"}` scored. Validation now
  walks the published schema itself and is cross-checked against `jsonschema` in CI.
- **`examples/findings.valid.json` was invalid against its own schema** (empty
  `path`/`quote` violate `minLength: 1`). The rejection case is now demonstrated
  with a blank-but-legal value.
- **Dedupe was defeated by formatting.** The key was the raw path string, so
  `src/a.py:10`, `./src/a.py:11`, and `src/a.py` scored three times. The key is now
  `(type, canonical file, quote fingerprint)`, and the same quote across several
  files is one finding with `occurrences`.
- **A malformed `scoring.json` raised a bare `KeyError`.** Weights are validated:
  non-negative integers, every type covered, version pinned; errors exit 2 with a
  readable message.
- **"Locked" weights were not locked.** `--scoring` accepted any file, including
  negative and fractional weights (a documented run produced −91). It now requires
  `--allow-custom-scoring`, and the report records the weights it used.
- **One malformed finding aborted the whole report.** Findings are validated and
  rejected individually; only a malformed envelope stops the run. Duplicate
  finding `id`s are rejected.
- **Schema `$id`** pointed at `alexhawat/bots-agents-skills`.

### Changed

- `scoring.json` is version 2 (`profiles` replace the flat `types` weight map).
  Findings payloads may declare `version: 1` or `2`; both are accepted.
- Verification is **on by default** against the current directory; `--no-verify`
  restores v1 behaviour and stamps the report `skipped`.
- Review-type scores move with the new profiles: `review` 8 → 10, `skill` 5 → 7,
  `agent` 4 → 6. `repo` is unchanged at 17.

## [1.0.0] - 2026-09-13

- Initial release: portable skill, `score.py`, flat weight table, per-runtime wrappers.
