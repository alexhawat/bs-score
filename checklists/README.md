# Checklists

One per review type. Read the one that matches your `target_kind`; they are kept
out of [`../SKILL.md`](../SKILL.md) so the recipe stays short.

Each ends with the JSON envelope to emit. All of them share the same rules: a
contiguous verbatim quote per finding, no `score` or `points` fields, and only
the five types in [`../scoring.json`](../scoring.json).

## Two failure modes that apply to every review type

### Hollow verification

A name, docstring, comment, or sentence asserts that something was checked, and
the thing next to it checks something weaker or nothing at all.

```text
"Verified: no secrets in this diff"        → no secret-related check performed
def test_the_command_runs(): assert "cmd" in readme   → a substring, not a run
"All endpoints are authenticated"          → one decorator, applied to one route
"CI enforces this"                         → no workflow step does
```

The tell is a verb of proof — *verified, ensures, guarantees, enforces, runs,
validates* — with no execution, assertion, or gate behind it. File it as
`missing_feature` (the verification is advertised and absent), quoting the
claim, not the weaker thing. It is the most common defect in AI-written reviews
and tests, and the easiest to miss because it reads like diligence.

### Counting by hand

If you find a defect in one file, it is usually in more. Sweep before you file:

```bash
rg -n --fixed-strings 'the exact quote'     # or: grep -rn
```

Then file **one** finding. Give same-cause findings a shared `cluster` id when
the wording differs between places; the scorer charges the cause once and counts
the files for you, and `files_affected` in the report is the number to quote.
Filing one defect N times earns nothing and misstates the shape of the problem.
