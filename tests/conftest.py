"""Shared fixtures: the repo layout and the six worked examples."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[1]
EXAMPLES = REPO / "examples"
FIXTURE_REPO = EXAMPLES / "fixture-repo"
FIXTURE_PROMPTS = EXAMPLES / "fixture-prompts"
FIXTURE_REVIEW = EXAMPLES / "fixture-review" / "review.json"

#: name -> extra CLI args, exactly as README.md prints them. Paths are relative
#: because a receipt records the root it was given, and a relative root keeps the
#: committed receipts identical on every machine.
EXAMPLE_INVOCATIONS: dict[str, list[str]] = {
    "valid": ["--repo-root", "examples/fixture-repo"],
    "review": [
        "--repo-root",
        "examples/fixture-repo",
        "--sources",
        "examples/fixture-review/review.json",
    ],
    "skill": ["--repo-root", "examples/fixture-repo"],
    "agent": ["--repo-root", "examples/fixture-repo"],
    "prompt": ["--repo-root", ".", "--sources", "examples/fixture-prompts"],
    "docs": ["--repo-root", "examples/fixture-docs"],
    "i18n": ["--repo-root", "examples/fixture-i18n"],
    "wild-tinycache": ["--repo-root", "examples/in-the-wild/tinycache"],
    "wild-greetcli": ["--repo-root", "examples/in-the-wild/greetcli"],
    "hallucinated": ["--repo-root", "examples/fixture-repo"],
    "self": ["--repo-root", "."],
}


@pytest.fixture(autouse=True)
def _run_from_repo_root(monkeypatch):
    """Examples are documented as run from the repository root; run them there."""
    monkeypatch.chdir(REPO)


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO


@pytest.fixture(scope="session")
def schema() -> dict[str, Any]:
    return json.loads((REPO / "findings.schema.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def scoring_document() -> dict[str, Any]:
    return json.loads((REPO / "scoring.json").read_text(encoding="utf-8"))


def load_example(name: str) -> dict[str, Any]:
    return json.loads((EXAMPLES / f"findings.{name}.json").read_text(encoding="utf-8"))


def load_receipt(name: str) -> dict[str, Any]:
    return json.loads((EXAMPLES / f"score.{name}.json").read_text(encoding="utf-8"))
