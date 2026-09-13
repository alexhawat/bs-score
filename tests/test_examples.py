"""Every worked example scores exactly what its committed receipt says."""

from __future__ import annotations

import json

import pytest
from conftest import EXAMPLE_INVOCATIONS, EXAMPLES, load_receipt

from bs_score.cli import main


@pytest.mark.parametrize("name", sorted(EXAMPLE_INVOCATIONS))
def test_example_matches_its_receipt(name, capsys, tmp_path):
    out = tmp_path / "report.json"
    code = main(
        [str(EXAMPLES / f"findings.{name}.json"), *EXAMPLE_INVOCATIONS[name], "-o", str(out), "-q"]
    )
    capsys.readouterr()
    assert code == 0
    assert json.loads(out.read_text(encoding="utf-8")) == load_receipt(name)


def test_documented_scores():
    """The numbers README.md and SKILL.md print."""
    assert {name: load_receipt(name)["score"] for name in EXAMPLE_INVOCATIONS} == {
        "valid": 17,
        "review": 10,
        "skill": 7,
        "agent": 6,
        "prompt": 18,
        "docs": 15,
        "i18n": 10,
        "hallucinated": 0,
        "self": 0,
    }


def test_a_fabricated_audit_scores_zero():
    """The whole point: unverifiable findings earn no points."""
    receipt = load_receipt("hallucinated")
    assert receipt["score"] == 0
    assert receipt["kept_count"] == 0
    assert {entry["reason"] for entry in receipt["rejected"]} == {"unverified_evidence"}


def test_every_example_verifies_its_evidence():
    for name in EXAMPLE_INVOCATIONS:
        receipt = load_receipt(name)
        assert receipt["evidence"]["mode"] == "verified", name
        assert receipt["evidence"]["repo_root"], name


def test_receipts_record_what_produced_them():
    for name in EXAMPLE_INVOCATIONS:
        receipt = load_receipt(name)
        for key in ("scoring_sha256", "schema_sha256", "findings_sha256", "profile", "weights"):
            assert receipt[key], f"{name} receipt is missing {key}"


def test_the_v1_audit_no_longer_verifies_against_this_tree():
    """`examples/findings.self.json` is the v1 audit of this repo, kept as a gate.

    All eight defects were fixed, so all eight quotes are gone. If one comes
    back, its quote verifies again, the score rises above zero, and CI fails.
    """
    receipt = load_receipt("self")
    assert receipt["score"] == 0
    assert receipt["rejected_count"] == 8
    assert receipt["evidence"]["by_status"] == {"quote_not_found": 8}
