"""llms.txt and llms-full.txt are generated from canonical sources."""

from __future__ import annotations

import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1] / "scripts"))

import gen_llms_txt  # noqa: E402
from conftest import REPO  # noqa: E402


def test_llms_files_are_up_to_date():
    assert gen_llms_txt.main(["--check"]) == 0


def test_llms_txt_follows_the_llmstxt_shape():
    text = (REPO / "llms.txt").read_text(encoding="utf-8")
    assert text.startswith("# bs_score\n\n> ")
    assert "uvx --from git+https://github.com/alexhawat/bs_score bs-score" in text
    for name in ("SKILL.md", "findings.schema.json", "scoring.json", "checklists/", "examples"):
        assert name in text


def test_llms_full_flattens_the_canonical_sources():
    text = (REPO / "llms-full.txt").read_text(encoding="utf-8")
    skill = (REPO / "SKILL.md").read_text(encoding="utf-8")
    assert skill in text  # SKILL.md verbatim
    for kind in ("repo", "pr", "review", "skill", "agent", "prompt", "docs"):
        assert f"`{kind}`" in text  # every weight-profile column
    assert "| `wrong_claim` |" in text  # the rendered weight table
    assert "breaking_bug" in text and "security_issue" in text  # type enum
    assert "--fail-over" in text and "--emit-findings" in text  # CLI surface
