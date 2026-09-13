"""Registry for evidence that does not live in a repository file.

A prompt pasted into a chat and a pull-request review body are both real
artifacts a finding can quote, and neither is a file in the tree under audit.
``--sources`` makes them addressable so their quotes get verified like any
other: without it, a ``prompt`` or ``review`` audit is scored on the model's
word alone.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from loguru import logger

TEXT_SUFFIXES = frozenset({".md", ".txt", ".prompt", ".j2", ".jinja", ".jinja2", ".xml"})


class SourceError(ValueError):
    """A --sources argument is missing, unreadable, or malformed."""


@dataclass
class SourceRegistry:
    """Maps locator refs (prompt ids, review locators) to their text."""

    texts: dict[str, str] = field(default_factory=dict)
    origins: dict[str, str] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return bool(self.texts)

    @property
    def ids(self) -> list[str]:
        """Registered ids, sorted."""
        return sorted(self.texts)

    def get(self, ref: str) -> str | None:
        """Return the text registered for ``ref``, or None."""
        return self.texts.get(ref)

    def _add(self, ref: str, text: str, origin: str, *, alias: bool = False) -> None:
        if ref in self.texts and self.texts[ref] != text:
            if alias:
                logger.debug("ambiguous alias {!r}; dropping it", ref)
                self.texts.pop(ref, None)
                self.origins.pop(ref, None)
                return
            raise SourceError(
                f"duplicate source id {ref!r} with different text "
                f"({self.origins.get(ref)} and {origin})"
            )
        self.texts[ref] = text
        self.origins[ref] = origin


def _load_manifest(path: Path, registry: SourceRegistry) -> None:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SourceError(f"cannot read source manifest {path}: {exc}") from exc
    entries = document.get("sources") if isinstance(document, dict) else document
    if not isinstance(entries, list):
        raise SourceError(f"{path}: expected a list under 'sources' (or a top-level list)")
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or "id" not in entry or "text" not in entry:
            raise SourceError(f"{path}: sources[{index}] needs both 'id' and 'text'")
        registry._add(str(entry["id"]), str(entry["text"]), f"{path}#sources[{index}]")


def _load_jsonl(path: Path, registry: SourceRegistry) -> None:
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SourceError(f"{path}:{number}: not valid JSON: {exc}") from exc
        if not isinstance(entry, dict) or "id" not in entry or "text" not in entry:
            raise SourceError(f"{path}:{number}: needs both 'id' and 'text'")
        registry._add(str(entry["id"]), str(entry["text"]), f"{path}:{number}")


def _load_directory(root: Path, registry: SourceRegistry) -> None:
    files = sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in TEXT_SUFFIXES)
    if not files:
        raise SourceError(
            f"{root} contains no text sources "
            f"(looked for {', '.join(sorted(TEXT_SUFFIXES))})"
        )
    stems: dict[str, int] = {}
    for file in files:
        stems[file.stem] = stems.get(file.stem, 0) + 1
    for file in files:
        ref = file.relative_to(root).as_posix()
        text = file.read_text(encoding="utf-8", errors="replace")
        registry._add(ref, text, str(file))
        # A bare stem is a convenience alias, and only when it is unambiguous.
        if stems[file.stem] == 1 and file.stem != ref:
            registry._add(file.stem, text, str(file), alias=True)


def load_sources(paths: list[Path]) -> SourceRegistry:
    """Build a :class:`SourceRegistry` from files, JSON/JSONL manifests, or directories.

    Args:
        paths: Each is a directory of prompt files, a ``.json`` manifest, a
            ``.jsonl`` stream, or a single text file (registered under its stem
            and its name).

    Raises:
        SourceError: A path is missing or malformed.
    """
    registry = SourceRegistry()
    for path in paths:
        if not path.exists():
            raise SourceError(f"--sources path does not exist: {path}")
        if path.is_dir():
            _load_directory(path, registry)
        elif path.suffix.lower() == ".json":
            _load_manifest(path, registry)
        elif path.suffix.lower() == ".jsonl":
            _load_jsonl(path, registry)
        else:
            text = path.read_text(encoding="utf-8", errors="replace")
            registry._add(path.name, text, str(path))
            registry._add(path.stem, text, str(path), alias=True)
    logger.info("loaded {} evidence source(s): {}", len(registry.texts), registry.ids)
    return registry


__all__ = ["SourceError", "SourceRegistry", "load_sources"]
