"""Documentation claims this repo can check itself: links and flags must be real."""

from __future__ import annotations

import re

import pytest
from conftest import REPO

from bs_score.cli import build_parser

SKIP_DIRS = {
    ".venv", ".git", ".pytest_cache", ".ruff_cache", "dist", "build",
    "fixture-repo", "fixture-docs", "fixture-i18n",
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


@pytest.mark.parametrize("document", MARKDOWN, ids=lambda p: str(p.relative_to(REPO)))
def test_documented_flags_exist(document):
    """Every `--flag` printed in the docs must be a real CLI option."""
    known = set()
    for action in build_parser()._actions:
        known.update(action.option_strings)
    # Flags belonging to other tools, or quoted as examples of a *broken* claim.
    ignore = {
        "--from", "--extra", "--wheel", "--python", "--check", "--write",
        "--prod", "--environment", "--watch", "--no-verify",
    }
    text = document.read_text(encoding="utf-8")
    mentioned = set(re.findall(r"(?<![\w-])(--[a-z][a-z0-9-]+)", text))
    unknown = mentioned - known - ignore
    assert unknown == set(), (
        f"{document.relative_to(REPO)} documents unknown flag(s): {sorted(unknown)}"
    )


def test_checklists_exist_for_every_review_type(schema):
    for kind in schema["properties"]["target_kind"]["enum"]:
        name = "pr" if kind == "branch" else kind
        assert (REPO / "checklists" / f"{name}.md").is_file(), kind
