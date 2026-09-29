"""Score bands: display-only labels over the raw sum."""

from __future__ import annotations

import json

import pytest
from conftest import EXAMPLES, FIXTURE_REPO

from bs_score.cli import main
from bs_score.report import score_band

VALID = str(EXAMPLES / "findings.valid.json")
ROOT = ["--repo-root", str(FIXTURE_REPO)]


@pytest.mark.parametrize(
    "score, band",
    [
        (0, "clean"),
        (1, "minor drift"),
        (5, "minor drift"),
        (6, "misleading"),
        (15, "misleading"),
        (16, "bullshit"),
        (10_000, "bullshit"),
    ],
)
def test_band_boundaries(score, band):
    assert score_band(score) == band


def test_report_carries_the_band(capsys):
    code = main([VALID, *ROOT, "-q"])
    assert code == 0
    report = json.loads(capsys.readouterr().out)
    assert report["score"] == 17
    assert report["band"] == "bullshit"


def test_markdown_report_shows_the_band(capsys):
    main([VALID, *ROOT, "--format", "md", "-q"])
    out = capsys.readouterr().out
    assert out.startswith("## Bullshit Score: **17** (bullshit)")


def test_all_unverified_is_not_valid(capsys):
    from bs_score.cli import EXIT_NOT_VALID

    code = main([str(EXAMPLES / "findings.hallucinated.json"), *ROOT, "-q"])
    assert code == EXIT_NOT_VALID
    report = json.loads(capsys.readouterr().out)
    assert report["score"] is None
    assert report["band"] == "NOT_VALID"
    assert report["verdict"] == "not_valid"


def test_all_unverified_stays_not_valid_with_depth_gate(capsys):
    from bs_score.cli import EXIT_NOT_VALID

    code = main(
        [str(EXAMPLES / "findings.hallucinated.json"), *ROOT, "--require-depth", "-q"]
    )
    assert code == EXIT_NOT_VALID
    report = json.loads(capsys.readouterr().out)
    assert report["score"] is None
    assert report["band"] == "NOT_VALID"
    assert report["verdict"] == "not_valid"


def test_empty_findings_still_score_zero(capsys, tmp_path):
    """Empty findings [] is a real clean 0 — distinct from all-unverified."""
    findings = tmp_path / "empty.json"
    findings.write_text(
        '{"version": 2, "target_kind": "repo", "target_ref": "empty", "findings": []}\n',
        encoding="utf-8",
    )
    code = main([str(findings), *ROOT, "-q"])
    assert code == 0
    report = json.loads(capsys.readouterr().out)
    assert report["score"] == 0
    assert report["band"] == "clean"
    assert report["verdict"] == "pass"
