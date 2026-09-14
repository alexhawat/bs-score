# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

### Changed

- A kept finding's `occurrences` now lists where the scorer *found* the quote
  (`{path, line}`); reports merged into it by dedupe are listed under `merged`.
  The Markdown renderer gained `files` and depth/blast-radius lines.
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
  (`uvx --from git+https://github.com/alexhawat/bs_score bs-score`) — true
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
  "git+https://github.com/alexhawat/bs_score@<ref>"` installs without a clone
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
