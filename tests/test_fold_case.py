"""--fold-case: case-insensitive quote matching, off by default."""

from __future__ import annotations

import json

from bs_score import locators
from bs_score.cli import main

PAYLOAD = {
    "version": 2,
    "target_kind": "repo",
    "findings": [
        {
            "id": "c1",
            "type": "wrong_claim",
            "title": "case-changed quote",
            "path": "README.md:9",
            # The artifact says "Supports OAuth2 login out of the box".
            "quote": "supports oauth2 login out of the box",
            "target": "readme",
        }
    ],
}


def _run(tmp_path, capsys, *extra):
    findings = tmp_path / "f.json"
    findings.write_text(json.dumps(PAYLOAD))
    code = main([str(findings), "--repo-root", "examples/fixture-repo", *extra, "-q"])
    return code, json.loads(capsys.readouterr().out)


def test_exact_matching_is_the_default(tmp_path, capsys):
    """A quote that changes case is a changed quote: rejected without the flag."""
    code, report = _run(tmp_path, capsys)
    assert code == 3
    assert report["score"] is None
    assert report["verdict"] == "not_valid"
    assert report["rejected"][0]["reason"] == "unverified_evidence"
    assert report["evidence"]["fold_case"] is False


def test_fold_case_matches_case_insensitively(tmp_path, capsys):
    _, report = _run(tmp_path, capsys, "--fold-case")
    assert report["score"] == 2
    assert report["kept"][0]["evidence"]["status"] == "verified"
    assert report["evidence"]["fold_case"] is True


def test_fold_case_uses_casefold_not_lower():
    """str.casefold() handles Unicode case (ß -> ss) where lower() does not."""
    assert locators.normalize_text("STRASSE", fold_case=True) == "strasse"
    assert locators.normalize_text("Straße", fold_case=True) == "strasse"


def test_fingerprints_follow_the_fold(tmp_path, capsys):
    """With --fold-case, the dedupe fingerprint is computed on the folded form."""
    _, report = _run(tmp_path, capsys, "--fold-case")
    expected = locators.quote_fingerprint(PAYLOAD["findings"][0]["quote"], fold_case=True)
    assert report["kept"][0]["quote_fingerprint"] == expected


def test_fold_case_reaches_the_blast_radius_sweep(tmp_path, capsys):
    """A quote that verifies case-insensitively must also be *found* that way.

    The sweep and the verifier normalise independently. If only one of them
    folds case, a finding verifies and then reports zero occurrences — the
    scorer contradicting itself inside one report.
    """
    import json

    from bs_score.cli import main

    payload = {
        "version": 2,
        "target_kind": "repo",
        "findings": [
            {
                "id": "shouty",
                "type": "wrong_claim",
                "title": "same claim, different case",
                "path": "README.md",
                "quote": "RUN `DEMO INSTALL --FAST` TO SET EVERYTHING UP.",
                "target": "readme",
            }
        ],
    }
    findings = tmp_path / "f.json"
    findings.write_text(json.dumps(payload), encoding="utf-8")
    args = [str(findings), "--repo-root", "examples/fixture-repo", "-q"]

    assert main([*args, "--fold-case"]) == 0
    folded = json.loads(capsys.readouterr().out)
    assert folded["kept_count"] == 1
    assert folded["kept"][0]["evidence"]["status"] == "verified"
    assert folded["kept"][0]["files_affected"] == 1, "verified but counted nowhere"

    assert main(args) == 3
    exact = json.loads(capsys.readouterr().out)
    assert exact["kept_count"] == 0, "exact matching is still the default"
    assert exact["verdict"] == "not_valid"
    assert exact["score"] is None
