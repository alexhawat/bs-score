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
    expected = load_receipt(name)
    if expected.get("verdict") == "not_valid":
        assert code == 3
    else:
        assert code == 0
    assert json.loads(out.read_text(encoding="utf-8")) == expected


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
        "wild-tinycache": 8,
        "wild-greetcli": 10,
        "hallucinated": None,
        "blast": 5,
        "shallow": 2,
        "self": None,
    }


def test_a_fabricated_audit_is_not_valid():
    """Unverified fabrications are NOT_VALID — not a clean score of 0."""
    receipt = load_receipt("hallucinated")
    assert receipt["score"] is None
    assert receipt["band"] == "NOT_VALID"
    assert receipt["verdict"] == "not_valid"
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

    All eight defects were fixed, so all eight quotes are gone → NOT_VALID (nothing
    verified). If one comes back, its quote verifies again, a numeric score appears,
    and CI fails.
    """
    receipt = load_receipt("self")
    assert receipt["score"] is None
    assert receipt["band"] == "NOT_VALID"
    assert receipt["verdict"] == "not_valid"
    assert receipt["rejected_count"] == 8
    assert receipt["evidence"]["by_status"] == {"quote_not_found": 8}


def test_dogfood_properties_hold():
    """Runs `scripts/check_dogfood.py`, the same assertions CI makes.

    Executes the real CLI for each claim rather than asserting on a receipt, so a
    change that only updates the committed receipts cannot make it pass.
    """
    import subprocess
    import sys

    from conftest import REPO

    result = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "check_dogfood.py")],
        capture_output=True,
        text=True,
        cwd=REPO,
    )
    assert result.returncode == 0, result.stdout + result.stderr
