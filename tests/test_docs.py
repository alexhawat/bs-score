"""Documentation claims this repo can check itself: links and flags must be real."""

from __future__ import annotations

import re

import pytest
from conftest import REPO

from bs_score.cli import build_claims_parser, build_parser

SKIP_DIRS = {
    ".venv", ".git", ".pytest_cache", ".ruff_cache", "dist", "build",
    "fixture-repo", "fixture-docs", "fixture-i18n", "tinycache", "greetcli",
}

MARKDOWN = sorted(
    path for path in REPO.rglob("*.md") if not SKIP_DIRS & set(path.parts)
)
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")


@pytest.mark.parametrize("document", MARKDOWN, ids=lambda p: str(p.relative_to(REPO)))
def test_relative_links_resolve(document):
    """A dead link in a project about phantom references would be embarrassing."""
    broken = []
    for target in LINK.findall(document.read_text(encoding="utf-8")):
        if target.startswith(("http://", "https://", "#", "mailto:")):
            continue
        resolved = (document.parent / target.split("#", 1)[0]).resolve()
        if not resolved.exists():
            broken.append(target)
    assert broken == [], f"{document.relative_to(REPO)} links to: {broken}"


# A flag only belongs to bs-score if it is written on a line that invokes it.
BS_SCORE_LINE = re.compile(r"\b(?:bs-score|score\.py|bs_score\.cli)\b")
FLAG = re.compile(r"(?<![\w-])(--[a-z][a-z0-9-]+)")


@pytest.mark.parametrize("document", MARKDOWN, ids=lambda p: str(p.relative_to(REPO)))
def test_documented_flags_exist(document):
    """Every `--flag` printed next to a `bs-score` invocation must be a real option.

    Scoped to fenced code blocks, and within them to the part of a line that
    follows the command name — so flags belonging to other tools (`rg
    --fixed-strings`, `uvx --from`) are not swept up, and a flag invented for
    bs-score cannot hide next to one that is real.
    """
    known: set[str] = set()
    for action in [*build_parser()._actions, *build_claims_parser()._actions]:
        known.update(action.option_strings)

    unknown: set[str] = set()
    in_fence = False
    for line in document.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            continue  # prose mentions a flag; a code block invokes it
        match = BS_SCORE_LINE.search(line)
        if match is None:
            continue
        # Only what follows the command name: `uvx --from … bs-score …` puts a
        # uv flag on the same line, and it is not ours.
        unknown |= set(FLAG.findall(line[match.end():])) - known
    assert unknown == set(), (
        f"{document.relative_to(REPO)} documents unknown bs-score flag(s): {sorted(unknown)}"
    )


def test_checklists_exist_for_every_review_type(schema):
    for kind in schema["properties"]["target_kind"]["enum"]:
        name = "pr" if kind == "branch" else kind
        assert (REPO / "checklists" / f"{name}.md").is_file(), kind
