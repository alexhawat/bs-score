"""Experimental MCP server: expose ``audit`` and ``score`` as MCP tools.

Thin wrapper over the same code the CLI runs — no logic lives here. Install
the optional extra and run over stdio:

    uv pip install 'bs-score[mcp]'
    bs-score-mcp            # or: python -m bs_score.mcp_server

The tools mirror the CLI:
    audit(document, repo_root)          -> the ``bs-score claims`` checks
    score(findings, repo_root, sources) -> the verified report (full JSON)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .claims import audit_document
from .evidence import Verifier
from .report import Options, build_report, sha256_of_document
from .resources import SCHEMA_FILENAME, SCORING_FILENAME, load_json_file, locate
from .scoring import load_scoring
from .sources import load_sources
from .sweep import TreeIndex


def audit_tool(document: str, repo_root: str = ".") -> list[dict[str, Any]]:
    """Mechanically check a document's claims (paths, commands, flags,
    versions, links, code blocks) and return one dict per check."""
    return [
        claim.as_dict()
        for claim in audit_document(Path(document), Path(repo_root))
    ]


def score_tool(
    findings: str, repo_root: str = ".", sources: list[str] | None = None
) -> dict[str, Any]:
    """Verify and score a findings payload; returns the full report."""
    scoring_document, scoring_sha = load_json_file(locate(SCORING_FILENAME))
    schema, schema_sha = load_json_file(locate(SCHEMA_FILENAME))
    payload, _ = load_json_file(Path(findings))
    scoring = load_scoring(scoring_document, scoring_sha)
    registry = load_sources([Path(s) for s in sources or []])
    verifier = Verifier(Path(repo_root), registry)
    # Same tree the CLI sweeps, or this tool returns a report missing a section
    # the CLI produces.
    tree = TreeIndex(Path(repo_root))
    return build_report(
        payload,
        scoring,
        schema,
        schema_sha,
        verifier,
        Options(),
        findings_sha256=sha256_of_document(payload),
        tree=tree,
    )


def create_server():
    """Build the FastMCP server. Imports ``mcp`` lazily — it is an extra."""
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise SystemExit(
            "the MCP server needs the optional extra: uv pip install 'bs-score[mcp]'"
        ) from exc

    server = FastMCP("bs-score")
    server.tool()(audit_tool)
    server.tool()(score_tool)
    return server


def run() -> None:  # pragma: no cover - stdio loop
    """Console-script entry point (stdio transport)."""
    create_server().run()


def main() -> None:  # pragma: no cover - stdio loop
    run()


if __name__ == "__main__":  # pragma: no cover
    main()


__all__ = ["audit_tool", "create_server", "main", "run", "score_tool"]
