"""bs-score find --jev: Jev-based finding discovery (mocked, no live API)."""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from types import SimpleNamespace

import pytest
from conftest import EXAMPLES

from bs_score.cli import EXIT_INVALID, EXIT_OK, main
from bs_score.jev_find import (
    JevConfigError,
    JevDependencyError,
    build_jev_state,
    collect_paths,
    collect_units,
    discover_findings,
    extract_units_from_markdown,
    judge_file_units,
    judge_unit,
    require_api_key,
)
from bs_score.jev_questions import (
    JEV_MODEL,
    KEEP_NOUL_MIN,
    SCORE_CONFIDENCE_MIN,
    RoutingThresholds,
    UnitJudgment,
    build_questions_for_units,
    parse_unit_judgment,
    route_unit_judgment,
)

FIXTURE_DOCS = EXAMPLES / "fixture-docs"
GUIDE = FIXTURE_DOCS / "guide.md"


@dataclass
class FakeNoulAnswer:
    noul: float


@dataclass
class FakeChoiceAnswer:
    choice: str
    confidence: float = 0.9


@dataclass
class FakeScoreAnswer:
    score: int
    confidence: float = 0.85


class FakeQuestion:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class FakeJevClient:
    """Minimal stand-in for TypeSafeClient.system_one."""

    def __init__(
        self,
        *,
        keep: float = 0.9,
        finding_type: str = "wrong_claim",
        choice_confidence: float = 0.9,
        score_confidence: float = 0.85,
    ) -> None:
        self.keep = keep
        self.finding_type = finding_type
        self.choice_confidence = choice_confidence
        self.score_confidence = score_confidence
        self.calls: list[tuple[dict, dict, dict]] = []

    def system_one(self, state, questions, *, model=None):  # noqa: ANN001
        self.calls.append((state, questions, {"model": model}))
        answers = {}
        for name in questions:
            if name.endswith("_keep"):
                answers[name] = FakeNoulAnswer(self.keep)
            elif name.endswith("_finding_type"):
                answers[name] = FakeChoiceAnswer(self.finding_type, self.choice_confidence)
            elif name.endswith("_confidence"):
                answers[name] = FakeScoreAnswer(2, confidence=self.score_confidence)
        return SimpleNamespace(
            model=model or JEV_MODEL,
            usage=SimpleNamespace(input_tokens=100, output_tokens=0),
            answers=answers,
        )

    def close(self) -> None:
        return None


@pytest.fixture(autouse=True)
def mock_optional_sdk(monkeypatch):
    """The standard test suite must not need the optional Jev extra."""
    monkeypatch.setattr(
        "bs_score.jev_find.require_jev_dependencies",
        lambda: (FakeJevClient, FakeQuestion, FakeQuestion, FakeQuestion),
    )


def test_extract_units_from_fixture_guide():
    units = extract_units_from_markdown(GUIDE, FIXTURE_DOCS)
    quotes = {unit.quote for unit in units}
    assert "Requires Python 3.9 or newer." in quotes
    assert any("config/poller.yaml" in quote for quote in quotes)


def test_extract_units_keeps_line_numbers_after_fenced_block(tmp_path):
    document = tmp_path / "guide.md"
    document.write_text(
        "```python\n" + "print('example')\n" * 12 + "```\n\n"
        "Requires Python 3.9 or newer.\n",
        encoding="utf-8",
    )
    units = extract_units_from_markdown(document, tmp_path)
    assert len(units) == 1
    assert units[0].line == 16
    assert units[0].quote == "Requires Python 3.9 or newer."


def test_multiline_sentence_quote_is_verbatim(tmp_path):
    """A sentence spanning source lines used to be space-joined into a quote
    that does not occur in the file — the verifier then rejects the finding
    find --jev itself produced."""
    document = tmp_path / "guide.md"
    document.write_text(
        "Intro paragraph here.\n\n"
        "The tool always verifies quotes against\n"
        "the artifacts they name before scoring.\n",
        encoding="utf-8",
    )
    text = document.read_text(encoding="utf-8")
    units = extract_units_from_markdown(document, tmp_path)
    multi = [u for u in units if "verifies quotes" in u.quote]
    assert len(multi) == 1
    assert multi[0].quote in text  # verbatim slice, not a space-joined rebuild
    assert multi[0].line == 3  # the line the quote starts on


def test_indented_and_repeated_sentences_get_their_own_lines(tmp_path):
    document = tmp_path / "guide.md"
    document.write_text(
        "  Python 3.11 is required by this project.\n"
        "Filler sentence with nothing to check here at all.\n"
        "Python 3.11 is required by this project.\n",
        encoding="utf-8",
    )
    units = extract_units_from_markdown(document, tmp_path)
    assert [u.line for u in units] == [1, 3]
    assert all(u.quote == "Python 3.11 is required by this project." for u in units)


def test_paragraph_before_a_heading_without_a_blank_line_is_extracted(tmp_path):
    """A heading flushed the pending paragraph without extracting it."""
    document = tmp_path / "guide.md"
    document.write_text(
        "A claim sentence that is always checked.\n"
        "## Heading without a blank line above\n",
        encoding="utf-8",
    )
    units = extract_units_from_markdown(document, tmp_path)
    assert [u.line for u in units] == [1]
    assert units[0].quote == "A claim sentence that is always checked."


def test_collect_units_docs_target():
    units = collect_units(
        FIXTURE_DOCS,
        target_kind="docs",
        paths=(GUIDE,),
    )
    assert units
    assert all(unit.path == "guide.md" for unit in units)


def test_glob_results_resolving_outside_repo_root_are_skipped(tmp_path):
    repo = tmp_path / "repo"
    docs = repo / "docs"
    docs.mkdir(parents=True)
    real = docs / "real.md"
    real.write_text("A claim sentence.\n", encoding="utf-8")
    outside = tmp_path / "outside.md"
    outside.write_text("Secret content outside the repo.\n", encoding="utf-8")
    link = docs / "leak.md"
    try:
        link.symlink_to(outside)
    except OSError as exc:  # platform cannot create symlinks
        pytest.skip(f"symlinks unavailable: {exc}")

    paths = collect_paths(repo, ("docs/*.md",))

    assert real in paths
    assert link not in paths
    assert all(path.resolve().is_relative_to(repo.resolve()) for path in paths)


def test_literal_pattern_escaping_repo_root_is_skipped(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("Secret content outside the repo.\n", encoding="utf-8")

    assert collect_paths(repo, ("../outside.md",)) == []


def test_collect_units_rejects_unsupported_kind():
    with pytest.raises(JevConfigError, match="not supported"):
        collect_units(FIXTURE_DOCS, target_kind="prompt")


def test_build_jev_state_filters_to_claim_units():
    units = extract_units_from_markdown(GUIDE, FIXTURE_DOCS)[:2]
    state = build_jev_state(
        target_kind="docs",
        file_path="guide.md",
        units=units,
        repo_root=FIXTURE_DOCS,
    )
    assert state["file"] == "guide.md"
    assert len(state["units"]) == 2
    assert all("quote" in unit and "context" in unit for unit in state["units"])
    assert "notice" in state


def test_build_questions_batches_all_units():
    from bs_score.jev_find import require_jev_dependencies

    _, Choice, Noul, Score = require_jev_dependencies()
    questions = build_questions_for_units(3, Choice=Choice, Noul=Noul, Score=Score)
    assert set(questions) == {
        "u0_keep",
        "u0_finding_type",
        "u0_confidence",
        "u1_keep",
        "u1_finding_type",
        "u1_confidence",
        "u2_keep",
        "u2_finding_type",
        "u2_confidence",
    }


def test_route_unit_judgment_requires_keep_and_confidence():
    low_keep = UnitJudgment(0.1, "wrong_claim", 0.9, 0.9)
    low_score = UnitJudgment(0.9, "wrong_claim", 0.9, 0.1)
    low_choice = UnitJudgment(0.9, "wrong_claim", 0.1, 0.9)
    good = UnitJudgment(0.9, "wrong_claim", 0.9, 0.85)

    assert not route_unit_judgment(low_keep)
    assert not route_unit_judgment(low_score)
    assert not route_unit_judgment(low_choice)
    assert route_unit_judgment(good)


def test_route_thresholds_match_versioned_defaults():
    floors = RoutingThresholds()
    assert floors.keep_noul_min == KEEP_NOUL_MIN
    assert floors.score_confidence_min == SCORE_CONFIDENCE_MIN


def test_judge_unit_rejects_below_threshold():
    unit = extract_units_from_markdown(GUIDE, FIXTURE_DOCS)[0]
    client = FakeJevClient(keep=0.1)
    finding = judge_unit(
        client,
        unit,
        repo_root=FIXTURE_DOCS,
        target_kind="docs",
    )
    assert finding is None


def test_judge_unit_rejects_low_score_confidence():
    unit = extract_units_from_markdown(GUIDE, FIXTURE_DOCS)[0]
    client = FakeJevClient(keep=0.95, score_confidence=0.1)
    finding = judge_unit(
        client,
        unit,
        repo_root=FIXTURE_DOCS,
        target_kind="docs",
    )
    assert finding is None


def test_judge_unit_emits_schema_fields():
    unit = extract_units_from_markdown(GUIDE, FIXTURE_DOCS)[0]
    client = FakeJevClient(keep=0.95, finding_type="wrong_claim")
    finding = judge_unit(
        client,
        unit,
        repo_root=FIXTURE_DOCS,
        target_kind="docs",
    )
    assert finding is not None
    assert finding["type"] == "wrong_claim"
    assert finding["quote"] == unit.quote
    assert finding["path"] == f"{unit.path}:{unit.line}"
    assert finding["title"]
    assert finding["confidence"] == 0.85


def test_judge_file_units_one_call_per_file():
    units = extract_units_from_markdown(GUIDE, FIXTURE_DOCS)
    client = FakeJevClient(keep=0.95)
    findings = judge_file_units(
        client,
        target_kind="docs",
        file_path="guide.md",
        units=units,
        repo_root=FIXTURE_DOCS,
    )
    assert len(client.calls) == 1
    state, questions, kwargs = client.calls[0]
    assert kwargs["model"] == JEV_MODEL
    assert len(state["units"]) == len(units)
    assert len(questions) == len(units) * 3
    assert findings


def test_discover_findings_batches_by_file(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    client = FakeJevClient(keep=0.95)
    payload = discover_findings(
        FIXTURE_DOCS,
        target_kind="docs",
        paths=(GUIDE,),
        client_factory=lambda: client,
    )
    assert len(client.calls) == 1
    assert payload["version"] == 2
    assert payload["target_kind"] == "docs"
    assert payload["audit"]["files_read"] == ["guide.md"]
    assert payload["findings"]
    for finding in payload["findings"]:
        assert set(finding) >= {"id", "type", "title", "path", "quote", "target", "confidence"}


class FlakyJevClient(FakeJevClient):
    """FakeJevClient that raises on files whose path ends with fail_on."""

    def __init__(self, *, fail_on: str, **kwargs) -> None:  # noqa: ANN003
        super().__init__(**kwargs)
        self.fail_on = fail_on

    def system_one(self, state, questions, *, model=None):  # noqa: ANN001
        if state["file"].endswith(self.fail_on):
            raise RuntimeError("boom")
        return super().system_one(state, questions, model=model)


def test_a_failing_file_is_skipped_and_the_rest_of_the_run_survives(monkeypatch, tmp_path):
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    (tmp_path / "a.md").write_text("Requires Python 3.9 or newer.\n")
    (tmp_path / "b.md").write_text("Supports Linux, macOS, and Windows.\n")
    flaky = FlakyJevClient(fail_on="a.md", keep=0.95)
    payload = discover_findings(
        tmp_path,
        target_kind="docs",
        client_factory=lambda: flaky,
    )
    assert [finding["path"] for finding in payload["findings"]] == ["b.md:1"]
    assert payload["audit"]["files_read"] == ["a.md", "b.md"]


def test_all_files_failing_yields_an_empty_payload_not_a_traceback(monkeypatch, tmp_path):
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    (tmp_path / "a.md").write_text("Requires Python 3.9 or newer.\n")
    (tmp_path / "b.md").write_text("Supports Linux, macOS, and Windows.\n")
    flaky = FlakyJevClient(fail_on=".md", keep=0.95)
    payload = discover_findings(
        tmp_path,
        target_kind="docs",
        client_factory=lambda: flaky,
    )
    assert payload["findings"] == []
    assert payload["audit"]["files_read"] == ["a.md", "b.md"]


def test_parse_unit_judgment_from_batched_response():
    response = SimpleNamespace(
        answers={
            "u0_keep": FakeNoulAnswer(0.8),
            "u0_finding_type": FakeChoiceAnswer("bug", 0.7),
            "u0_confidence": FakeScoreAnswer(1, confidence=0.75),
        }
    )
    judgment = parse_unit_judgment(response, 0)
    assert judgment == UnitJudgment(0.8, "bug", 0.7, 0.75)


def test_cli_requires_jev_flag(capsys):
    code = main(["find", "--repo-root", str(FIXTURE_DOCS), "-q"])
    assert code == EXIT_INVALID
    captured = capsys.readouterr()
    combined = (captured.out + captured.err).lower()
    assert "requires --jev" in combined


def test_cli_missing_api_key(monkeypatch, capsys):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    code = main(
        [
            "find",
            "--jev",
            "--target-kind",
            "docs",
            "--document",
            str(GUIDE),
            "--repo-root",
            str(FIXTURE_DOCS),
            "-q",
        ]
    )
    assert code == EXIT_INVALID
    err = capsys.readouterr().err
    assert "TYPESAFE_API_KEY" in err


def test_cli_missing_sdk(monkeypatch, capsys):
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")

    def _boom():
        raise JevDependencyError("install me")

    monkeypatch.setattr("bs_score.jev_find.require_jev_dependencies", _boom)
    code = main(
        [
            "find",
            "--jev",
            "--target-kind",
            "docs",
            "--document",
            str(GUIDE),
            "--repo-root",
            str(FIXTURE_DOCS),
            "-q",
        ]
    )
    assert code == EXIT_INVALID
    assert "install" in capsys.readouterr().err.lower()


def test_cli_emits_findings_json(monkeypatch, capsys):
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    monkeypatch.setattr(
        "bs_score.cli.discover_findings",
        lambda *args, **kwargs: {
            "version": 2,
            "target_kind": "docs",
            "findings": [],
            "audit": {"files_read": ["guide.md"]},
        },
    )
    code = main(
        [
            "find",
            "--jev",
            "--target-kind",
            "docs",
            "--document",
            str(GUIDE),
            "--repo-root",
            str(FIXTURE_DOCS),
            "-q",
        ]
    )
    assert code == EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["target_kind"] == "docs"


def test_cli_unwritable_output_is_a_usage_error(monkeypatch, tmp_path, capsys):
    """A failed `find --jev -o` used to escape as a traceback and exit 1 — the
    same signal as 'over --fail-over', so a CI gate read a full disk as a bad
    score. Mirror the guarded write in main(): exit 2 with a logged error."""
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    monkeypatch.setattr(
        "bs_score.cli.discover_findings",
        lambda *args, **kwargs: {"version": 2, "target_kind": "docs", "findings": []},
    )
    blocked = tmp_path / "blocked"
    blocked.write_text("not a directory")  # a child path under it cannot be created
    code = main(
        [
            "find",
            "--jev",
            "--repo-root",
            str(FIXTURE_DOCS),
            "--document",
            str(GUIDE),
            "-o",
            str(blocked / "findings.json"),
            "-q",
        ]
    )
    captured = capsys.readouterr()
    assert code == EXIT_INVALID
    assert "cannot write" in captured.err
    assert "Traceback" not in captured.err


def test_cli_resolves_document_from_repo_root(monkeypatch, tmp_path, capsys):
    paths_seen = []

    def fake_discover(*args, **kwargs):
        paths_seen.extend(kwargs["paths"])
        return {"version": 2, "target_kind": "docs", "findings": []}

    monkeypatch.setattr("bs_score.cli.discover_findings", fake_discover)
    monkeypatch.chdir(tmp_path)
    code = main(
        ["find", "--jev", "--repo-root", str(FIXTURE_DOCS), "--document", "guide.md", "-q"]
    )
    assert code == EXIT_OK
    assert paths_seen == [GUIDE]
    capsys.readouterr()


def test_cli_score_forwards_flags_and_cleans_up(monkeypatch, tmp_path, capsys):
    payload = json.loads((EXAMPLES / "findings.valid.json").read_text(encoding="utf-8"))
    monkeypatch.setattr("bs_score.cli.discover_findings", lambda *args, **kwargs: payload)
    temporary_directory = tempfile.TemporaryDirectory
    monkeypatch.setattr(
        "bs_score.cli.tempfile.TemporaryDirectory",
        lambda: temporary_directory(dir=tmp_path),
    )

    code = main(
        [
            "find", "--jev", "--repo-root", str(EXAMPLES / "fixture-repo"),
            "--score", "--fail-over", "0", "--no-scan", "-q",
        ]
    )
    report = json.loads(capsys.readouterr().out)
    assert code == 1
    assert report["score"] == 17
    assert report["blast_radius"]["mode"] == "not_scanned"
    assert list(tmp_path.iterdir()) == []


def test_require_api_key_missing(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    with pytest.raises(JevConfigError, match="TYPESAFE_API_KEY"):
        require_api_key()


def test_default_scoring_path_unchanged(capsys):
    """Without --jev, the default scorer command is identical."""
    code = main(["examples/findings.valid.json", "--repo-root", "examples/fixture-repo", "-q"])
    assert code in {EXIT_OK, 1}
    report = json.loads(capsys.readouterr().out)
    assert "score" in report
