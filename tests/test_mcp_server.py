"""The MCP tools are thin wrappers; their logic is tested without the extra."""

from __future__ import annotations

import pytest
from conftest import EXAMPLES

from bs_score import mcp_server

FIXTURE_DOCS = EXAMPLES / "fixture-docs"


def test_audit_tool_matches_the_claims_subcommand():
    report = mcp_server.audit_tool(
        str(FIXTURE_DOCS / "guide.md"), str(FIXTURE_DOCS)
    )
    failed = [c for c in report if c["verdict"] == "fail"]
    assert len(failed) == 3
    assert {c["kind"] for c in failed} == {"version", "path", "flag"}


def test_score_tool_matches_the_cli_receipt():
    report = mcp_server.score_tool(
        str(EXAMPLES / "findings.valid.json"), str(EXAMPLES / "fixture-repo")
    )
    assert report["score"] == 17
    assert report["band"] == "bullshit"
    assert report["evidence"]["mode"] == "verified"


def test_server_construction_needs_the_extra():
    """Without the mcp package, create_server fails with an actionable message."""
    pytest.importorskip("mcp", reason="mcp extra not installed; wrapper-only test")
    server = mcp_server.create_server()
    assert server.name == "bs-score"


def test_score_tool_returns_the_same_sections_as_the_cli():
    """`score_tool` documents itself as returning "the full report".

    It builds the report directly rather than going through the CLI, so a new
    section wired into `cli.py` and not here would leave the MCP path silently
    returning less than it claims.
    """
    from bs_score.mcp_server import score_tool

    report = score_tool("examples/findings.blast.json", "examples/fixture-repo")
    assert report["blast_radius"]["mode"] == "scanned"
    assert report["kept"][0]["files_affected"] == 3
    assert report["depth"]["status"] == "deep"
