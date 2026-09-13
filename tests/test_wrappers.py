"""The seven runtime wrappers are generated, so they cannot drift apart again."""

from __future__ import annotations

import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1] / "scripts"))

import gen_agent_wrappers  # noqa: E402
from conftest import REPO  # noqa: E402


def test_wrappers_are_up_to_date():
    assert gen_agent_wrappers.main(["--check"]) == 0


def test_every_runtime_has_both_files():
    for runtime in gen_agent_wrappers.RUNTIMES:
        directory = REPO / "agents" / runtime
        assert (directory / "SKILL.md").is_file()
        assert (directory / "README.md").is_file()


def test_wrapper_frontmatter_declares_its_tools():
    for runtime in gen_agent_wrappers.RUNTIMES:
        text = (REPO / "agents" / runtime / "SKILL.md").read_text(encoding="utf-8")
        assert "allowed-tools:" in text
        assert "license: MIT" in text
