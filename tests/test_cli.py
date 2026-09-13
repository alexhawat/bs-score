"""CLI contract: exit codes, output formats, and the verification switches."""

from __future__ import annotations

import json

import pytest
from conftest import EXAMPLES, FIXTURE_PROMPTS, FIXTURE_REPO

from bs_score.cli import EXIT_INVALID, EXIT_OK, EXIT_OVER_THRESHOLD, main

VALID = str(EXAMPLES / "findings.valid.json")
ROOT = ["--repo-root", str(FIXTURE_REPO)]


def run(args, capsys):
    code = main([*args, "-q"])
    return code, capsys.readouterr().out


def test_scoring_succeeds(capsys):
    code, out = run([VALID, *ROOT], capsys)
    assert code == EXIT_OK
    assert json.loads(out)["score"] == 17


def test_fail_over_gates_ci(capsys):
    assert run([VALID, *ROOT, "--fail-over", "16"], capsys)[0] == EXIT_OVER_THRESHOLD
    assert run([VALID, *ROOT, "--fail-over", "17"], capsys)[0] == EXIT_OK


def test_verdict_is_recorded_in_the_report(capsys):
    _, out = run([VALID, *ROOT, "--fail-over", "5"], capsys)
    report = json.loads(out)
    assert report["verdict"] == "fail"
    assert report["fail_over"] == 5


def test_markdown_format(capsys):
    _, out = run([VALID, *ROOT, "--format", "md"], capsys)
    assert out.startswith("## Bullshit Score: **17**")


def test_missing_repo_root_is_a_usage_error(capsys):
    assert run([VALID, "--repo-root", "does/not/exist"], capsys)[0] == EXIT_INVALID


def test_require_evidence_contradicts_no_verify(capsys):
    assert run([VALID, *ROOT, "--no-verify", "--require-evidence"], capsys)[0] == EXIT_INVALID


def test_no_verify_stamps_the_report(capsys):
    _, out = run([VALID, "--no-verify"], capsys)
    report = json.loads(out)
    assert report["evidence"]["mode"] == "skipped"
    assert report["score"] == 17


def test_unverifiable_locators_are_kept_by_default_and_dropped_under_require_evidence(capsys):
    """A review body with no --sources cannot be checked either way."""
    review = str(EXAMPLES / "findings.review.json")
    _, out = run([review, *ROOT], capsys)
    lenient = json.loads(out)
    assert lenient["evidence"]["by_status"]["not_verifiable"] == 2
    assert lenient["kept_count"] == 3

    _, out = run([review, *ROOT, "--require-evidence"], capsys)
    strict = json.loads(out)
    assert strict["kept_count"] == 1
    assert strict["score"] < lenient["score"]


def test_prompt_sources_make_prompt_quotes_verifiable(capsys):
    prompt = str(EXAMPLES / "findings.prompt.json")
    _, out = run(
        [prompt, "--repo-root", str(FIXTURE_PROMPTS), "--sources", str(FIXTURE_PROMPTS),
         "--require-evidence"],
        capsys,
    )
    report = json.loads(out)
    assert report["score"] == 18
    assert report["profile"] == "prompt"
    assert report["evidence"]["by_status"] == {"verified": 5}


def test_unknown_prompt_id_is_rejected_not_ignored(capsys, tmp_path):
    payload = {
        "version": 2,
        "target_kind": "prompt",
        "findings": [
            {
                "id": "p1",
                "type": "bug",
                "title": "t",
                "path": "prompt:does-not-exist",
                "quote": "whatever",
                "target": "prompt",
            }
        ],
    }
    findings = tmp_path / "f.json"
    findings.write_text(json.dumps(payload))
    _, out = run([str(findings), "--sources", str(FIXTURE_PROMPTS)], capsys)
    report = json.loads(out)
    assert report["score"] == 0
    assert report["rejected"][0]["reason"] == "unverified_evidence"


def test_strict_lines_rejects_a_real_quote_at_the_wrong_line(capsys, tmp_path):
    payload = {
        "version": 2,
        "target_kind": "repo",
        "findings": [
            {
                "id": "p1",
                "type": "bug",
                "title": "real quote, invented line",
                "path": "src/api.py:400",
                "quote": "page = int(params.get('page', 1)) - 1 if page else 0",
                "target": "code",
            }
        ],
    }
    findings = tmp_path / "f.json"
    findings.write_text(json.dumps(payload))

    _, out = run([str(findings), *ROOT], capsys)
    assert json.loads(out)["kept"][0]["evidence"]["status"] == "verified_wrong_line"

    _, out = run([str(findings), *ROOT, "--strict-lines"], capsys)
    assert json.loads(out)["score"] == 0


def test_paths_outside_the_root_are_rejected(capsys, tmp_path):
    payload = {
        "version": 2,
        "target_kind": "repo",
        "findings": [
            {
                "id": "p1",
                "type": "security_issue",
                "title": "escape",
                "path": "../../../../etc/passwd:1",
                "quote": "root",
                "target": "code",
            }
        ],
    }
    findings = tmp_path / "f.json"
    findings.write_text(json.dumps(payload))
    _, out = run([str(findings), *ROOT], capsys)
    report = json.loads(out)
    assert report["score"] == 0
    assert "outside_root" in report["rejected"][0]["detail"] or "path_not_found" in report[
        "rejected"
    ][0]["detail"]


def test_output_file_matches_stdout(capsys, tmp_path):
    out_path = tmp_path / "report.json"
    _, out = run([VALID, *ROOT, "-o", str(out_path)], capsys)
    assert out_path.read_text(encoding="utf-8") == out


@pytest.mark.parametrize("flag", ["--version"])
def test_version_flag(flag, capsys):
    with pytest.raises(SystemExit) as excinfo:
        main([flag])
    assert excinfo.value.code == 0
