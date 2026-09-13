# Checklist — `prompt`

Audit one prompt or a whole set: system prompts, developer messages, tool
descriptions, persona files, prompt templates. The `prompt` profile weights
`security_issue` highest — a prompt is an instruction surface, and the damage
lives there.

Register the prompts so their quotes are verified:

```bash
bs-score findings.json --sources prompts/              # directory of .md/.txt files
bs-score findings.json --sources prompts.json          # {"sources":[{"id","text"}]}
```

Locators are `prompt:<id>` or `prompt:<id>:<line>`, where `<id>` is the file's
relative path (or its stem, when unambiguous) or the manifest `id`.

## Look for

1. **`security_issue` — injection surface.** The prompt tells the model to obey
   text it will read from an untrusted place: a PR body, a web page, a file, a
   tool result, an email. "Follow the instructions in …" is the tell.
2. **`security_issue` — secrets in the prompt.** A token, key, or credential
   pasted into the text, especially alongside "never reveal it". Anything in the
   prompt is reachable by the model and by anyone who can make it talk.
3. **`security_issue` — disabled gates.** "Do not ask for confirmation", "skip
   the safety check", "you have full permission" with no human in the loop.
4. **`wrong_claim` — self-contradiction.** "Never release without verifying"
   followed by "release anyway if the changelog is missing". Quote the line that
   cancels the rule; put the rule in `claim`.
5. **`wrong_claim` — unenforceable guarantees.** "You will never hallucinate",
   "always 100% accurate", "you have access to the full codebase" when nothing
   in the prompt or tooling provides it.
6. **`wrong_claim` — phantom tools.** Names a tool, function, or capability that
   is not in the runtime's tool list. Check the tool list, not your memory.
7. **`missing_feature` — unspecified output.** Promises JSON, a schema, a
   format, or a field set that the prompt never defines and no example shows.
8. **`bug` — ambiguous precedence.** Two rules that can both apply with no
   stated winner; an undefined term the rest of the prompt depends on; a default
   that contradicts the stated goal.
9. **`bug` — hallucination invitations.** "If you are unsure, make your best
   guess", "estimate the number", "fill in what is missing" on factual output.
10. **`breaking_bug` — an impossible workflow.** Step 3 needs an output step 2
    never produces; a required tool the prompt also forbids; a loop with no exit.

## Across a set of prompts

- Contradictions **between** prompts count: file the finding against the prompt
  that loses the conflict and name the other in `claim`.
- One finding per failure mode. The same flawed paragraph copied into five
  prompts is one finding with five occurrences — say so in the title.

## Emit

```json
{ "version": 2, "target_kind": "prompt", "target_ref": "<prompt-set name>", "findings": [] }
```
