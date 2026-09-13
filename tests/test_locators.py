"""Path canonicalisation and quote fingerprints."""

from __future__ import annotations

import pytest

from bs_score import locators


@pytest.mark.parametrize(
    "raw, kind, ref, line",
    [
        ("src/api.py", locators.FILE, "src/api.py", None),
        ("src/api.py:88", locators.FILE, "src/api.py", 88),
        ("src/api.py:88-95", locators.FILE, "src/api.py", 88),
        ("./src/api.py:88", locators.FILE, "src/api.py", 88),
        ("a/b/../c.py:4", locators.FILE, "a/c.py", 4),
        (".claude/agents/x.md", locators.FILE, ".claude/agents/x.md", None),
        ("prompt:system", locators.PROMPT, "system", None),
        ("prompt:agents/system.md:12", locators.PROMPT, "agents/system.md", 12),
        ("review:body", locators.REVIEW, "review:body", None),
        ("pull/12/reviews/34#scope", locators.REVIEW, "pull/12/reviews/34", None),
    ],
)
def test_parse(raw, kind, ref, line):
    locator = locators.parse(raw)
    assert (locator.kind, locator.ref, locator.line_start) == (kind, ref, line)


def test_absolute_paths_are_flagged():
    assert locators.parse("/etc/passwd").is_absolute
    assert not locators.parse("src/api.py").is_absolute


@pytest.mark.parametrize(
    "left, right",
    [
        ("foo   bar\nbaz", "foo bar baz"),
        ("the “thing”", 'the "thing"'),
        ("a — b", "a - b"),
        ("  padded  ", "padded"),
    ],
)
def test_fingerprint_ignores_reflow_and_typography(left, right):
    assert locators.quote_fingerprint(left) == locators.quote_fingerprint(right)


def test_fingerprint_distinguishes_different_text():
    assert locators.quote_fingerprint("alpha") != locators.quote_fingerprint("beta")
