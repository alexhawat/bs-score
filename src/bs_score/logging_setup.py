"""Loguru configuration for bs_score.

All diagnostics go to stderr so stdout stays a clean JSON (or Markdown) report
that a calling agent can pipe. `configure(verbosity)` is idempotent.
"""

from __future__ import annotations

import os
import sys

from loguru import logger

_LEVELS = ("WARNING", "INFO", "DEBUG", "TRACE")


def configure(verbosity: int = 0, *, quiet: bool = False) -> None:
    """Route loguru to stderr at a level derived from -v repetition.

    Args:
        verbosity: 0 = warnings only, 1 = info, 2 = debug, 3+ = trace.
        quiet: Silence logging entirely (errors are still surfaced by exit codes).

    Environment:
        BS_SCORE_LOG_LEVEL overrides the computed level when set.
    """
    logger.remove()
    if quiet:
        return
    level = os.environ.get("BS_SCORE_LOG_LEVEL") or _LEVELS[min(verbosity, len(_LEVELS) - 1)]
    logger.add(
        sys.stderr,
        level=level.upper(),
        format="<level>{level: <8}</level> | <cyan>{name}</cyan> - <level>{message}</level>",
        backtrace=False,
        diagnose=False,
    )


__all__ = ["configure", "logger"]
