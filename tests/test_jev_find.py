"""bs-score find --jev: Jev-based finding discovery (mocked, no live API)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from types import SimpleNamespace

import pytest
from conftest import EXAMPLES

from bs_score.cli import EXIT_INVALID, EXIT_OK, main
from bs_score.jev_find import (
    JevConfigError,
    JevDependencyError,
    collect_units,
    discover_findings,
    extract_units_from_markdown,
    judge_unit,
    require_api_key,
)

FIXTURE_DOCS = EXAMPLES / "fixture-docs"
GUIDE = FIXTURE_DOCS / "guide.md"


@dataclass
class FakeNoulAnswer:
    noul: float


@dataclass
class FakeChoiceAnswer:
    choice: str


@dataclass
class FakeScoreAnswer:
    score: int
    confidence: float | None = None


class FakeJevClient:
    """Minimal stand-in for TypeSafeClient.system_one."""

    def __init__(self, *, keep: float = 0.9, finding_type: str = "wrong_claim") -> None:
        self.keep = keep
        self.finding_type = finding_type
        self.calls: list[tuple[dict, dict]] = []

    def system_one(self, state, questions):  # noqa: ANN001
        self.calls.append((state, questions))
        return SimpleNamespace(
            answers={
                "keep": FakeNoulAnswer(self.keep),
                "finding_type": FakeChoiceAnswer(self.finding_type),
                "confidence": FakeScoreAnswer(2, confidence=0.85),
            }
        )

    def close(self) -> None:
        return None


def test_extract_units_from_fixture_guide():
    units = extract_units_from_markdown(GUIDE, FIXTURE_DOCS)
    quotes = {unit.quote for unit in units}
    assert "Requires Python 3.9 or newer." in quotes
    assert any("config/poller.yaml" in quote for quote in quotes)


def test_collect_units_docs_target():
    units = collect_units(
        FIXTURE_DOCS,
        target_kind="docs",
        paths=(GUIDE,),
    )
    assert units
    assert all(unit.path == "guide.md" for unit in units)


def test_collect_units_rejects_unsupported_kind():
    with pytest.raises(JevConfigError, match="not supported"):
        collect_units(FIXTURE_DOCS, target_kind="prompt")


def test_judge_unit_rejects_below_threshold():
    unit = extract_units_from_markdown(GUIDE, FIXTURE_DOCS)[0]
    client = FakeJevClient(keep=0.1)
    finding = judge_unit(
        client,
        unit,
        repo_root=FIXTURE_DOCS,
        target_kind="docs",
        questions={"keep": object(), "finding_type": object(), "confidence": object()},
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
        questions={"keep": object(), "finding_type": object(), "confidence": object()},
    )
    assert finding is not None
    assert finding["type"] == "wrong_claim"
    assert finding["quote"] == unit.quote
    assert finding["path"] == f"{unit.path}:{unit.line}"
    assert finding["title"]
    assert finding["confidence"] == 0.85


def test_discover_findings_payload(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    payload = discover_findings(
        FIXTURE_DOCS,
        target_kind="docs",
        paths=(GUIDE,),
        client_factory=lambda: FakeJevClient(keep=0.95),
    )
    assert payload["version"] == 2
    assert payload["target_kind"] == "docs"
    assert payload["audit"]["files_read"] == ["guide.md"]
    assert payload["findings"]
    for finding in payload["findings"]:
        assert set(finding) >= {"id", "type", "title", "path", "quote", "target", "confidence"}


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
    monkeypatch.setitem(__import__("sys").modules, "typesafe_sdk", None)

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
