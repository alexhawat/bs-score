"""Count how many places a defect actually occurs, instead of trusting the count.

A model that finds one dead command in the README has found one instance of it;
the repository may hold twenty-six. Asking the model to enumerate them invites
either an undercount (it stopped looking) or an inflated score (it filed each
one separately). Neither is necessary: once a quote is verified, the scorer can
sweep the tree for it and report the blast radius as a measurement.

The score still counts the defect once. Only the report gets bigger.
"""

from __future__ import annotations

import bisect
import subprocess
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from .locators import normalize_text

#: Extensions that are never worth searching for a source quote.
BINARY_SUFFIXES = frozenset(
    {
        ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip", ".gz",
        ".tar", ".whl", ".so", ".dylib", ".dll", ".exe", ".woff", ".woff2",
        ".ttf", ".otf", ".mp4", ".mp3", ".wav", ".bin", ".pyc",
    }
)

#: Directories skipped even when a file inside them is tracked.
SKIP_DIRS = frozenset(
    {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache", ".ruff_cache",
     ".mypy_cache", "dist", "build", ".tox"}
)

MAX_FILE_BYTES = 1_000_000
MAX_FILES = 20_000


@dataclass(frozen=True)
class Occurrence:
    """One place a quote appears."""

    path: str
    line: int

    def as_dict(self) -> dict[str, object]:
        """JSON-ready form."""
        return {"path": self.path, "line": self.line}


@dataclass
class _IndexedFile:
    text: str
    offsets: list[int]
    lines: list[int]


def _normalize_with_lines(raw: str, *, fold_case: bool = False) -> _IndexedFile:
    """Normalise a file and keep a map from normalised offset back to line number.

    ``normalize_text`` collapses every whitespace run to a single space, so the
    joined per-line form is character-identical to normalising the whole file —
    which means an offset found here maps back to a real line.
    """
    text_parts: list[str] = []
    offsets: list[int] = []
    lines: list[int] = []
    cursor = 0
    for number, line in enumerate(raw.splitlines(), start=1):
        piece = normalize_text(line, fold_case=fold_case)
        if not piece:
            continue
        if text_parts:
            cursor += 1  # the single space that joins the previous piece
        offsets.append(cursor)
        lines.append(number)
        text_parts.append(piece)
        cursor += len(piece)
    return _IndexedFile(" ".join(text_parts), offsets, lines)


class TreeIndex:
    """A normalised, searchable view of every text file in a tree.

    Built lazily and once per run: the files are read a single time and searched
    for every quote, so a sweep costs one pass regardless of how many findings
    there are.
    """

    def __init__(self, root: Path, *, fold_case: bool = False) -> None:
        self.root = root.resolve()
        # Must match the verifier: if a quote verified case-insensitively, the
        # sweep has to find it the same way or a verified finding reports zero
        # occurrences.
        self.fold_case = fold_case
        self._files: dict[str, _IndexedFile] | None = None

    @property
    def file_count(self) -> int:
        """Number of indexed text files."""
        return len(self._index())

    def paths(self) -> list[str]:
        """Repo-relative paths of every indexed file, sorted."""
        return sorted(self._index())

    def _candidate_paths(self) -> list[Path]:
        """Tracked files when this is a git checkout, else everything on disk."""
        try:
            result = subprocess.run(
                ["git", "-C", str(self.root), "ls-files", "-z", "--cached", "--others",
                 "--exclude-standard"],
                capture_output=True,
                timeout=30,
                check=False,
            )
            if result.returncode == 0:
                names = [n for n in result.stdout.decode("utf-8", "replace").split("\0") if n]
                logger.debug("git ls-files returned {} path(s)", len(names))
                return [self.root / name for name in names]
        except (OSError, subprocess.SubprocessError):
            logger.debug("git unavailable; falling back to a filesystem walk")
        return [p for p in self.root.rglob("*") if p.is_file()]

    def _index(self) -> dict[str, _IndexedFile]:
        if self._files is not None:
            return self._files

        indexed: dict[str, _IndexedFile] = {}
        for path in self._candidate_paths():
            if len(indexed) >= MAX_FILES:
                logger.warning("stopped indexing at {} files", MAX_FILES)
                break
            try:
                relative = path.relative_to(self.root)
            except ValueError:
                continue
            if SKIP_DIRS & set(relative.parts):
                continue
            if path.suffix.lower() in BINARY_SUFFIXES:
                continue
            try:
                if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
                    continue
                raw = path.read_bytes()
            except OSError:
                continue
            if b"\0" in raw[:8192]:
                continue
            indexed[relative.as_posix()] = _normalize_with_lines(
                raw.decode("utf-8", "replace"), fold_case=self.fold_case
            )

        logger.info("indexed {} text file(s) under {}", len(indexed), self.root)
        self._files = indexed
        return indexed

    def find(self, quote: str, *, limit: int = 200) -> list[Occurrence]:
        """Return every place ``quote`` appears, as ``(path, line)`` pairs.

        Args:
            quote: Raw quote text; normalised here so callers need not.
            limit: Stop after this many occurrences.
        """
        needle = normalize_text(quote, fold_case=self.fold_case)
        if not needle:
            return []
        found: list[Occurrence] = []
        for relative, indexed in sorted(self._index().items()):
            start = indexed.text.find(needle)
            while start != -1 and len(found) < limit:
                position = bisect.bisect_right(indexed.offsets, start) - 1
                line = indexed.lines[position] if position >= 0 else 1
                found.append(Occurrence(relative, line))
                start = indexed.text.find(needle, start + 1)
            if len(found) >= limit:
                logger.warning("occurrence limit {} reached for a quote", limit)
                break
        return found


__all__ = ["BINARY_SUFFIXES", "MAX_FILES", "MAX_FILE_BYTES", "Occurrence", "TreeIndex"]
