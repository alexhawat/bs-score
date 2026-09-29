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
        assert set(claim) == {"kind", "claim", "verdict", "evidence", "span", "line"}
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

#: What a changelog names that is not a claim about the tree as it stands: the
#: versions it exists to record, a field reference, and values a past release
#: got wrong. Passed as --ignore, so each is reported as a skip, not dropped.
CHANGELOG_IGNORES = ("v2.0.0", "depth.status", "src/a.py", "alexhawat/bots-*")


#: The README's install table names where the skill goes in *your* checkout,
#: which is not a path in this one. Same class as a runtime artifact.
DOC_IGNORES = {"README.md": ("*skills/bs-score",), "SKILL.md": ()}


@pytest.mark.parametrize("document", ["README.md", "SKILL.md"])
def test_this_repos_own_docs_have_no_failing_claims(document):
    """Dogfood: our own top-level docs must pass the mechanical checks."""
    report = claims.audit_document(REPO / document, REPO, ignore=DOC_IGNORES[document])
    failed = [c for c in report if c.verdict == "fail" and c.span not in ILLUSTRATIVE_SPANS]
    assert failed == [], [(c.claim, c.evidence) for c in failed]


def test_the_changelog_passes_once_its_historical_mentions_are_named():
    """A changelog names old versions and past mistakes; neither is a live claim.

    It could not be checked at all before: version mentions inside URLs counted,
    and there was no way to say "this one is history". Both are fixed, so the
    changelog is in scope now — and a *new* false claim in it still fails.
    """
    report = claims.audit_document(REPO / "CHANGELOG.md", REPO, ignore=CHANGELOG_IGNORES)
    failed = [c for c in report if c.verdict == "fail"]
    assert failed == [], [(c.claim, c.evidence) for c in failed]
    # Every ignore earns its place: an unused one means the doc changed.
    named = {c.evidence.removeprefix("ignored by --ignore ") for c in report
             if c.evidence.startswith("ignored by")}
    assert named == set(CHANGELOG_IGNORES), (
        f"unused --ignore pattern(s): {set(CHANGELOG_IGNORES) - named}"
    )


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


def test_a_version_inside_a_url_is_an_address_not_a_claim(tmp_path):
    """A link to semver.org/spec/v2.0.0.html does not assert this project is 2.0.0."""
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "demo"\nversion = "2.2.0"\n')
    doc = tmp_path / "doc.md"
    doc.write_text(
        "Follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).\n"
        "Bare https://example.com/v1.0.0/guide too.\n"
    )
    versions = [c for c in claims.audit_document(doc, tmp_path) if c.kind == "version"]
    assert [c for c in versions if c.verdict == "fail"] == []

    # A version claim in prose is still checked.
    doc.write_text("Install version 1.0.0 of demo.\n")
    failed = [c for c in claims.audit_document(doc, tmp_path) if c.verdict == "fail"]
    assert [c.claim for c in failed] == ["version 1.0.0 matches pyproject.toml"]


def test_a_github_slug_the_doc_links_to_is_not_a_repo_path(tmp_path):
    """`owner/repo` is a path shape, but the document says it is a GitHub repo."""
    doc = tmp_path / "doc.md"
    doc.write_text("See `octocat/hello-world` at https://github.com/octocat/hello-world.\n")
    paths = [c for c in claims.audit_document(doc, tmp_path) if c.kind == "path"]
    assert [(c.verdict, c.evidence) for c in paths] == [
        ("skip", "github.com/octocat/hello-world appears in this document: a repo, not a path")
    ]

    # Without the URL there is no evidence it is a repo, so it stays a path claim.
    doc.write_text("See `octocat/hello-world`.\n")
    paths = [c for c in claims.audit_document(doc, tmp_path) if c.kind == "path"]
    assert [c.verdict for c in paths] == ["fail"]


def test_ignore_marks_a_claim_skipped_and_names_the_pattern(tmp_path):
    """--ignore covers every kind, and never drops a check silently."""
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "demo"\nversion = "2.2.0"\n')
    doc = tmp_path / "doc.md"
    doc.write_text("It writes `report.md` and `report.sarif`. Since version 1.0.0.\n")

    assert len([c for c in claims.audit_document(doc, tmp_path) if c.verdict == "fail"]) == 3

    ignored = claims.audit_document(doc, tmp_path, ignore=("report.*", "1.0.0"))
    assert [c for c in ignored if c.verdict == "fail"] == []
    skipped = [c for c in ignored if "ignored by" in c.evidence]
    assert len(skipped) == 3, "an ignored check must still be reported, as a skip"
    assert all(c.verdict == "skip" for c in skipped)


def test_a_url_without_its_scheme_is_not_a_path(tmp_path):
    """`semver.org/spec/v2.0.0.html` in backticks is an address, not a directory."""
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "ci.yml").write_text("on: push\n")
    doc = tmp_path / "doc.md"
    doc.write_text("See `semver.org/spec/v2.0.0.html` and `github.com/owner/repo`.\n")
    assert [c for c in claims.audit_document(doc, tmp_path) if c.kind == "path"] == []

    # A leading dot marks a real path, and it is still checked.
    doc.write_text("Config in `.github/ci.yml`, missing one in `.github/nope.yml`.\n")
    paths = claims.audit_document(doc, tmp_path)
    assert sorted((c.verdict, c.span) for c in paths if c.kind == "path") == [
        ("fail", "`.github/nope.yml`"), ("pass", "`.github/ci.yml`"),
    ]


def _two_command_repo(root):
    """A script whose entry point dispatches to a subcommand parser."""
    (root / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "1.0.0"\n\n'
        '[project.scripts]\ndemo = "demo.cli:run"\n'
    )
    pkg = root / "demo"
    pkg.mkdir()
    (pkg / "cli.py").write_text(
        "import argparse\n"
        "import sys\n\n"
        "def build_parser():\n"
        "    parser = argparse.ArgumentParser(prog='demo')\n"
        "    parser.add_argument('--speed')\n"
        "    return parser\n\n"
        "def build_extra_parser():\n"
        "    parser = argparse.ArgumentParser(prog='demo extra')\n"
        "    parser.add_argument('--deep', action='store_true')\n"
        "    return parser\n\n"
        "def run():\n"
        "    argv = sys.argv[1:]\n"
        "    if argv and argv[0] == 'extra':\n"
        "        build_extra_parser().parse_args(argv[1:])\n"
        "    else:\n"
        "        build_parser().parse_args(argv)\n"
    )
    return root


def test_a_subcommand_flag_is_not_the_base_commands_flag(tmp_path):
    """Flags were unioned across every parser in the entry module, so a
    subcommand-only flag falsely passed against the base command."""
    root = _two_command_repo(tmp_path)
    facts = claims.load_project_facts(root)

    failed = [c for c in claims.check_flags("demo --deep", facts) if c.verdict == "fail"]
    assert [c.claim for c in failed] == ["`demo` accepts --deep"]

    passed = claims.check_flags("demo extra --deep", facts)
    assert [(c.claim, c.verdict) for c in passed] == [("`demo extra` accepts --deep", "pass")]

    # The base command's own flags are still checked, and still pass.
    assert [c.verdict for c in claims.check_flags("demo --speed fast", facts)] == ["pass"]


def test_flags_fall_back_to_the_module_union_without_named_builders(tmp_path):
    """A module whose parser is built inline (no build_*_parser functions)
    keeps the old whole-module behaviour."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "1.0.0"\n\n'
        '[project.scripts]\ndemo = "demo.cli:main"\n'
    )
    pkg = tmp_path / "demo"
    pkg.mkdir()
    (pkg / "cli.py").write_text(
        "import argparse\n\n"
        "def main():\n"
        "    parser = argparse.ArgumentParser(prog='demo')\n"
        "    parser.add_argument('--speed')\n"
        "    parser.parse_args()\n"
    )
    facts = claims.load_project_facts(tmp_path)
    assert "--speed" in facts.flags["demo"]


def test_this_repo_attributes_claims_flags_to_the_claims_parser():
    facts = claims.load_project_facts(REPO)
    assert "--check-links" in facts.flags["bs-score claims"]
    assert "--check-links" not in facts.flags["bs-score"]
    assert "--fail-over" in facts.flags["bs-score"]


def test_a_backticked_version_is_not_a_path_claim(tmp_path):
    """`9.9.9` matched the file-ish branch of PATH_LIKE and failed as a
    missing path. Versions are the version checker's business, not the path
    checker's — and a bare one is not a claim at all."""
    assert claims.check_paths("released `9.9.9` and `1.2` last week", tmp_path) == []
    # A real missing path right next to it is still caught.
    found = claims.check_paths("see `9.9.9` and `gone.txt`", tmp_path)
    assert [(c.claim, c.verdict) for c in found] == [("path `gone.txt` exists", "fail")]


def test_bare_name_claims_resolve_through_the_name_index(tmp_path):
    """Unique match passes, several matches are ambiguous, none is false."""
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "only.txt").write_text("x")
    for other in ("b", "c"):
        (tmp_path / other).mkdir()
        (tmp_path / other / "dup.txt").write_text("x")
    found = claims.check_paths("`only.txt` `dup.txt` `gone.txt`", tmp_path)
    assert [(c.claim, c.verdict) for c in found] == [
        ("path `only.txt` exists", "pass"),
        ("path `dup.txt` exists", "skip"),
        ("path `gone.txt` exists", "fail"),
    ]


def test_pruned_directories_never_enter_the_name_index(tmp_path):
    """node_modules used to be filtered out *after* the walk; now it is never
    walked, so a same-named vendored file cannot make a claim ambiguous."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.js").write_text("x")
    vendored = tmp_path / "node_modules" / "pkg"
    vendored.mkdir(parents=True)
    (vendored / "app.js").write_text("x")
    (vendored / "only-vendored.js").write_text("x")

    found = claims.check_paths("`app.js` and `only-vendored.js`", tmp_path)
    assert [(c.claim, c.verdict) for c in found] == [
        ("path `app.js` exists", "pass"),  # unique: the vendored copy is unseen
        ("path `only-vendored.js` exists", "fail"),
    ]
