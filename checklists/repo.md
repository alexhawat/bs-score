# Checklist — `repo`

Audit the repository in **two passes**. Stopping after Pass A is an incomplete audit.

## Pass A — claims

README, docs, marketing copy, badges, and `--help` text against the implementation.

1. Features asserted but absent → `missing_feature`.
2. Features that exist but behave differently than documented → `wrong_claim`.
3. Paths, CLI flags, env vars, and endpoints named in docs that do not exist.
4. Absolutes — "always", "never", "automatically", "zero-config", "deterministic"
   — with nothing in the code enforcing them.
5. Install or quick-start commands that cannot run as printed.

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

## Emit

```json
{ "version": 2, "target_kind": "repo", "target_ref": "<owner/repo@sha>", "findings": [] }
```
