# Checklist — `skill`

Audit a skill pack: `SKILL.md` (or `skill.md`, or the recipe file) **and** every
script, wrapper, schema, or helper it names. The `skill` profile weights
`missing_feature` highest: advertising a capability that does not exist is the
defining skill failure.

## Look for

1. **`wrong_claim`** — the MD asserts a step, path, flag, tool, or outcome the
   code does not do, or does differently.
2. **`missing_feature`** — a capability with no implementation: a script that is
   not in the repo, a stub, a dead link, an empty handler.
3. **Commands that cannot run as printed.** Shell snippets are the usual
   offender: `$0` inside a Markdown code block is the operator's shell, not the
   skill file; relative paths resolve against the caller's cwd, not the skill
   directory.
4. **`bug` / `breaking_bug` / `security_issue`** in skill-adjacent code the MD
   implies is safe or correct.
5. **Hollow absolutes** — "always", "never", "automatically" — with no code
   behind them.
6. **Frontmatter vs body vs code.** A `description` that promises more than the
   body delivers is a contradiction. So is a declared tool the skill never uses,
   or a used tool it never declares.
7. **Progressive-disclosure claims** — files referenced for "more detail" that
   do not exist.

Do not invent missing files: if a referenced path is absent, quote the *reference*
from the MD and file `missing_feature`.

Use `target: "skill"` for MD quotes and `target: "code"` for script quotes.

## Emit

```json
{ "version": 2, "target_kind": "skill", "target_ref": "<path-or-name>", "findings": [] }
```
