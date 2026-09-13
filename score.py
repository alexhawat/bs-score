#!/usr/bin/env python3
"""Compatibility shim: ``python3 score.py findings.json`` runs the bs-score CLI.

The packaged entry point is ``bs-score`` (``uv run bs-score`` from a clone, or the
installed console script). This file stays so the command printed in older SKILL.md
copies keeps working from a checkout.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

try:
    from bs_score.cli import main
except ModuleNotFoundError as exc:  # pragma: no cover - dependency guidance path
    missing = getattr(exc, "name", "a dependency")
    sys.stderr.write(
        f"bs_score needs {missing}. Install it with one of:\n"
        f"  uv run score.py findings.json     # from this clone\n"
        f"  uv sync --extra dev                # then: uv run bs-score ...\n"
        f"  pip install -e .                   # then: bs-score ...\n"
    )
    raise SystemExit(2) from exc

if __name__ == "__main__":
    raise SystemExit(main())
