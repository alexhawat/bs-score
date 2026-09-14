#!/usr/bin/env python3
"""Generate llms.txt and llms-full.txt from the canonical sources.

Both files are *generated* — an llms file that drifts from SKILL.md or
scoring.json is exactly the kind of wrong info this project exists to catch.

- ``llms.txt`` follows llmstxt.org: a short index with links.
- ``llms-full.txt`` flattens everything an agent needs into one fetch:
  SKILL.md verbatim, the weight table rendered from ``scoring.json``, the
  findings contract summarised from ``findings.schema.json``, and the CLI
  surface rendered from the argparse definitions.

Usage:
    python3 scripts/gen_llms_txt.py          # write
    python3 scripts/gen_llms_txt.py --check  # verify, exit 1 on drift
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from bs_score.cli import build_claims_parser, build_parser  # noqa: E402

RAW = "https://raw.githubusercontent.com/alexhawat/bs_score/main"

PITCH = (
    "Your AI auditor lies. bs_score catches it — every claim is quoted, every "
    "quote is verified, and the score comes from code, not prose. The LLM finds "
    "defects and quotes the evidence; the bs-score CLI verifies every quote "
    "against the artifact it names, then scores what survived. Higher = more "
    "bullshit."
)

INSTALL = "uvx --from git+https://github.com/alexhawat/bs_score bs-score --help"


def weight_table(scoring: dict) -> str:
    """Render the full weight table from scoring.json (never hand-written)."""
    profiles = scoring["profiles"]
    kinds = ["repo", "pr", "review", "skill", "agent", "prompt", "docs"]
    kinds = [k for k in kinds if k in profiles] + sorted(set(profiles) - set(kinds))
    header = "| type | " + " | ".join(f"`{k}`" for k in kinds) + " |"
    rule = "|" + "---|" + "-------:|" * len(kinds)
    rows = []
    for finding_type in scoring["types"]:
        cells = [str(profiles[k]["weights"][finding_type]) for k in kinds]
        rows.append(f"| `{finding_type}` | " + " | ".join(cells) + " |")
    return "\n".join([header, rule, *rows])


def schema_summary(schema: dict) -> str:
    """Flatten the findings contract into prose an agent can rely on."""
    kinds = schema["properties"]["target_kind"]["enum"]
    item = schema["properties"]["findings"]["items"]
    fields = item["properties"]
    lines = [
        f"- Envelope: {{version: 1|2, target_kind: one of {kinds}, "
        "target_ref?: string, findings: [...]}. No other keys; `score` and "
        "`points` in a payload are rejected.",
        f"- Finding required fields: {item['required']}; optional: "
        f"{sorted(set(fields) - set(item['required']))}. No other keys.",
        f"- finding.type is one of {fields['type']['enum']}.",
        f"- finding.target is one of {fields['target']['enum']}.",
        "- finding.path: `file[:line[-line]]`, `prompt:<id>[:line]`, or "
        "`review:` / `pull/<n>/reviews/<id>` locator. finding.quote: verbatim, "
        "contiguous, whitespace/typography-normalised at verification.",
        "- finding.confidence: 0–1, display-only.",
    ]
    return "\n".join(lines)


def cli_flags() -> str:
    """Render both parsers' options so the documented CLI cannot drift."""
    sections = []
    for prog, parser in (("bs-score FINDINGS", build_parser()),
                         ("bs-score claims DOC", build_claims_parser())):
        lines = [f"`{prog}` options:"]
        for action in parser._actions:
            if not action.option_strings:
                continue
            names = ", ".join(action.option_strings)
            help_text = (action.help or "").replace("\n", " ")
            lines.append(f"- `{names}` — {help_text}")
        sections.append("\n".join(lines))
    return "\n\n".join(sections)


def render_llms_txt() -> str:
    return f"""# bs_score

> {PITCH}

Install (no clone): `{INSTALL}`

## Canonical

- [SKILL.md]({RAW}/SKILL.md): the agent recipe — workflow, finding object, hard rules
- [findings.schema.json]({RAW}/findings.schema.json): the findings contract, enforced in full
- [scoring.json]({RAW}/scoring.json): the pinned per-review-type weights

## Checklists (one per review type)

- [repo]({RAW}/checklists/repo.md): README claims + deep code pass
- [pr]({RAW}/checklists/pr.md): a diff and its callers (also `branch`)
- [review]({RAW}/checklists/review.md): a PR review graded against the diff
- [skill]({RAW}/checklists/skill.md): SKILL.md + every script it names
- [agent]({RAW}/checklists/agent.md): agent/persona configs
- [prompt]({RAW}/checklists/prompt.md): one or many prompts
- [docs]({RAW}/checklists/docs.md): one document, claims only

## Examples

- [examples/]({RAW}/examples/README.md): worked findings + byte-exact score receipts
- [hallucinated]({RAW}/examples/findings.hallucinated.json): a fabricated audit scores 0

## Full context

- [llms-full.txt]({RAW}/llms-full.txt): everything above, flattened into one file
"""


def render_llms_full() -> str:
    skill = (REPO / "SKILL.md").read_text(encoding="utf-8")
    scoring = json.loads((REPO / "scoring.json").read_text(encoding="utf-8"))
    schema = json.loads((REPO / "findings.schema.json").read_text(encoding="utf-8"))
    return f"""# bs_score — full context for agents

{PITCH}

Install (no clone): `{INSTALL}`

Everything below is generated from the canonical sources by
scripts/gen_llms_txt.py; CI fails if it drifts.

================================================================================
SKILL.md (verbatim)
================================================================================

{skill}
================================================================================
Weight table (rendered from scoring.json)
================================================================================

One score, starting at 0; higher = more bullshit. Score bands (display-only):
0 clean · 1–5 minor drift · 6–15 misleading · 16+ bullshit.

{weight_table(scoring)}

================================================================================
Findings contract (summarised from findings.schema.json)
================================================================================

{schema_summary(schema)}

================================================================================
CLI surface (rendered from the argparse definitions)
================================================================================

{cli_flags()}
"""


def main(argv: list[str] | None = None) -> int:
    """Write (or check) llms.txt and llms-full.txt."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Exit 1 if any file is out of date")
    args = parser.parse_args(argv)

    rendered = {"llms.txt": render_llms_txt(), "llms-full.txt": render_llms_full()}
    drift: list[str] = []
    for name, content in rendered.items():
        path = REPO / name
        current = path.read_text(encoding="utf-8") if path.is_file() else None
        if current == content:
            continue
        if args.check:
            drift.append(name)
        else:
            path.write_text(content, encoding="utf-8")

    if drift:
        print("out of date (run scripts/gen_llms_txt.py):", file=sys.stderr)
        for name in drift:
            print(f"  {name}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
