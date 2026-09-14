"""Baseline files: accept known findings once, gate only on new ones.

A baseline is the set of dedupe keys — ``(type, canonical file, quote
fingerprint)`` — for findings a project has seen and chosen to live with.
``--baseline`` removes matching findings from the score (they are listed under
``baselined`` in the report, not ``kept``); ``--write-baseline`` captures
everything the run accepted — ``kept`` *and* ``baselined`` — so tomorrow's run
only scores what changed, and refreshing a baseline in place keeps it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from loguru import logger

BASELINE_VERSION = 1


class BaselineError(ValueError):
    """A --baseline file is unreadable or malformed."""


def key_of(finding: dict[str, Any]) -> tuple[str, str, str]:
    """The baseline match key: type, canonical file, quote fingerprint."""
    return (
        str(finding["type"]),
        str(finding["canonical_file"]),
        str(finding["quote_fingerprint"]),
    )


def load_baseline(path: Path) -> frozenset[tuple[str, str, str]]:
    """Load a baseline file into a set of match keys.

    Raises:
        BaselineError: the file is missing, not JSON, or the wrong shape.
    """
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BaselineError(f"cannot read baseline {path}: {exc}") from exc
    if not isinstance(document, dict) or not isinstance(document.get("findings"), list):
        raise BaselineError(f"{path}: expected {{'version': 1, 'findings': [...]}}")
    keys: set[tuple[str, str, str]] = set()
    for index, entry in enumerate(document["findings"]):
        if not isinstance(entry, dict) or not all(
            isinstance(entry.get(field), str) for field in ("type", "file", "quote_fingerprint")
        ):
            raise BaselineError(
                f"{path}: findings[{index}] needs string type, file, and quote_fingerprint"
            )
        keys.add((entry["type"], entry["file"], entry["quote_fingerprint"]))
    logger.info("loaded {} baselined finding(s) from {}", len(keys), path)
    return frozenset(keys)


def render_baseline(findings: list[dict[str, Any]]) -> dict[str, Any]:
    """Build the baseline document for a report's accepted findings.

    Entries are deduped by match key: findings already covered by a baseline skip
    the dedupe pass (they are never registered as a merge target), so the same
    defect can arrive here more than once.
    """
    entries: dict[tuple[str, str, str], dict[str, Any]] = {}
    for finding in findings:
        entry = {
            "type": finding["type"],
            "file": finding["canonical_file"],
            "quote_fingerprint": finding["quote_fingerprint"],
            "title": finding["title"],
        }
        entries.setdefault(key_of(finding), entry)
    return {"version": BASELINE_VERSION, "findings": list(entries.values())}


def write_baseline(path: Path, report: dict[str, Any]) -> None:
    """Write a baseline covering everything ``report`` accepted.

    Both ``kept`` and ``baselined`` go in. Writing only ``kept`` loses every
    finding the run's own ``--baseline`` suppressed, so the obvious
    ``--baseline b.json --write-baseline b.json`` refresh emptied the file and
    the next run scored the lot again.
    """
    findings = [*report["kept"], *report["baselined"]]
    path.parent.mkdir(parents=True, exist_ok=True)
    document = render_baseline(findings)
    path.write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    logger.info("wrote baseline with {} finding(s) to {}", len(document["findings"]), path)


__all__ = [
    "BASELINE_VERSION",
    "BaselineError",
    "key_of",
    "load_baseline",
    "render_baseline",
    "write_baseline",
]
