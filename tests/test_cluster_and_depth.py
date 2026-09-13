"""Root-cause clustering and audit-depth checking.

Both exist because of a real miss: an audit of PR #2 reported one dead install
command as three findings and implied that was the whole inventory. It was in
26 files. Clustering keeps the score honest; the sweep keeps the count honest;
the depth block makes a shallow pass visible instead of indistinguishable.
"""

from __future__ import annotations

import json

import pytest
from conftest import EXAMPLES, FIXTURE_REPO

from bs_score import depth as depth_module
from bs_score.cli import EXIT_INVALID, EXIT_OK, EXIT_OVER_THRESHOLD, main

BLAST = str(EXAMPLES / "findings.blast.json")
SHALLOW = str(EXAMPLES / "findings.shallow.json")
ROOT = ["--repo-root", str(FIXTURE_REPO)]


def run(args, capsys):
    code = main([*args, "-q"])
    return code, capsys.readouterr().out


def report(args, capsys):
    return json.loads(run(args, capsys)[1])


# --- clustering ---------------------------------------------------------------


def test_three_wordings_of_one_root_cause_score_once(capsys):
    data = report([BLAST, *ROOT], capsys)
    kept = {finding["id"]: finding for finding in data["kept"]}
    assert "install-readme" in kept
    assert kept["install-readme"]["points"] == 3, "one root cause, one charge"
    assert len(kept["install-readme"]["merged"]) == 2
    assert {entry["reason"] for entry in data["deduped"]} == {"same_root_cause"}


def test_a_clusters_blast_radius_is_the_union_of_its_members(capsys):
    data = report([BLAST, *ROOT], capsys)
    kept = {finding["id"]: finding for finding in data["kept"]}["install-readme"]
    assert {occurrence["path"] for occurrence in kept["occurrences"]} == {
        "README.md",
        "docs/quickstart.md",
        "docs/install.md",
    }
    assert kept["files_affected"] == 3


def test_clustering_never_merges_across_types(capsys):
    """`cluster` is scoped by type, so a bug and a wrong_claim stay separate."""
    data = report([BLAST, *ROOT], capsys)
    assert data["kept_count"] == 2
    assert sorted(data["count_by_type"]) == ["missing_feature", "wrong_claim"]


def test_findings_without_a_cluster_still_dedupe_on_the_quote(capsys, tmp_path):
    payload = {
        "version": 2,
        "target_kind": "repo",
        "findings": [
            {
                "id": f"n{index}",
                "type": "bug",
                "title": "same quote",
                "path": path,
                "quote": "sub.add_parser('serve')",
                "target": "code",
            }
            for index, path in enumerate(["src/cli.py:9", "./src/cli.py:10"])
        ],
    }
    findings = tmp_path / "f.json"
    findings.write_text(json.dumps(payload))
    data = report([str(findings), *ROOT], capsys)
    assert data["kept_count"] == 1


# --- blast radius -------------------------------------------------------------


def test_the_count_is_measured_not_asserted(capsys):
    """A finding filed once against one file still reports every file it hits."""
    payload_path = EXAMPLES / "findings.blast.json"
    data = report([str(payload_path), *ROOT], capsys)
    assert data["blast_radius"]["mode"] == "scanned"
    assert data["blast_radius"]["tree_files"] > 0
    assert set(data["blast_radius"]["files_affected"]) >= {
        "README.md",
        "docs/install.md",
        "docs/quickstart.md",
    }


def test_no_scan_leaves_the_count_unreported(capsys):
    data = report([BLAST, *ROOT, "--no-scan"], capsys)
    assert data["blast_radius"]["mode"] == "not_scanned"
    assert data["kept"][0].get("files_affected") is None
    assert data["score"] == 5, "scanning must not change the score"


def test_scanning_does_not_change_the_score(capsys):
    scanned = report([BLAST, *ROOT], capsys)["score"]
    unscanned = report([BLAST, *ROOT, "--no-scan"], capsys)["score"]
    assert scanned == unscanned


def test_no_internal_keys_leak_into_the_report(capsys):
    for args in ([BLAST, *ROOT], [BLAST, *ROOT, "--no-scan"]):
        for finding in report(args, capsys)["kept"]:
            assert not [key for key in finding if key.startswith("_")]


# --- depth --------------------------------------------------------------------


def test_a_docs_only_pass_is_labelled_shallow(capsys):
    data = report([SHALLOW, *ROOT], capsys)
    assert data["depth"]["status"] == depth_module.SHALLOW
    assert data["depth"]["code_files_read"] == 0


def test_a_file_that_does_not_exist_earns_no_depth_credit(capsys):
    data = report([SHALLOW, *ROOT], capsys)
    assert data["depth"]["missing_files"] == ["src/does_not_exist.py"]
    assert data["depth"]["files_read"] == 2, "the phantom file is not counted"


def test_a_real_code_pass_is_labelled_deep(capsys):
    data = report([BLAST, *ROOT], capsys)
    assert data["depth"]["status"] == depth_module.DEEP
    assert data["depth"]["code_files_read"] >= 1
    assert 0 < data["depth"]["coverage"] <= 1


def test_an_audit_with_no_block_is_unreported_not_assumed_deep(capsys, tmp_path):
    payload = {
        "version": 2,
        "target_kind": "repo",
        "findings": [
            {
                "id": "a",
                "type": "bug",
                "title": "t",
                "path": "src/cli.py:9",
                "quote": "sub.add_parser('serve')",
                "target": "code",
            }
        ],
    }
    findings = tmp_path / "f.json"
    findings.write_text(json.dumps(payload))
    assert report([str(findings), *ROOT], capsys)["depth"]["status"] == depth_module.UNREPORTED


def test_review_and_prompt_audits_do_not_require_a_code_pass(capsys):
    data = report(
        [
            str(EXAMPLES / "findings.prompt.json"),
            "--repo-root",
            ".",
            "--sources",
            "examples/fixture-prompts",
        ],
        capsys,
    )
    assert data["depth"]["status"] == depth_module.NOT_REQUIRED


@pytest.mark.parametrize("payload, expected", [(SHALLOW, EXIT_OVER_THRESHOLD), (BLAST, EXIT_OK)])
def test_require_depth_gates_on_the_code_pass(payload, expected, capsys):
    assert run([payload, *ROOT, "--require-depth"], capsys)[0] == expected


def test_require_depth_needs_something_to_check_against(capsys):
    assert run([BLAST, "--no-verify", "--require-depth"], capsys)[0] == EXIT_INVALID
