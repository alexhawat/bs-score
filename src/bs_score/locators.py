"""Parse, canonicalise, and fingerprint the locators findings point at.

Two jobs, both load-bearing for determinism:

* **Canonical paths.** ``src/api.py:88``, ``./src/api.py:91`` and ``src/api.py``
  all name the same file. Scoring them as three findings turns the score into a
  function of the model's formatting rather than of what it found.
* **Quote fingerprints.** A defect is identified by the text quoted, not by the
  line number attached to it, so the fingerprint of the normalised quote is part
  of the dedupe key.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from pathlib import PurePosixPath

LINE_SUFFIX = re.compile(r":(\d+)(?:-(\d+))?$")
REVIEW_LOCATOR = re.compile(r"^(?:review:|pull/\d+/reviews/)")

# Typographic substitutions applied before comparison: a model that re-types a
# quote will usually straighten or curl the punctuation, and that is not a lie.
_TYPOGRAPHY = str.maketrans(
    {
        "‘": "'",
        "’": "'",
        "‚": "'",
        "“": '"',
        "”": '"',
        "„": '"',
        "–": "-",
        "—": "-",
        "−": "-",
        " ": " ",
        "…": "...",
    }
)

FILE = "file"
PROMPT = "prompt"
REVIEW = "review"


@dataclass(frozen=True)
class Locator:
    """A parsed ``path`` field."""

    raw: str
    kind: str
    ref: str
    line_start: int | None = None
    line_end: int | None = None
    fragment: str = ""

    @property
    def is_absolute(self) -> bool:
        """True when the locator escapes any repository root."""
        return self.kind == FILE and (self.ref.startswith("/") or ":" in self.ref.split("/")[0])


def normalize_text(text: str) -> str:
    """Fold a string to its comparison form: NFKC, plain punctuation, single spaces."""
    folded = unicodedata.normalize("NFKC", text).translate(_TYPOGRAPHY)
    return re.sub(r"\s+", " ", folded).strip()


def quote_fingerprint(quote: str) -> str:
    """Stable short digest of a quote's comparison form."""
    return hashlib.sha256(normalize_text(quote).encode("utf-8")).hexdigest()[:16]


def canonical_file(ref: str) -> str:
    """Collapse a file reference to one spelling.

    Strips ``./`` segments and resolves ``..`` textually. Leading dots are
    preserved: ``.claude/agents/x.md`` is a real path, not a relative marker.
    """
    text = ref.strip().replace("\\", "/")
    if not text:
        return ""
    leading_slash = text.startswith("/")
    parts: list[str] = []
    for part in PurePosixPath(text).parts:
        if part in {"", "/", "."}:
            continue
        if part == ".." and parts and parts[-1] != "..":
            parts.pop()
            continue
        parts.append(part)
    joined = "/".join(parts)
    return f"/{joined}" if leading_slash else joined


def parse(path: str) -> Locator:
    """Parse a finding's ``path`` into a :class:`Locator`.

    Recognised forms::

        src/api.py                  file
        src/api.py:88               file, line 88
        src/api.py:88-95            file, lines 88..95
        .claude/agents/x.md         file (leading dot preserved)
        prompt:system               prompt, resolved from --sources
        prompt:system:12            prompt, line 12
        pull/12/reviews/34#scope    review locator, resolved from --sources
    """
    raw = path.strip()
    body = raw
    fragment = ""
    if "#" in body:
        body, _, fragment = body.partition("#")

    if body.startswith("prompt:"):
        remainder = body[len("prompt:") :]
        match = LINE_SUFFIX.search(remainder)
        if match:
            return Locator(
                raw=raw,
                kind=PROMPT,
                ref=remainder[: match.start()].strip(),
                line_start=int(match.group(1)),
                line_end=int(match.group(2)) if match.group(2) else None,
                fragment=fragment,
            )
        return Locator(raw=raw, kind=PROMPT, ref=remainder.strip(), fragment=fragment)

    if REVIEW_LOCATOR.match(body):
        return Locator(raw=raw, kind=REVIEW, ref=body.strip(), fragment=fragment)

    match = LINE_SUFFIX.search(body)
    if match:
        return Locator(
            raw=raw,
            kind=FILE,
            ref=canonical_file(body[: match.start()]),
            line_start=int(match.group(1)),
            line_end=int(match.group(2)) if match.group(2) else None,
            fragment=fragment,
        )
    return Locator(raw=raw, kind=FILE, ref=canonical_file(body), fragment=fragment)


__all__ = [
    "FILE",
    "PROMPT",
    "REVIEW",
    "Locator",
    "canonical_file",
    "normalize_text",
    "parse",
    "quote_fingerprint",
]
