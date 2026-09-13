"""Locate and fingerprint the two data files that define a score.

A bs_score report is only reproducible if you know which weights and which
contract produced it, so every load returns the file's sha256 alongside its
content. Canonical copies live at the repository root (the paths the docs
quote); an installed wheel carries the same bytes under ``bs_score/data/``.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from loguru import logger

_PACKAGE_DATA = Path(__file__).resolve().parent / "data"
_REPO_ROOT = Path(__file__).resolve().parents[2]

SCORING_FILENAME = "scoring.json"
SCHEMA_FILENAME = "findings.schema.json"


class DataFileError(RuntimeError):
    """Raised when a data file is missing or is not valid JSON."""


def _candidates(filename: str) -> list[Path]:
    return [_PACKAGE_DATA / filename, _REPO_ROOT / filename]


def locate(filename: str) -> Path:
    """Return the first existing copy of ``filename`` (package data, then repo root)."""
    for candidate in _candidates(filename):
        if candidate.is_file():
            logger.debug("resolved {} -> {}", filename, candidate)
            return candidate
    searched = ", ".join(str(candidate) for candidate in _candidates(filename))
    raise DataFileError(f"cannot find {filename}; looked in: {searched}")


def sha256_of(path: Path) -> str:
    """Return the sha256 of a file's bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json_file(path: Path) -> tuple[Any, str]:
    """Load JSON from ``path`` and return ``(document, sha256)``.

    Raises:
        DataFileError: the file is unreadable or not valid JSON.
    """
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise DataFileError(f"cannot read {path}: {exc}") from exc
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DataFileError(f"{path} is not valid JSON: {exc}") from exc
    return document, hashlib.sha256(raw).hexdigest()


__all__ = [
    "SCHEMA_FILENAME",
    "SCORING_FILENAME",
    "DataFileError",
    "load_json_file",
    "locate",
    "sha256_of",
]
