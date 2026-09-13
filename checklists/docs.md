# Checklist — `docs`

Audit a document — a README, guide, tutorial, man page, or spec — for one thing
only: **claims contradicted by what exists**. No deep code pass; the text itself
is the artifact. The `docs` profile weights `wrong_claim` highest, because a
wrong statement is the defining docs failure.

## Method

1. **Extract every checkable assertion.** Walk the text line by line and list
   anything a reader could prove or disprove:
   - paths — files, directories, config locations the text names;
   - commands — invocations, subcommands, install lines;
   - flags and options — every long option and its documented effect;
   - numbers — limits, timeouts, counts, exit codes, ports;
   - versions — language/runtime/dependency requirements;
   - guarantees — "always", "never", "automatically", "by default",
     "zero-config", "deterministic".
2. **Prove or disprove each one.** Resolve the path, run or read the command's
   definition, diff the version against the packaging metadata, find the code
   that enforces (or fails to enforce) the absolute.
3. **File one finding per disproven assertion.** `wrong_claim` for a stated fact
   that is false; `missing_feature` when the text asserts a capability with
   nothing behind it at all. Quote the *sentence that lies*, verbatim.
4. **Skip the uncheckable.** Opinions, aspirations, and marketing adjectives
   ("fast", "elegant") are not findings.

Mechanical head start: `bs-score claims <doc>` verifies paths, commands, flags,
versions, links, and fenced code blocks without an LLM and can emit
pre-verified `wrong_claim` findings. Its output is a floor, not a ceiling —
check by hand everything it cannot see (semantics, guarantees, behaviour).

Use `target: "readme"` for prose quotes and `target: "other"` for anything else
in the document.

## Emit

```json
{ "version": 2, "target_kind": "docs", "target_ref": "<path-or-URL>", "findings": [] }
```
