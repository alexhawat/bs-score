"""Jev-based finding discovery via TypeSafe System One.

``bs-score find --jev`` collects deterministic candidate units from markdown
artifacts, asks TypeSafe (Jev) structured questions about each one, and emits a
``findings.schema.json`` payload. Quotes are always verbatim spans from the
file; titles come from fixed templates keyed by finding type.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .claims import FENCED_BLOCK, _line_of, load_project_facts

FINDING_TYPES = (
    "breaking_bug",
    "security_issue",
    "missing_feature",
    "bug",
    "wrong_claim",
)

DEFAULT_DOC_GLOBS = ("README.md", "docs/**/*.md", "*.md")

# Sentences that look like checkable assertions rather than headings or fluff.
CLAIM_HINT = re.compile(
    r"(?i)\b("
    r"always|never|automatically|by default|zero-config|deterministic|"
    r"requires?|supports?|install|configure|run|must|will|can(?:not|'t)?|"
    r"guarantee|verified|enforced|tested|version|python\b"
    r")\b|`[^`]+`"
)

SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")

TITLE_TEMPLATES: dict[str, str] = {
    "wrong_claim": "Stated claim contradicted by the artifact",
    "missing_feature": "Advertised capability not present in the artifact",
    "bug": "Incorrect behaviour in the artifact",
    "breaking_bug": "Crash, data loss, or broken workflow",
    "security_issue": "Security weakness in the artifact",
}

TARGET_FOR_PATH: dict[str, str] = {
    ".md": "readme",
    ".py": "code",
    ".json": "other",
    ".yaml": "other",
    ".yml": "other",
}

SUPPORTED_TARGET_KINDS = frozenset({"repo", "docs"})


class JevError(Exception):
    """Base error for Jev discovery."""


class JevDependencyError(JevError):
    """typesafe-sdk is not installed."""


class JevConfigError(JevError):
    """Missing API key or unsupported options."""


@dataclass(frozen=True)
class CandidateUnit:
    """One verbatim span Jev may judge."""

    path: str  # repo-relative posix path
    line: int  # 1-based
    quote: str  # verbatim span from the file
    context: str  # surrounding excerpt for Jev state


class JevClient(Protocol):
    """Minimal TypeSafe client surface used by discovery."""

    def system_one(
        self,
        state: Any,
        questions: dict[str, Any],
    ) -> Any: ...


def require_jev_dependencies() -> tuple[Any, Any, Any, Any]:
    """Import TypeSafe SDK types or raise with install instructions."""
    try:
        from typesafe_sdk import Choice, Noul, Score, TypeSafeClient
    except ImportError as exc:  # pragma: no cover - exercised via tests
        raise JevDependencyError(
            "find --jev requires the optional typesafe-sdk package. "
            "Install with: uv sync --extra jev  (or: pip install 'bs-score[jev]')"
        ) from exc
    return TypeSafeClient, Choice, Noul, Score


def require_api_key() -> str:
    """Return TYPESAFE_API_KEY or raise."""
    key = os.environ.get("TYPESAFE_API_KEY", "").strip()
    if not key:
        raise JevConfigError(
            "find --jev requires TYPESAFE_API_KEY in the environment. "
            "See https://docs.typesafe.ai/sdk/python/"
        )
    return key


def default_doc_paths(repo_root: Path) -> list[Path]:
    """Return markdown files under repo_root for the default glob set."""
    return collect_paths(repo_root, DEFAULT_DOC_GLOBS)


def collect_paths(repo_root: Path, globs: tuple[str, ...]) -> list[Path]:
    """Resolve repeatable path globs relative to repo_root."""
    seen: set[Path] = set()
    ordered: list[Path] = []
    for pattern in globs:
        if any(char in pattern for char in "*?[]"):
            for path in sorted(repo_root.glob(pattern)):
                if path.is_file() and path not in seen:
                    seen.add(path)
                    ordered.append(path)
            continue
        path = repo_root / pattern
        if path.is_file() and path not in seen:
            seen.add(path)
            ordered.append(path)
    return ordered


def _strip_fences(text: str) -> str:
    """Remove fenced code blocks so prose sentences are not parsed from them."""
    return FENCED_BLOCK.sub("", text)


def _sentences_from_paragraph(paragraph: str) -> list[str]:
    parts = SENTENCE_SPLIT.split(paragraph.strip())
    return [part.strip() for part in parts if part.strip()]


def _claim_like(sentence: str) -> bool:
    if len(sentence) < 12:
        return False
    if sentence.lstrip().startswith("#"):
        return False
    return CLAIM_HINT.search(sentence) is not None


def extract_units_from_markdown(path: Path, repo_root: Path) -> list[CandidateUnit]:
    """Extract claim-like sentences from one markdown file."""
    text = path.read_text(encoding="utf-8", errors="replace")
    prose = _strip_fences(text)
    try:
        relative = path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        relative = path.name

    units: list[CandidateUnit] = []
    paragraph_lines: list[str] = []
    paragraph_start = 0
    offset = 0

    for raw_line in prose.splitlines(keepends=True):
        line = raw_line.rstrip("\n")
        stripped = line.strip()
        if not stripped:
            if paragraph_lines:
                paragraph = " ".join(paragraph_lines)
                for sentence in _sentences_from_paragraph(paragraph):
                    if not _claim_like(sentence):
                        continue
                    line_no = _line_of(text, paragraph_start + paragraph.find(sentence))
                    units.append(
                        CandidateUnit(
                            path=relative,
                            line=line_no,
                            quote=sentence,
                            context=_context_excerpt(text, line_no),
                        )
                    )
                paragraph_lines = []
            offset += len(raw_line)
            continue
        if stripped.startswith("#"):
            paragraph_lines = []
            paragraph_start = offset + len(raw_line)
            offset += len(raw_line)
            continue
        if not paragraph_lines:
            paragraph_start = offset
        paragraph_lines.append(stripped)
        offset += len(raw_line)

    if paragraph_lines:
        paragraph = " ".join(paragraph_lines)
        for sentence in _sentences_from_paragraph(paragraph):
            if not _claim_like(sentence):
                continue
            line_no = _line_of(text, paragraph_start + paragraph.find(sentence))
            units.append(
                CandidateUnit(
                    path=relative,
                    line=line_no,
                    quote=sentence,
                    context=_context_excerpt(text, line_no),
                )
            )
    return units


def _context_excerpt(text: str, line_no: int, *, radius: int = 3) -> str:
    lines = text.splitlines()
    start = max(0, line_no - 1 - radius)
    end = min(len(lines), line_no + radius)
    return "\n".join(lines[start:end])


def collect_units(
    repo_root: Path,
    *,
    target_kind: str,
    globs: tuple[str, ...] = DEFAULT_DOC_GLOBS,
    paths: tuple[Path, ...] = (),
) -> list[CandidateUnit]:
    """Collect candidate units for supported review types."""
    if target_kind not in SUPPORTED_TARGET_KINDS:
        supported = ", ".join(sorted(SUPPORTED_TARGET_KINDS))
        raise JevConfigError(
            f"--target-kind {target_kind!r} is not supported by find --jev yet "
            f"(supported: {supported})"
        )

    files = list(paths) if paths else collect_paths(repo_root, globs)
    units: list[CandidateUnit] = []
    for path in files:
        if path.suffix.lower() != ".md":
            continue
        units.extend(extract_units_from_markdown(path, repo_root))
    return units


def _finding_target(path: str) -> str:
    suffix = Path(path).suffix.lower()
    return TARGET_FOR_PATH.get(suffix, "other")


def _build_questions(Choice: Any, Noul: Any, Score: Any) -> dict[str, Any]:
    return {
        "keep": Noul(
            instructions=(
                "The quoted span states a concrete, checkable claim about this "
                "project (a path, command, flag, version, guarantee, or capability) "
                "that is false or contradicted by the repository context provided."
            ),
        ),
        "finding_type": Choice(
            instructions="When the claim is a real defect, which finding type fits best?",
            criteria={
                "wrong_claim": "A stated fact in the text is contradicted by the artifact",
                "missing_feature": "The text asserts a capability with nothing behind it",
                "bug": "Incorrect behaviour that is not catastrophic",
                "breaking_bug": "Crash, wrong result, data loss, or workflow that cannot run",
                "security_issue": "Auth, injection, secrets, privilege, or unsafe instruction",
            },
        ),
        "confidence": Score(
            instructions="How confident are you that this is a real defect?",
            criteria=[
                "Low — plausible but uncertain",
                "Medium — likely a real issue",
                "High — clearly contradicted or broken",
            ],
        ),
    }


def _confidence_value(score_answer: Any) -> float:
    if getattr(score_answer, "confidence", None) is not None:
        return float(max(0.0, min(1.0, score_answer.confidence)))
    index = int(getattr(score_answer, "score", 1))
    return {0: 0.33, 1: 0.66, 2: 0.9}.get(index, 0.66)


def judge_unit(
    client: JevClient,
    unit: CandidateUnit,
    *,
    repo_root: Path,
    target_kind: str,
    questions: dict[str, Any],
    keep_threshold: float = 0.5,
) -> dict[str, Any] | None:
    """Ask Jev about one unit; return a finding dict or None if rejected."""
    facts = load_project_facts(repo_root)
    state = {
        "target_kind": target_kind,
        "file": unit.path,
        "line": unit.line,
        "quote": unit.quote,
        "context": unit.context,
        "project": {
            "scripts": sorted(facts.scripts),
            "version": facts.version,
            "python_floor": facts.python_floor,
        },
    }
    response = client.system_one(state=state, questions=questions)
    keep_answer = response.answers["keep"]
    if float(keep_answer.noul) < keep_threshold:
        return None

    type_answer = response.answers["finding_type"]
    finding_type = type_answer.choice
    if finding_type not in FINDING_TYPES:
        finding_type = "wrong_claim"

    confidence_answer = response.answers["confidence"]
    return {
        "type": finding_type,
        "title": TITLE_TEMPLATES[finding_type],
        "path": f"{unit.path}:{unit.line}",
        "quote": unit.quote,
        "target": _finding_target(unit.path),
        "confidence": _confidence_value(confidence_answer),
    }


def discover_findings(
    repo_root: Path,
    *,
    target_kind: str,
    globs: tuple[str, ...] = DEFAULT_DOC_GLOBS,
    paths: tuple[Path, ...] = (),
    client_factory: Callable[[], JevClient] | None = None,
    keep_threshold: float = 0.5,
) -> dict[str, Any]:
    """Run Jev discovery and return a findings payload."""
    TypeSafeClient, Choice, Noul, Score = require_jev_dependencies()
    require_api_key()
    questions = _build_questions(Choice, Noul, Score)

    units = collect_units(
        repo_root,
        target_kind=target_kind,
        globs=globs,
        paths=paths,
    )
    files_read = sorted({unit.path for unit in units})

    factory = client_factory or (lambda: TypeSafeClient())
    client = factory()
    findings: list[dict[str, Any]] = []
    try:
        for index, unit in enumerate(units, start=1):
            judged = judge_unit(
                client,
                unit,
                repo_root=repo_root,
                target_kind=target_kind,
                questions=questions,
                keep_threshold=keep_threshold,
            )
            if judged is None:
                continue
            judged["id"] = f"jev-{index}"
            findings.append(judged)
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()

    payload: dict[str, Any] = {
        "version": 2,
        "target_kind": target_kind,
        "findings": findings,
    }
    if files_read:
        payload["audit"] = {"files_read": files_read}
    return payload


__all__ = [
    "CandidateUnit",
    "DEFAULT_DOC_GLOBS",
    "FINDING_TYPES",
    "JevConfigError",
    "JevDependencyError",
    "JevError",
    "SUPPORTED_TARGET_KINDS",
    "collect_paths",
    "collect_units",
    "default_doc_paths",
    "discover_findings",
    "extract_units_from_markdown",
    "judge_unit",
    "require_api_key",
    "require_jev_dependencies",
]
