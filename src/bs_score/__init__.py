"""Bullshit Score: verify the evidence, then score it deterministically."""

from __future__ import annotations

from loguru import logger

__all__ = ["__version__"]

__version__ = "2.2.0"

# Library convention: stay silent until a front-end (bs_score.cli) opts in.
logger.disable("bs_score")
