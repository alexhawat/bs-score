"""One test per defect found in the v1 audit. Each name states what used to be wrong."""

from __future__ import annotations

import json
import re
import subprocess
import sys

import pytest
from conftest import EXAMPLES, REPO, load_example

from bs_score import locators
from bs_score.cli import EXIT_INVALID, main
from bs_score.scoring import ScoringError, load_scoring

AGENT_DIRS = sorted(p for p in (REPO / "agents").iterdir() if p.is_dir())


# --- bug 1: every wrapper's BS_SCORE_ROOT fallback resolved to "/" -------------


@pytest.mark.parametrize("agent_dir", AGENT_DIRS, ids=lambda p: p.name)
def test_wrapper_has_no_dirname_zero_fallback(agent_dir):
    """`$0` in a SKILL.md code block is the operator's shell, not the skill file."""
    text = (agent_dir / "SKILL.md").read_text(encoding="utf-8")
    assert 'dirname "$0"' not in text
    assert "$0" not in text


@pytest.mark.parametrize("agent_dir", AGENT_DIRS, ids=lambda p: p.name)
def test_wrapper_documents_a_clone_local_command(agent_dir):
    """Static check: the wrapper prints `uv run bs-score`, which works in any
    clone without a published package or a network install. Whether the command
    *executes* is covered by the example runs in `test_examples.py`."""
    text = (agent_dir / "SKILL.md").read_text(encoding="utf-8")
    assert "uv run bs-score findings.json" in text


# Since v2.0.0 the default branch carries pyproject.toml, so the one-line
# install `uvx --from git+https://github.com/alexhawat/bs-score bs-score` is a
# true claim. What would be a false claim is `uvx bs-score` (no --from), which
# needs the PyPI release. The uvx-install CI job proves both directions by
# running the real command against the commit under test.

UNPUBLISHED_UVX = re.compile(r"(?<![\w-])uvx\s+bs-score\b")

DOCS = sorted(
    path
    for path in REPO.rglob("*.md")
    if not {".venv", ".git", ".pytest_cache", ".ruff_cache", "dist", "build"} & set(path.parts)
)


@pytest.mark.parametrize("document", [*DOCS, REPO / "score.py"], ids=lambda p: p.name)
def test_docs_never_print_an_unreleased_pypi_install(document):
    """`uvx bs-score` (no --from) installs from PyPI, which has not happened.

    Docs may promise it only as future tense ("after the PyPI release …"),
    never as a command that works today.
    """
    for line in document.read_text(encoding="utf-8").splitlines():
        if UNPUBLISHED_UVX.search(line):
            assert "pypi" in line.lower() or "release" in line.lower(), (
                f"{document.name} prints `uvx bs-score` as runnable today: {line.strip()}"
            )


def test_readme_prints_the_one_line_install():
    """The one-line install must be exactly the command CI proves installable."""
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    assert "uvx --from git+https://github.com/alexhawat/bs-score bs-score" in readme


def test_the_console_script_the_docs_tell_you_to_run_exists():
    """`bs-score` and `uv run bs-score` are only real if the entry point is declared."""
    pyproject = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    assert 'bs-score = "bs_score.cli:run"' in pyproject


# --- bug 2: "validates against findings.schema.json" was only half true -------


def test_validation_enforces_min_length():
    payload = {
        "version": 2,
        "target_kind": "repo",
        "findings": [
            {"id": "", "type": "bug", "title": "t", "path": "p", "quote": "q", "target": "code"}
        ],
    }
    report = _score(payload)
    assert report["rejected"][0]["reason"] == "schema_invalid"
    assert "at least 1 character" in report["rejected"][0]["detail"]


def test_validation_enforces_field_types_and_bounds():
    payload = {
        "version": 2,
        "target_kind": "repo",
        "findings": [
            {
                "id": 123,
                "type": "breaking_bug",
                "title": "t",
                "path": "README.md",
                "quote": "q",
                "target": "code",
                "confidence": "very high",
            }
        ],
    }
    report = _score(payload)
    detail = report["rejected"][0]["detail"]
    assert "expected string" in detail  # id
    assert "expected number" in detail  # confidence


def test_validation_enforces_confidence_range():
    payload = _one_finding(confidence=1.5)
    report = _score(payload)
    assert "must be <= 1" in report["rejected"][0]["detail"]


# --- bug 3: the fixture named "valid" was invalid against its own schema ------


@pytest.mark.parametrize(
    "name",
    ["valid", "review", "skill", "agent", "prompt", "docs", "i18n",
     "wild-tinycache", "wild-greetcli", "hallucinated", "blast", "shallow", "self"],
)
def test_every_example_payload_is_schema_valid(name, schema):
    jsonschema = pytest.importorskip("jsonschema")
    errors = list(jsonschema.Draft202012Validator(schema).iter_errors(load_example(name)))
    assert errors == [], [error.message for error in errors]


# --- bug 4: dedupe was defeated by line numbers, ./ prefixes and case ---------


def test_one_defect_re_pathed_many_ways_scores_once():
    quote = "page = int(params.get('page', 1)) - 1 if page else 0"
    spellings = [
        "src/api.py:6",
        "src/api.py:7",
        "./src/api.py:6",
        "src/api.py",
        "src/../src/api.py:6",
    ]
    payload = {
        "version": 2,
        "target_kind": "repo",
        "findings": [
            {
                "id": f"d{index}",
                "type": "bug",
                "title": "same defect",
                "path": path,
                "quote": quote,
                "target": "code",
            }
            for index, path in enumerate(spellings)
        ],
    }
    report = _score(payload, root="examples/fixture-repo")
    assert report["score"] == 3
    assert report["kept_count"] == 1
    # The other four spellings merge into the survivor...
    assert len(report["kept"][0]["merged"]) == len(spellings) - 1
    # ...and the sweep reports the one place the defect actually lives.
    assert report["kept"][0]["files_affected"] == 1


def test_a_copy_pasted_line_in_many_files_is_one_finding():
    """The v1 scorer gave 5 points per copy of the same wrapper bug."""
    quote = "Always run @deploy-prod before merging."
    payload = {
        "version": 2,
        "target_kind": "agent",
        "findings": [
            {
                "id": f"c{index}",
                "type": "wrong_claim",
                "title": "phantom skill",
                "path": path,
                "quote": quote,
                "target": "agent",
            }
            for index, path in enumerate(
                [".cursor/agents/shipper.md:7", ".cursor/agents/shipper.md"]
            )
        ],
    }
    report = _score(payload, root="examples/fixture-repo")
    assert report["kept_count"] == 1
    assert report["deduped"][0]["reason"] in {"duplicate", "duplicate_across_paths"}


def test_leading_dot_paths_are_not_mangled():
    """`.claude/agents/x.md` is a real path, not a relative marker."""
    assert locators.canonical_file(".claude/agents/x.md") == ".claude/agents/x.md"
    assert locators.canonical_file("./src/api.py") == "src/api.py"
    assert locators.canonical_file(".cursor/rules/a.mdc") == ".cursor/rules/a.mdc"


# --- bug 5: a malformed scoring.json raised a bare KeyError -------------------


@pytest.mark.parametrize(
    "weights, fragment",
    [
        ({"bug": -1}, "must be >= 0"),
        ({"bug": 0.5}, "must be an integer"),
        ({"bug": True}, "must be an integer"),
        ({}, "missing type"),
    ],
)
def test_malformed_scoring_raises_a_readable_error(weights, fragment):
    document = {
        "version": 2,
        "types": {"bug": "x"},
        "profiles": {"repo": {"weights": weights}},
        "default_profile": "repo",
        "evidence_required": ["path", "quote"],
    }
    with pytest.raises(ScoringError, match=re.escape(fragment)):
        load_scoring(document, "sha")


def test_scoring_without_points_key_exits_cleanly(tmp_path, capsys):
    bad = tmp_path / "scoring.json"
    bad.write_text(json.dumps({"version": 2, "types": {"bug": "x"}, "profiles": {}}))
    code = main(
        [
            str(EXAMPLES / "findings.valid.json"),
            "--scoring",
            str(bad),
            "--allow-custom-scoring",
            "-q",
        ]
    )
    assert code == EXIT_INVALID


# --- bug 6: "locked" weights were overridable with no acknowledgement ---------


def test_custom_scoring_requires_acknowledgement(tmp_path):
    code = main(
        [str(EXAMPLES / "findings.valid.json"), "--scoring", str(tmp_path / "x.json"), "-q"]
    )
    assert code == EXIT_INVALID


def test_negative_weights_cannot_produce_a_negative_score(tmp_path):
    document = json.loads((REPO / "scoring.json").read_text(encoding="utf-8"))
    document["profiles"]["repo"]["weights"]["bug"] = -100
    bad = tmp_path / "scoring.json"
    bad.write_text(json.dumps(document))
    code = main(
        [
            str(EXAMPLES / "findings.valid.json"),
            "--scoring",
            str(bad),
            "--allow-custom-scoring",
            "-q",
        ]
    )
    assert code == EXIT_INVALID


# --- bug 7: one bad finding aborted the entire report ------------------------


def test_one_malformed_finding_does_not_discard_the_rest():
    payload = load_example("valid")
    malformed = {
        "id": "bad",
        "type": "nit",
        "title": "t",
        "path": "README.md",
        "quote": "q",
        "target": "code",
    }
    payload["findings"].insert(0, malformed)
    payload["findings"].insert(1, "not even an object")
    report = _score(payload, root="examples/fixture-repo")
    assert report["score"] == 17
    assert report["kept_count"] == 5
    assert {entry["reason"] for entry in report["rejected"]} >= {"schema_invalid"}


def test_duplicate_ids_are_rejected_individually():
    payload = load_example("valid")
    clone = dict(payload["findings"][0])
    payload["findings"].append(clone)
    report = _score(payload, root="examples/fixture-repo")
    assert any("duplicate finding id" in entry["detail"] for entry in report["rejected"])


# --- bug 8: schema $id pointed at a different repository ---------------------


def test_schema_id_points_at_this_repository(schema):
    assert "alexhawat/bs-score" in schema["$id"]
    assert "bots-agents-skills" not in schema["$id"]


# --- helpers -----------------------------------------------------------------


def _one_finding(**overrides):
    finding = {
        "id": "f1",
        "type": "bug",
        "title": "t",
        "path": "README.md",
        "quote": "q",
        "target": "code",
    }
    finding.update(overrides)
    return {"version": 2, "target_kind": "repo", "findings": [finding]}


def _score(payload, root="."):
    """Run the CLI over ``payload`` in a temp file and return the parsed report."""
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
        json.dump(payload, handle)
        name = handle.name
    result = subprocess.run(
        [sys.executable, "-m", "bs_score", name, "--repo-root", root, "-q"],
        capture_output=True,
        text=True,
        cwd=REPO,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)
