# Checklist — `agent`

Audit an agent/persona config, or a directory of them. Typical roots:
`.cursor/agents/`, `.cursor/rules/`, `.claude/agents/`, `.claude/skills/`,
`AGENTS.md`, `.codex/`, `.github/agents/`, bot persona files.

The `agent` profile weights `security_issue` highest: a config that instructs
unsafe behaviour is the worst thing in this category.

## Look for

1. **`security_issue`** — instructs exfiltrating secrets, bypassing auth,
   disabling a safety gate, or committing with `--no-verify`, without a
   documented human gate. Quote the line.
2. **`wrong_claim`** — claims tools, skills, connectors, repos, or powers that
   are not wired: a skill file that is not in the workspace, a path that does not
   resolve, a tool absent from the allowlist.
3. **`missing_feature`** — "owns X" or "always does Y" with no routine, skill, or
   script behind it.
4. **Internal contradictions** — the same file says "never push" and "auto-push
   to main"; agent A forbids what agent B requires.
5. **Phantom dependencies** — referenced MCP servers, commands, or make targets
   that do not exist in the workspace.
6. **Stale routing** — a table pointing at files that moved or were deleted.

When auditing a folder, file one finding per failure mode per agent file, unless
a shared root config is the single source — then quote the root once.

Use `target: "agent"` for persona quotes, `target: "skill"` or `"code"` when the
contradiction lives in a linked skill or script.

## Emit

```json
{ "version": 2, "target_kind": "agent", "target_ref": "<path-or-dir>", "findings": [] }
```
