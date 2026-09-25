"""render_markdown: user-controlled text must not break the tables it lands in."""

from __future__ import annotations

import json
from pathlib import Path

from conftest import EXAMPLES

from bs_score.cli import EXIT_OK, main
from bs_score.report import render_markdown

VALID = EXAMPLES / "findings.valid.json"


def test_pipes_and_newlines_in_titles_do_not_break_the_kept_table(tmp_path, capsys):
    """A title like `a | b` used to render as one column too many, and a
    newline ended the row early."""
    payload = json.loads(VALID.read_text(encoding="utf-8"))
    payload["findings"][0]["title"] = "a | b\nsecond line"
    payload["findings"][0]["path"] = "src/api | weird.py:3"
    findings = tmp_path / "f.json"
    findings.write_text(json.dumps(payload))

    code = main([str(findings), "--no-verify", "--format", "md", "-q"])
    out = capsys.readouterr().out
    assert code == EXIT_OK
    row = next(ln for ln in out.splitlines() if "a \\| b second line" in ln)
    # Five columns is six unescaped pipes; the escaped ones stay literal.
    assert row.replace("\\|", "").count("|") == 6
    assert "src/api \\| weird.py:3" in row


def _minimal_report(**overrides):
    from bs_score import depth as depth_module

    report = {
        "label": "Bullshit Score",
        "score": 5,
        "band": "minor drift",
        "verdict": "pass",
        "target_kind": "repo",
        "profile": "repo",
        "target_ref": None,
        "kept_count": 0,
        "rejected_count": 0,
        "deduped_count": 0,
        "baselined_count": 0,
        "evidence": {"mode": "skipped", "by_status": {}},
        "depth": {"status": depth_module.NOT_REQUIRED},
        "blast_radius": {"mode": "not_scanned"},
        "scoring_sha256": "0" * 64,
        "schema_sha256": "0" * 64,
        "by_type": {},
        "kept": [],
        "rejected": [],
        "baselined": [],
    }
    report.update(overrides)
    return report


def test_newlines_are_normalised_in_rejected_and_baselined_bullets():
    """Bullets are not table cells, but a newline still splits the item."""
    report = _minimal_report(
        rejected=[
            {"index": 0, "id": "f1", "reason": "missing_evidence",
             "detail": "quote is blank\nreally", "finding": {}}
        ],
        baselined=[{"id": "f2", "title": "multi\nline | title", "path": "a.py:1"}],
    )
    out = render_markdown(report)
    assert "quote is blank really" in out
    bullet = next(ln for ln in out.splitlines() if "f2" in ln)
    assert bullet.startswith("- `f2` — multi line \\| title (`a.py:1`)")
