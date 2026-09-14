"""bs-score claims: mechanical claim verification with no LLM."""

from __future__ import annotations

import json

import pytest
from conftest import EXAMPLES, REPO

from bs_score import claims
from bs_score.cli import EXIT_INVALID, EXIT_OK, EXIT_OVER_THRESHOLD, main

FIXTURE_DOCS = EXAMPLES / "fixture-docs"
GUIDE = FIXTURE_DOCS / "guide.md"


def _by_verdict(report):
    out = {"pass": [], "fail": [], "skip": []}
    for claim in report:
        out[claim["verdict"]].append(claim)
    return out


def test_guide_yields_exactly_its_three_false_claims():
    """The fixture guide's three lies are all mechanically provable."""
    report = [c.as_dict() for c in claims.audit_document(GUIDE, FIXTURE_DOCS)]
    failed = _by_verdict(report)["fail"]
    assert {(c["kind"], c["claim"]) for c in failed} == {
        ("version", "installable on Python 3.9"),
        ("path", "path `config/poller.yaml` exists"),
        ("flag", "`poller` accepts --serve"),
    }


def test_true_claims_pass():
    report = [c.as_dict() for c in claims.audit_document(GUIDE, FIXTURE_DOCS)]
    passed = _by_verdict(report)["pass"]
    assert any(c["kind"] == "command" and "poller" in c["claim"] for c in passed)
    assert any(c["kind"] == "flag" and "--once" in c["claim"] for c in passed)


def test_cli_exit_codes(capsys):
    code = main(["claims", str(GUIDE), "--repo-root", str(FIXTURE_DOCS), "-q"])
    assert code == EXIT_OVER_THRESHOLD  # failures present
    capsys.readouterr()
    assert main(["claims", "does/not/exist.md", "-q"]) == EXIT_INVALID
    assert main(["claims", str(GUIDE), "--repo-root", "does/not/exist", "-q"]) == EXIT_INVALID


def test_cli_json_shape(capsys):
    main(["claims", str(GUIDE), "--repo-root", str(FIXTURE_DOCS), "-q"])
    report = json.loads(capsys.readouterr().out)
    assert report
    for claim in report:
        assert set(claim) == {"kind", "claim", "verdict", "evidence", "line"}
        assert claim["verdict"] in {"pass", "fail", "skip"}


def test_emit_findings_round_trips_through_the_scorer(tmp_path, capsys):
    """--emit-findings output is a scorable payload whose quotes all verify."""
    code = main(
        ["claims", str(GUIDE), "--repo-root", str(FIXTURE_DOCS), "--emit-findings", "-q"]
    )
    assert code == EXIT_OVER_THRESHOLD
    payload = json.loads(capsys.readouterr().out)
    assert payload["target_kind"] == "docs"
    assert len(payload["findings"]) == 3

    findings = tmp_path / "findings.json"
    findings.write_text(json.dumps(payload))
    code = main([str(findings), "--repo-root", str(FIXTURE_DOCS), "-q"])
    assert code == EXIT_OK
    report = json.loads(capsys.readouterr().out)
    assert report["rejected_count"] == 0
    assert report["score"] == 15  # 3 wrong_claims x 5 under the docs profile


def test_paths(tmp_path):
    (tmp_path / "real").mkdir()
    (tmp_path / "real/file.txt").write_text("x")
    found = claims.check_paths("see `real/file.txt` and `real/missing.txt`", tmp_path)
    assert [(c.claim, c.verdict) for c in found] == [
        ("path `real/file.txt` exists", "pass"),
        ("path `real/missing.txt` exists", "fail"),
    ]


def test_non_paths_are_not_path_claims(tmp_path):
    text = "use `--force`, set `FOO=bar`, visit `https://x.dev/a.md`, run `pip install`"
    assert claims.check_paths(text, tmp_path) == []


def test_versions(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nversion = "1.2.3"\nrequires-python = ">=3.11"\n'
    )
    facts = claims.load_project_facts(tmp_path)
    report = claims.check_versions("Now at version 1.2.3. Needs Python 3.10.", facts)
    assert [(c.verdict) for c in report] == ["pass", "fail"]


def test_links(tmp_path):
    doc = tmp_path / "doc.md"
    (tmp_path / "other.md").write_text("# Target\n")
    doc.write_text(
        "# Title\n\n[ok](other.md) [anchor](#title) [bad](gone.md) [web](https://x.dev)\n"
    )
    report = claims.check_links(doc.read_text(), doc, tmp_path)
    by_span = {(c.claim, c.verdict) for c in report}
    assert ("link target other.md resolves", "pass") in by_span
    assert ("anchor #title exists", "pass") in by_span
    assert ("link target gone.md resolves", "fail") in by_span
    assert ("URL https://x.dev responds", "skip") in by_span


def test_code_blocks():
    text = (
        "```python\nx = 1\n```\n"
        "```python\nx = (\n```\n"
        "```json\n{\"a\": 1}\n```\n"
        "```json\n{bad}\n```\n"
        "```bash\necho ok\n```\n"
        "```yaml\na: 1\n```\n"
    )
    report = claims.check_code_blocks(text)
    verdicts = [(c.kind, c.verdict) for c in report]
    assert verdicts.count(("code_block", "pass")) >= 2  # good python + good json
    assert verdicts.count(("code_block", "fail")) == 2  # broken python + broken json
    assert ("code_block", "skip") in verdicts  # yaml has no parser here


def test_unknown_commands_are_not_claimed(tmp_path):
    """Only declared entry points are checked; everything else is out of scope."""
    facts = claims.ProjectFacts(scripts={"poller": "poller.cli:main"})
    assert claims.check_commands("run `make install` then `poller --once`", facts) != []
    assert claims.check_commands("run `make install`", facts) == []


#: Illustrative locator *forms* in SKILL.md's path table — examples of syntax,
#: not claims that these files exist. Same idea as the ignore-set in test_docs.
ILLUSTRATIVE_SPANS = {"`.claude/agents/x.md`", "`.cursor/rules/y.mdc`", "`src/a.py`"}


@pytest.mark.parametrize("document", ["README.md", "SKILL.md"])
def test_this_repos_own_docs_have_no_failing_claims(document):
    """Dogfood: our own top-level docs must pass the mechanical checks."""
    report = claims.audit_document(REPO / document, REPO)
    failed = [c for c in report if c.verdict == "fail" and c.span not in ILLUSTRATIVE_SPANS]
    assert failed == [], [(c.claim, c.evidence) for c in failed]


def test_a_flag_on_the_next_line_is_not_this_commands_flag(tmp_path):
    """`\\s+` used to cross newlines, so another tool's flag became a false claim."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\n[project.scripts]\nbs-score = "bs_score.cli:run"\n'
    )
    module = tmp_path / "src" / "bs_score"
    module.mkdir(parents=True)
    (module / "cli.py").write_text(
        "import argparse\np = argparse.ArgumentParser()\np.add_argument('--repo-root')\n"
    )
    doc = tmp_path / "doc.md"
    doc.write_text("    bs-score findings.json\n    ruff check --totally-made-up .\n")

    flags = [c for c in claims.audit_document(doc, tmp_path) if c.kind == "flag"]
    assert [c.claim for c in flags if c.verdict == "fail"] == []


def test_a_heading_inside_a_fence_does_not_satisfy_an_anchor(tmp_path):
    """```console output that starts with `##` is not a heading to link to."""
    doc = tmp_path / "doc.md"
    doc.write_text(
        "# Real\n\n[phantom](#phantom-section)\n\n```console\n## Phantom Section\n```\n"
    )
    anchors = [c for c in claims.audit_document(doc, tmp_path) if "anchor" in c.claim]
    assert [c.verdict for c in anchors] == ["fail"]
