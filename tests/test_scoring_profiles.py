"""One score, weights that depend on the review type."""

from __future__ import annotations

import re

import pytest
from conftest import REPO

from bs_score.resources import load_json_file
from bs_score.scoring import load_scoring


@pytest.fixture(scope="module")
def scoring():
    document, sha = load_json_file(REPO / "scoring.json")
    return load_scoring(document, sha)


def test_every_review_type_in_the_schema_has_a_profile(scoring, schema):
    kinds = set(schema["properties"]["target_kind"]["enum"])
    assert kinds <= set(scoring.profiles), sorted(kinds - set(scoring.profiles))


def test_every_profile_covers_every_finding_type(scoring, schema):
    types = set(schema["properties"]["findings"]["items"]["properties"]["type"]["enum"])
    assert types == set(scoring.types)
    for profile in scoring.profiles.values():
        assert set(profile.weights) == types, profile.name


def test_weights_differ_between_review_types(scoring):
    """A per-type table that is identical everywhere would be pointless."""
    tables = {name: tuple(sorted(p.weights.items())) for name, p in scoring.profiles.items()}
    assert len(set(tables.values())) > 1
    assert tables["review"] != tables["repo"]
    assert tables["prompt"] != tables["repo"]


def test_agent_and_prompt_profiles_weight_unsafe_instructions_highest(scoring):
    for name in ("agent", "prompt"):
        weights = scoring.profiles[name].weights
        assert weights["security_issue"] == max(weights.values()), name


def test_unknown_review_type_falls_back_to_the_default(scoring):
    assert scoring.profile_for("nonsense").name == scoring.default_profile


def test_confidence_never_affects_the_score(scoring):
    assert scoring.confidence_affects_score is False


PROFILE_COLUMNS = ["repo", "pr", "review", "skill", "agent", "prompt"]


def _weight_table_from_markdown(text: str) -> dict[str, list[int]]:
    """Parse the `| type | … | 5 | 6 | … |` rows out of a docs table."""
    rows: dict[str, list[int]] = {}
    for line in text.splitlines():
        match = re.match(r"^\|\s*`(\w+)`\s*\|(.+)\|\s*$", line)
        if not match:
            continue
        cells = re.findall(r"\|\s*(\d+)\s*(?=\|)", "|" + match.group(2) + "|")
        numbers = [int(cell) for cell in cells]
        if len(numbers) == len(PROFILE_COLUMNS):
            rows[match.group(1)] = numbers
    return rows


@pytest.mark.parametrize("document_name", ["README.md", "SKILL.md"])
def test_docs_and_scoring_agree_on_every_weight(document_name, scoring):
    """A weight table in the docs that drifts from scoring.json is exactly the
    kind of thing this project exists to catch."""
    text = (REPO / document_name).read_text(encoding="utf-8")
    table = _weight_table_from_markdown(text)
    assert set(table) == set(scoring.types), f"{document_name} weight table is incomplete"
    for finding_type, cells in table.items():
        # `pr` and `branch` share one column in the docs.
        documented = dict(zip(PROFILE_COLUMNS, cells, strict=True))
        for profile_name, points in documented.items():
            assert scoring.profiles[profile_name].weights[finding_type] == points, (
                f"{document_name}: {finding_type} under {profile_name} says {points}, "
                f"scoring.json says {scoring.profiles[profile_name].weights[finding_type]}"
            )
        assert scoring.profiles["branch"].weights[finding_type] == documented["pr"]
