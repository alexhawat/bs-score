"""--format sarif: valid SARIF 2.1.0, stable against a golden file."""

from __future__ import annotations

import json

from conftest import EXAMPLES, FIXTURE_REPO, REPO

from bs_score.cli import EXIT_OK, main

GOLDEN = REPO / "tests" / "golden" / "report.valid.sarif"
VALID = str(EXAMPLES / "findings.valid.json")
ROOT = ["--repo-root", str(FIXTURE_REPO)]


def _sarif(capsys):
    code = main([VALID, *ROOT, "--format", "sarif", "-q"])
    assert code == EXIT_OK
    return json.loads(capsys.readouterr().out)


def test_sarif_matches_the_golden_file(capsys):
    assert _sarif(capsys) == json.loads(GOLDEN.read_text(encoding="utf-8"))


def test_sarif_is_well_formed(capsys):
    sarif = _sarif(capsys)
    assert sarif["version"] == "2.1.0"
    assert sarif["$schema"].endswith("sarif-2.1.0.json")
    run = sarif["runs"][0]
    assert run["tool"]["driver"]["name"] == "bs-score"
    assert run["properties"]["bs_score"] == 17

    rule_ids = {rule["id"] for rule in run["tool"]["driver"]["rules"]}
    assert rule_ids == {"breaking_bug", "bug", "missing_feature", "security_issue", "wrong_claim"}
    for result in run["results"]:
        assert result["ruleId"] in rule_ids
        assert result["level"] in {"error", "warning", "note"}
        location = result["locations"][0]["physicalLocation"]
        assert location["artifactLocation"]["uri"]


def test_severity_levels_follow_the_type(capsys):
    sarif = _sarif(capsys)
    levels = {r["ruleId"]: r["level"] for r in sarif["runs"][0]["results"]}
    assert levels["breaking_bug"] == "error"
    assert levels["security_issue"] == "error"
    assert levels["wrong_claim"] == "note"


def test_rejected_and_baselined_findings_are_not_results(capsys, tmp_path):
    # findings.valid.json has one blank-evidence finding that is rejected.
    sarif = _sarif(capsys)
    assert len(sarif["runs"][0]["results"]) == 5  # kept only

    baseline = tmp_path / "b.json"
    main([VALID, *ROOT, "--write-baseline", str(baseline), "-q"])
    capsys.readouterr()
    code = main([VALID, *ROOT, "--baseline", str(baseline), "--format", "sarif", "-q"])
    assert code == EXIT_OK
    sarif = json.loads(capsys.readouterr().out)
    assert sarif["runs"][0]["results"] == []
