#!/usr/bin/env python3
"""Generate agents/<runtime>/{SKILL.md,README.md} from one template.

The seven wrappers were 95% identical and drifted independently; the v1 shell
snippet was wrong in all seven at once. They are generated now, and
``tests/test_wrappers.py`` fails if the committed files differ from this output.

Usage:
    python3 scripts/gen_agent_wrappers.py          # write
    python3 scripts/gen_agent_wrappers.py --check  # verify, exit 1 on drift
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
AGENTS = REPO / "agents"

RUNTIMES: dict[str, dict[str, str]] = {
    "claude": {
        "title": "Claude Code",
        "install": (
            "Copy or symlink this folder to `~/.claude/skills/bs_score` (personal) or "
            "`.claude/skills/bs_score` (project). The slash command comes from the "
            "directory name, so keep it `bs_score`."
        ),
    },
    "codex": {
        "title": "Codex",
        "install": (
            "Point Codex at this folder, or paste the root `SKILL.md` into `AGENTS.md`."
        ),
    },
    "cursor": {
        "title": "Cursor",
        "install": (
            "Add this folder under your Cursor skills path, or `@` the root `SKILL.md` "
            "from a clone."
        ),
    },
    "grok": {
        "title": "Grok Bot",
        "install": (
            "Attach the root `SKILL.md` as the bot skill, or copy this folder into the "
            "bot's skills library."
        ),
    },
    "hermes": {
        "title": "Hermes",
        "install": "Register this folder as a skill, or load the root `SKILL.md`.",
    },
    "openclaw": {
        "title": "OpenClaw",
        "install": "Register this folder as a skill, or load the root `SKILL.md`.",
    },
    "opencode": {
        "title": "OpenCode",
        "install": "Register this skill folder with OpenCode, or load the root `SKILL.md`.",
    },
}

SKILL_TEMPLATE = """---
name: bs_score
description: >-
  Use when auditing a repo, PR, branch, PR review, AI skill, agent config, or one
  or more prompts for claims vs truth and real defects: follow the canonical
  bs_score SKILL.md, emit findings JSON, then run bs-score (higher = more
  bullshit).
allowed-tools: Read, Grep, Glob, Bash
license: MIT
---

# Bullshit Score (`bs_score`) — {title}

{install}

## Canonical pack

This wrapper belongs to [alexhawat/bs_score](https://github.com/alexhawat/bs_score).

1. Read **`SKILL.md` at the repository root** — the two-pass workflow, the
   per-review-type checklists, and the hard rules live there.
2. Emit findings JSON matching `findings.schema.json` (no `score` / `points`).
3. Score it. No clone and no `PYTHONPATH` required:

```bash
uvx --from git+https://github.com/alexhawat/bs_score bs-score findings.json --repo-root .
```

(Once the package is published, `uvx bs-score …` is the short form.)

Quotes are verified against the files they name before anything is scored, so
`--repo-root` must point at the tree you audited. For prompts and review bodies,
add `--sources` (`bs-score` below is the same command):

```bash
bs-score findings.json --sources prompts/                    # prompt audit
bs-score findings.json --repo-root . --sources review.json   # review audit
```

From a clone, `python3 score.py findings.json` and `uv run bs-score …` do the same thing.

## What it audits

| `target_kind` | Scope | Weight profile |
|---------------|-------|----------------|
| `repo` | Docs claims **and** deep code | baseline |
| `pr` / `branch` | The diff and its callers | landing defects weigh more |
| `review` | A PR review vs the diff | false claims and misses weigh more |
| `skill` | Skill MD + the code it names | unimplemented claims weigh more |
| `agent` | Agent / persona configs | unsafe instructions weigh most |
| `prompt` | One or more prompts | injection and secrets weigh most |

## Fixture examples

Run from a clone of the repo:

```bash
uv run bs-score examples/findings.valid.json  --repo-root examples/fixture-repo   # 17
uv run bs-score examples/findings.review.json --repo-root examples/fixture-repo \\
    --sources examples/fixture-review/review.json                                # 10
uv run bs-score examples/findings.skill.json  --repo-root examples/fixture-repo   # 7
uv run bs-score examples/findings.agent.json  --repo-root examples/fixture-repo   # 6
uv run bs-score examples/findings.prompt.json --sources examples/fixture-prompts  # 18
uv run bs-score examples/findings.hallucinated.json \\
    --repo-root examples/fixture-repo                                            # 0
```

That last one is the point: a fabricated audit scores zero because none of its
quotes exist.

Never invent the score — report only what `bs-score` printed.
"""

README_TEMPLATE = """# bs_score — {title}

Wrapper for **{title}**. Canonical skill and scorer:
[alexhawat/bs_score](https://github.com/alexhawat/bs_score).

{install}

Scoring needs no clone:

```bash
uvx --from git+https://github.com/alexhawat/bs_score bs-score findings.json --repo-root .
```

<!-- generated by scripts/gen_agent_wrappers.py; edit the template, not this file -->
"""


def render(runtime: str) -> dict[str, str]:
    """Return ``{filename: content}`` for one runtime."""
    context = RUNTIMES[runtime]
    return {
        "SKILL.md": SKILL_TEMPLATE.format(**context),
        "README.md": README_TEMPLATE.format(**context),
    }


def main(argv: list[str] | None = None) -> int:
    """Write (or check) every wrapper."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Exit 1 if any file is out of date")
    args = parser.parse_args(argv)

    drift: list[str] = []
    for runtime in RUNTIMES:
        directory = AGENTS / runtime
        directory.mkdir(parents=True, exist_ok=True)
        for filename, content in render(runtime).items():
            path = directory / filename
            current = path.read_text(encoding="utf-8") if path.is_file() else None
            if current == content:
                continue
            if args.check:
                drift.append(str(path.relative_to(REPO)))
            else:
                path.write_text(content, encoding="utf-8")

    if drift:
        print("out of date (run scripts/gen_agent_wrappers.py):", file=sys.stderr)
        for path in drift:
            print(f"  {path}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
