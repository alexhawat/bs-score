"""Verify that every quoted piece of evidence actually exists.

This is the pass that separates bs_score from a calculator attached to an
opinion. Without it a fabricated finding — a race condition in a file that has
no async code, a token in a module that does not exist — scores exactly like a
real one. With it, a quote that cannot be found in the artifact it names is
rejected before any points are assigned.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loguru import logger

from . import locators
from .locators import Locator
from .sources import SourceRegistry

VERIFIED = "verified"
WRONG_LINE = "verified_wrong_line"
QUOTE_NOT_FOUND = "quote_not_found"
PATH_NOT_FOUND = "path_not_found"
OUTSIDE_ROOT = "outside_root"
UNREADABLE = "unreadable"
NOT_VERIFIABLE = "not_verifiable"
SKIPPED = "skipped"

#: Statuses that prove the quote is real.
PASSING = frozenset({VERIFIED, WRONG_LINE})
#: Statuses that prove it is not.
FAILING = frozenset({QUOTE_NOT_FOUND, PATH_NOT_FOUND, OUTSIDE_ROOT, UNREADABLE})
#: Statuses where no artifact was available to check against.
INCONCLUSIVE = frozenset({NOT_VERIFIABLE, SKIPPED})

DEFAULT_LINE_WINDOW = 10
_MAX_BYTES = 8 * 1024 * 1024


@dataclass(frozen=True)
class Verdict:
    """The outcome of checking one finding's quote against its artifact."""

    status: str
    detail: str = ""
    resolved: str = ""

    @property
    def passing(self) -> bool:
        """True when the quote was found in the named artifact."""
        return self.status in PASSING

    @property
    def failing(self) -> bool:
        """True when the artifact exists (or should) and the quote is not in it."""
        return self.status in FAILING

    def as_dict(self) -> dict[str, Any]:
        """JSON-ready form for the report."""
        payload: dict[str, Any] = {"status": self.status}
        if self.detail:
            payload["detail"] = self.detail
        if self.resolved:
            payload["resolved"] = self.resolved
        return payload


class Verifier:
    """Checks findings' quotes against repository files and registered sources."""

    def __init__(
        self,
        repo_root: Path | None,
        sources: SourceRegistry | None = None,
        *,
        line_window: int = DEFAULT_LINE_WINDOW,
    ) -> None:
        # `given_root` goes in the receipt so a report stays portable across
        # machines; `repo_root` is the resolved path used for containment checks.
        self.given_root = repo_root
        self.repo_root = repo_root.resolve() if repo_root else None
        self.sources = sources or SourceRegistry()
        self.line_window = line_window
        self._cache: dict[str, str | None] = {}

    @property
    def enabled(self) -> bool:
        """True when there is anything to verify against."""
        return self.repo_root is not None or bool(self.sources)

    def verify(self, finding: dict[str, Any]) -> Verdict:
        """Return a :class:`Verdict` for one finding."""
        if not self.enabled:
            return Verdict(SKIPPED, "verification disabled")

        locator = locators.parse(str(finding.get("path", "")))
        quote = locators.normalize_text(str(finding.get("quote", "")))
        if not quote:
            return Verdict(QUOTE_NOT_FOUND, "quote is empty after normalisation")

        if locator.kind == locators.FILE:
            text, verdict = self._read_file(locator)
        else:
            text, verdict = self._read_source(locator)
        if verdict is not None:
            return verdict
        assert text is not None

        if quote not in locators.normalize_text(text):
            return Verdict(
                QUOTE_NOT_FOUND,
                f"quote is not present in {locator.ref}",
                resolved=locator.ref,
            )
        return self._check_line(locator, quote, text)

    def _check_line(self, locator: Locator, quote: str, text: str) -> Verdict:
        if locator.line_start is None:
            return Verdict(VERIFIED, resolved=locator.ref)
        lines = text.splitlines()
        end = locator.line_end or locator.line_start
        low = max(0, locator.line_start - 1 - self.line_window)
        high = min(len(lines), end + self.line_window)
        window = locators.normalize_text("\n".join(lines[low:high]))
        if quote in window:
            return Verdict(VERIFIED, resolved=locator.ref)
        return Verdict(
            WRONG_LINE,
            f"quote exists but not within {self.line_window} lines of {locator.line_start}",
            resolved=locator.ref,
        )

    def _read_file(self, locator: Locator) -> tuple[str | None, Verdict | None]:
        if self.repo_root is None:
            return None, Verdict(NOT_VERIFIABLE, "no --repo-root for a file locator")
        if not locator.ref:
            return None, Verdict(PATH_NOT_FOUND, "empty path")
        if locator.is_absolute:
            return None, Verdict(OUTSIDE_ROOT, f"{locator.ref} is not inside the repository root")

        if locator.ref in self._cache:
            cached = self._cache[locator.ref]
            if cached is None:
                return None, Verdict(PATH_NOT_FOUND, f"{locator.ref} does not exist")
            return cached, None

        candidate = (self.repo_root / locator.ref).resolve()
        if not candidate.is_relative_to(self.repo_root):
            return None, Verdict(OUTSIDE_ROOT, f"{locator.ref} escapes the repository root")
        if not candidate.is_file():
            self._cache[locator.ref] = None
            return None, Verdict(PATH_NOT_FOUND, f"{locator.ref} does not exist")
        try:
            if candidate.stat().st_size > _MAX_BYTES:
                return None, Verdict(UNREADABLE, f"{locator.ref} is larger than {_MAX_BYTES} bytes")
            text = candidate.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return None, Verdict(UNREADABLE, f"{locator.ref}: {exc.strerror or exc}")
        self._cache[locator.ref] = text
        return text, None

    def _read_source(self, locator: Locator) -> tuple[str | None, Verdict | None]:
        text = self.sources.get(locator.ref)
        if text is not None:
            return text, None
        if not self.sources:
            return None, Verdict(
                NOT_VERIFIABLE,
                f"no --sources registered for {locator.kind} locator {locator.ref!r}",
            )
        logger.debug(
            "unknown {} id {!r}; known ids: {}", locator.kind, locator.ref, self.sources.ids
        )
        return None, Verdict(
            PATH_NOT_FOUND,
            f"{locator.kind} {locator.ref!r} is not among the registered sources",
        )


__all__ = [
    "DEFAULT_LINE_WINDOW",
    "FAILING",
    "INCONCLUSIVE",
    "PASSING",
    "Verdict",
    "Verifier",
]
