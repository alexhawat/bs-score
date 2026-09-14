# Checklist — `repo`

Audit the repository in **two passes**. Stopping after Pass A is an incomplete audit.

## Pass A — claims

README, docs, marketing copy, badges, and `--help` text against the implementation.

1. Features asserted but absent → `missing_feature`.
2. Features that exist but behave differently than documented → `wrong_claim`.
3. Paths, CLI flags, env vars, and endpoints named in docs that do not exist.
4. Absolutes — "always", "never", "automatically", "zero-config", "deterministic"
   — with nothing in the code enforcing them.
5. Install or quick-start commands that cannot run as printed. Actually run
   them, or check that CI does; a command nothing executes is a claim nobody
   checked. Then sweep — the same broken command is rarely in only one file.
6. Hollow verification: "verified", "enforced", "guaranteed", "tested" with
   nothing behind it (see [shared failure modes](README.md#hollow-verification)).

## Pass B — deep code (required)

Read entrypoints and core modules, not just the docs.

1. Logic, state, and ordering bugs; off-by-one; wrong default.
2. Side effects with no rollback on the cancel/error path.
3. Error handling that swallows failure (bare `except`, ignored return, exit 0
   on error).
4. Security: injection, secrets in source, missing authorisation check, unsafe
   deserialisation, path traversal.
5. Control flow that makes an advertised workflow impossible to complete.
6. Dead branches that the docs describe as live behaviour.

## Before you emit

- Sweep each quote across the tree (`rg -n --fixed-strings '<quote>'`). One
  defect in one file is usually one defect in several.
- Give same-cause findings a shared `cluster` id.
- List what you opened in `audit.files_read`. A `repo` audit with no
  implementation file in that list is stamped **shallow**.
- Re-read [the shared failure modes](README.md#two-failure-modes-that-apply-to-every-review-type),
  especially hollow verification.

## Emit

```json
{ "version": 2, "target_kind": "repo", "target_ref": "<owner/repo@sha>", "findings": [] }
```
