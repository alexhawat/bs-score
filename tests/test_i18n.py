"""Quotes are verified verbatim in the artifact's own language."""

from __future__ import annotations

import json

from conftest import EXAMPLES, load_example, load_receipt

from bs_score.cli import main

I18N = EXAMPLES / "fixture-i18n"


def test_french_and_japanese_quotes_verify(capsys):
    code = main(
        [str(EXAMPLES / "findings.i18n.json"), "--repo-root", str(I18N), "-q"]
    )
    assert code == 0
    report = json.loads(capsys.readouterr().out)
    assert report["evidence"]["by_status"] == {"verified": 2}
    assert report["score"] == 10  # 2 wrong_claims x 5 under the docs profile
    assert report["band"] == "misleading"


def test_the_receipt_matches():
    assert load_receipt("i18n")["score"] == 10


def test_a_translated_quote_does_not_verify(tmp_path, capsys):
    """NFKC folding is not transliteration: a translated quote is a lie."""
    translated = dict(load_example("i18n")["findings"][0])
    translated["id"] = "fr-1-translated"
    translated["quote"] = "The configuration file is `config/app.yaml`."
    payload = {"version": 2, "target_kind": "docs", "findings": [translated]}
    findings = tmp_path / "f.json"
    findings.write_text(json.dumps(payload), encoding="utf-8")

    code = main([str(findings), "--repo-root", str(I18N), "-q"])
    assert code == 0
    report = json.loads(capsys.readouterr().out)
    assert report["score"] == 0
    assert report["rejected"][0]["reason"] == "unverified_evidence"
