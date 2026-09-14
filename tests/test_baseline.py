"""--baseline suppresses known findings; --write-baseline captures them."""

from __future__ import annotations

import json

import pytest
from conftest import EXAMPLES, FIXTURE_REPO

from bs_score.baseline import BaselineError, load_baseline, render_baseline
from bs_score.cli import EXIT_INVALID, EXIT_OK, main

VALID = str(EXAMPLES / "findings.valid.json")
ROOT = ["--repo-root", str(FIXTURE_REPO)]


def _run(args, capsys):
    code = main([*args, "-q"])
    return code, json.loads(capsys.readouterr().out)


def test_write_then_baseline_scores_only_new_findings(tmp_path, capsys):
    baseline = tmp_path / ".bs-score-baseline.json"
    code, report = _run([VALID, *ROOT, "--write-baseline", str(baseline)], capsys)
    assert code == EXIT_OK
    assert report["score"] == 17  # writing does not suppress

    # Same findings, now baselined: nothing is new, nothing scores.
    code, report = _run([VALID, *ROOT, "--baseline", str(baseline)], capsys)
    assert code == EXIT_OK
    assert report["score"] == 0
    assert report["band"] == "clean"
    assert report["kept_count"] == 0
    # f3-dup no longer merges into f3 (baselined findings don't register dedupe
    # keys), so it is baselined on its own identical key.
    assert report["baselined_count"] == 6

    # One new finding on top of the baseline scores on its own.
    payload = json.loads((EXAMPLES / "findings.valid.json").read_text())
    payload["findings"].append(
        {
            "id": "new-1",
            "type": "wrong_claim",
            "title": "new claim, not in the baseline",
            "path": "README.md:11",
            "quote": "API key authentication",
            "target": "readme",
        }
    )
    findings = tmp_path / "f.json"
    findings.write_text(json.dumps(payload))
    _, report = _run([str(findings), *ROOT, "--baseline", str(baseline)], capsys)
    assert report["score"] == 2
    assert report["kept_count"] == 1
    assert report["baselined_count"] == 6


def test_fail_over_gates_on_new_findings_only(tmp_path, capsys):
    baseline = tmp_path / "b.json"
    _run([VALID, *ROOT, "--write-baseline", str(baseline)], capsys)
    code, _ = _run([VALID, *ROOT, "--baseline", str(baseline), "--fail-over", "0"], capsys)
    assert code == EXIT_OK  # over threshold only if *new* findings score


def test_malformed_baseline_is_a_usage_error(tmp_path, capsys):
    bad = tmp_path / "b.json"
    bad.write_text('{"findings": [{"type": 1}]}')
    code = main([VALID, *ROOT, "--baseline", str(bad), "-q"])
    capsys.readouterr()
    assert code == EXIT_INVALID
    with pytest.raises(BaselineError):
        load_baseline(bad)


def test_render_baseline_round_trip():
    kept = [
        {
            "type": "bug",
            "canonical_file": "src/api.py",
            "quote_fingerprint": "abc123",
            "title": "t",
        }
    ]
    document = render_baseline(kept)
    assert document["version"] == 1
    assert document["findings"][0]["file"] == "src/api.py"


def test_refreshing_a_baseline_in_place_keeps_it(tmp_path, capsys):
    """`--baseline b --write-baseline b` used to truncate b to nothing.

    Baselined findings are not in ``kept``, and only ``kept`` was written, so the
    obvious way to refresh a baseline emptied it and the next run scored every
    finding again.
    """
    baseline = tmp_path / "b.json"
    _run([VALID, *ROOT, "--write-baseline", str(baseline)], capsys)
    before = json.loads(baseline.read_text())["findings"]
    assert before

    _run([VALID, *ROOT, "--baseline", str(baseline), "--write-baseline", str(baseline)], capsys)
    after = json.loads(baseline.read_text())["findings"]
    assert {tuple(sorted(e.items())) for e in after} == {
        tuple(sorted(e.items())) for e in before
    }

    # And it still suppresses on the next run.
    _, report = _run([VALID, *ROOT, "--baseline", str(baseline)], capsys)
    assert report["score"] == 0


def test_render_baseline_dedupes_repeated_entries():
    """Baselined findings skip dedupe, so the same key can arrive twice."""
    entry = {
        "type": "bug",
        "canonical_file": "src/api.py",
        "quote_fingerprint": "abc123",
        "title": "t",
    }
    assert len(render_baseline([entry, dict(entry), entry])["findings"]) == 1
