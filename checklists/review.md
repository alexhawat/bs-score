# Checklist — `review`

You are grading an existing pull-request review against the diff it reviewed.
Inputs: the review body, its inline comments, and the PR's files and diff.

Register the review text so its quotes are verifiable:

```bash
bs-score findings.json --repo-root . --sources review.json
```

where `review.json` is `{"version": 1, "sources": [{"id": "review:body", "text": "…"}]}`.

## Look for

1. **Scope labels.** "Change-scoped", "in this PR" — check against the PR's file
   list. Findings about `.venv/`, runner paths, or untouched files → `wrong_claim`.
2. **Severity inflation.** "Never read", "no coverage" filed as Critical or
   Major → `wrong_claim`.
3. **Internal contradictions.** "Analyzer passed" alongside findings of exactly
   that class.
4. **Hollow verification.** "Verified: no secrets" with no secret-related check
   performed → `missing_feature`.
5. **False findings.** An asserted defect the code disproves → `wrong_claim`.
6. **Misses.** A real defect present in the diff that the review did not report
   → `bug` / `breaking_bug` / `security_issue`, quoting the *code*, not the review.

## Rules

- **Never score a finding the review got right.**
- One finding per failure mode. Put the exemplar quote in `quote` and the count
  in the title ("4 out-of-diff paths cited as change-scoped").

## Emit

```json
{ "version": 2, "target_kind": "review", "target_ref": "<owner/repo#42 review:99>", "findings": [] }
```
