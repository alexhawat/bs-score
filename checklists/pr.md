# Checklist — `pr` / `branch`

Same two passes as [`repo`](repo.md), with the diff as the unit of review. The
`pr` and `branch` profiles weight landing defects above documentation drift.

## Scope

- `git diff <base>...<head>` or `gh pr diff <n>` is the primary surface.
- Read the **callers** of every changed function, not only the changed lines: a
  signature change that compiles can still break a call site.

## Look for

1. The change does not do what its title and description say → `wrong_claim`.
2. A new code path that is never reached (registered nowhere, flag never set,
   handler never wired) → `missing_feature` or `bug`.
3. Behaviour changes with no corresponding test, where the diff claims coverage.
4. Error paths added without the rollback the happy path assumes.
5. Secrets, tokens, or internal hostnames introduced by the diff.
6. Migrations or config changes with no backward-compatible path.
7. Docs in the same repo that the diff has just made false.

## Before you emit

- Sweep each quote across the tree (`rg -n --fixed-strings '<quote>'`). One
  defect in one file is usually one defect in several.
- Give same-cause findings a shared `cluster` id.
- List what you opened in `audit.files_read`. A `pr` audit with no
  implementation file in that list is stamped **shallow**.
- Re-read [the shared failure modes](README.md#two-failure-modes-that-apply-to-every-review-type),
  especially hollow verification.

## Emit

```json
{ "version": 2, "target_kind": "pr", "target_ref": "<owner/repo#42>", "findings": [] }
```
