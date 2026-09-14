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


def test_clean_audit_is_labelled_clean(capsys):
    main([str(EXAMPLES / "findings.hallucinated.json"), *ROOT, "-q"])
    report = json.loads(capsys.readouterr().out)
    assert report["band"] == "clean"
