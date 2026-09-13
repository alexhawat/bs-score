"""Deterministic claim checking — no LLM involved.

``bs-score claims README.md`` extracts the assertions a document makes that a
machine can prove or disprove on its own: paths that must exist, commands that
must be declared entry points, flags that must exist in the argparse
definition, version numbers that must match the packaging metadata, Markdown
links that must resolve, and fenced code blocks that must parse.

Every failed check can be emitted as a pre-verified ``wrong_claim`` finding
(``--emit-findings``), ready for ``bs-score`` to score. The output is a floor,
not a ceiling: semantics, guarantees, and behaviour still need the human or
the model — that is what the ``docs`` checklist is for.
"""

from __future__ import annotations

import ast
import json
import re
import shutil
import subprocess
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

INLINE_CODE = re.compile(r"`([^`\n]+)`")
FENCED_BLOCK = re.compile(r"^```(\w*)\s*\n(.*?)^```", re.MULTILINE | re.DOTALL)
MARKDOWN_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
HEADING = re.compile(r"^#{1,6}\s+(.*?)\s*#*\s*$", re.MULTILINE)
FLAG = re.compile(r"(?<![\w-])(--[a-zA-Z][\w-]*)")
VERSION_MENTION = re.compile(r"\b(?:version\s+|v)(\d+\.\d+(?:\.\d+)?)\b", re.IGNORECASE)
PYTHON_FLOOR_MENTION = re.compile(r"\bPython\s+(\d+\.\d+)\b", re.IGNORECASE)
# A code span that looks like a path: segments separated by /, or a file-ish
# name with a short suffix. URLs, flags, and KEY=value pairs are not paths.
PATH_LIKE = re.compile(r"^(?:\.?[\w.-]+/)+[\w.-]+/?$|^[\w.-]+\.[A-Za-z0-9]{1,8}$")

_URL_SCHEMES = ("http://", "https://", "mailto:", "ftp://")


@dataclass(frozen=True)
class Claim:
    """One mechanically checked assertion."""

    kind: str  # path | command | flag | version | link | code_block
    claim: str  # human-readable statement of what was checked
    verdict: str  # pass | fail | skip
    evidence: str
    span: str  # verbatim text from the document the claim came from
    line: int  # 1-based line of the span in the document

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "claim": self.claim,
            "verdict": self.verdict,
            "evidence": self.evidence,
            "line": self.line,
        }


@dataclass
class ProjectFacts:
    """What the packaging metadata and CLI definitions assert."""

    scripts: dict[str, str] = field(default_factory=dict)  # name -> module:func
    flags: dict[str, set[str]] = field(default_factory=dict)  # script -> --flags
    version: str | None = None
    python_floor: str | None = None  # e.g. "3.11" from requires-python


# --- project facts ------------------------------------------------------------


def _parse_pyproject(repo_root: Path) -> dict[str, Any]:
    """Extract the fields claims care about, without a TOML dependency.

    Python 3.10 has no tomllib, and the fields we need (``project.version``,
    ``project.requires-python``, ``project.scripts``) sit in simple sections,
    so a small section-aware reader is enough and stays deterministic.
    """
    pyproject = repo_root / "pyproject.toml"
    facts: dict[str, Any] = {"scripts": {}}
    if not pyproject.is_file():
        return facts
    section = ""
    for raw in pyproject.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("["):
            section = line.strip("[]").strip()
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if section == "project" and key == "version":
            facts["version"] = value
        elif section == "project" and key == "requires-python":
            facts["requires-python"] = value
        elif section == "project.scripts" and key:
            facts["scripts"][key] = value
    return facts


def _module_candidates(repo_root: Path, module: str) -> list[Path]:
    relative = Path(*module.split(".")).with_suffix(".py")
    return [repo_root / relative, repo_root / "src" / relative]


def _argparse_flags(path: Path) -> set[str]:
    """Collect the option strings a module registers with argparse."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return set()
    flags: set[str] = {"--help"}  # argparse always adds -h/--help
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr != "add_argument":
            continue
        for arg in node.args:
            if (
                isinstance(arg, ast.Constant)
                and isinstance(arg.value, str)
                and arg.value.startswith("--")
            ):
                flags.add(arg.value)
    return flags


def load_project_facts(repo_root: Path) -> ProjectFacts:
    """Read packaging metadata and CLI flag definitions under ``repo_root``."""
    raw = _parse_pyproject(repo_root)
    facts = ProjectFacts(scripts=dict(raw["scripts"]))
    facts.version = raw.get("version")
    requires_python = raw.get("requires-python") or ""
    floor = re.search(r">=\s*(\d+\.\d+)", requires_python)
    if floor:
        facts.python_floor = floor.group(1)
    for name, target in facts.scripts.items():
        module = target.split(":", 1)[0]
        for candidate in _module_candidates(repo_root, module):
            if candidate.is_file():
                facts.flags[name] = _argparse_flags(candidate)
                break
    return facts


# --- individual checks ----------------------------------------------------------


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _slug(heading: str) -> str:
    """GitHub-style anchor slug for a Markdown heading."""
    slug = re.sub(r"[^\w\s-]", "", heading.strip().lower())
    return re.sub(r"\s+", "-", slug)


def check_paths(text: str, repo_root: Path) -> list[Claim]:
    """Inline-code spans that look like paths must exist under the repo root."""
    claims: list[Claim] = []
    for match in INLINE_CODE.finditer(text):
        span = match.group(0)
        token = match.group(1).strip()
        if not PATH_LIKE.match(token):
            continue
        if any(token.startswith(scheme) for scheme in _URL_SCHEMES) or "=" in token:
            continue
        claims.append(_check_path(token, span, _line_of(text, match.start()), repo_root))
    return claims


def _check_path(token: str, span: str, line: int, repo_root: Path) -> Claim:
    claim = f"path `{token}` exists"
    if (repo_root / token.rstrip("/")).exists():
        return Claim("path", claim, "pass", f"found {token}", span, line)
    # A bare name in prose (`findings.valid.json`) often means "the file by
    # this name in this tree", not "at the root". A unique match satisfies the
    # claim; several matches make it ambiguous; none makes it false.
    name = token.rstrip("/").rsplit("/", 1)[-1]
    try:
        matches = [
            p for p in repo_root.rglob(name)
            if not {".git", ".venv", "node_modules", "__pycache__"} & set(p.parts)
        ]
    except OSError:
        matches = []
    if len(matches) == 1:
        return Claim("path", claim, "pass",
                     f"found at {matches[0].relative_to(repo_root)}", span, line)
    if matches:
        return Claim("path", claim, "skip",
                     f"ambiguous: {len(matches)} files named {name}", span, line)
    return Claim("path", claim, "fail",
                 f"{token} does not exist under {repo_root}", span, line)


def check_commands(text: str, facts: ProjectFacts) -> list[Claim]:
    """Commands named in the doc that match a declared entry point are real."""
    claims: list[Claim] = []
    for name in sorted(facts.scripts):
        for match in re.finditer(rf"(?<![\w./-]){re.escape(name)}(?![\w-])", text):
            claims.append(
                Claim("command", f"command `{name}` is a declared entry point", "pass",
                      f"pyproject.toml [project.scripts] declares {name} = {facts.scripts[name]}",
                      name, _line_of(text, match.start()))
            )
            break  # one claim per command is enough
    return claims


def check_flags(text: str, facts: ProjectFacts) -> list[Claim]:
    """Flags used with a known entry point must exist in its CLI definition."""
    claims: list[Claim] = []
    for name in sorted(facts.scripts):
        if name not in facts.flags:
            continue
        known = facts.flags[name]
        for match in re.finditer(
            rf"(?<![\w./-]){re.escape(name)}((?:\s+[^\s`|&;]+)*)", text
        ):
            invocation = match.group(0)
            for flag in FLAG.findall(invocation):
                if flag in known:
                    claims.append(
                        Claim("flag", f"`{name}` accepts {flag}", "pass",
                              f"{flag} is registered in the argparse definition",
                              invocation.strip(), _line_of(text, match.start()))
                    )
                else:
                    claims.append(
                        Claim("flag", f"`{name}` accepts {flag}", "fail",
                              f"{flag} is not among the declared flags: {sorted(known)}",
                              invocation.strip(), _line_of(text, match.start()))
                    )
    return claims


def check_versions(text: str, facts: ProjectFacts) -> list[Claim]:
    """Version numbers in the doc must agree with the packaging metadata."""
    claims: list[Claim] = []
    if facts.version:
        for match in VERSION_MENTION.finditer(text):
            mentioned = match.group(1)
            verdict = "pass" if mentioned == facts.version else "fail"
            evidence = (
                f"pyproject.toml declares version {facts.version}"
                if verdict == "pass"
                else f"document says {mentioned}; pyproject.toml declares {facts.version}"
            )
            claims.append(
                Claim("version", f"version {mentioned} matches pyproject.toml", verdict,
                      evidence, match.group(0), _line_of(text, match.start()))
            )
    if facts.python_floor:
        required = tuple(int(p) for p in facts.python_floor.split("."))
        for match in PYTHON_FLOOR_MENTION.finditer(text):
            claimed = match.group(1)
            ok = tuple(int(p) for p in claimed.split(".")) >= required
            claims.append(
                Claim("version", f"installable on Python {claimed}", "pass" if ok else "fail",
                      f"requires-python floor is {facts.python_floor}; the doc says {claimed}",
                      match.group(0), _line_of(text, match.start()))
            )
    return claims


def check_links(
    text: str, doc_path: Path, repo_root: Path, *, check_urls: bool = False
) -> list[Claim]:
    """Markdown links must resolve: relative targets and in-doc anchors."""
    claims: list[Claim] = []
    for match in MARKDOWN_LINK.finditer(text):
        target = match.group(1)
        line = _line_of(text, match.start())
        span = match.group(0)
        if any(target.startswith(scheme) for scheme in _URL_SCHEMES):
            if not check_urls:
                claims.append(Claim("link", f"URL {target} responds", "skip",
                                    "pass --check-links to fetch URLs", span, line))
                continue
            verdict, evidence = _check_url(target)
            claims.append(Claim("link", f"URL {target} responds", verdict, evidence, span, line))
            continue
        path_part, _, anchor = target.partition("#")
        if path_part:
            resolved = (doc_path.parent / path_part).resolve()
            if not resolved.exists():
                claims.append(Claim("link", f"link target {target} resolves", "fail",
                                    f"{path_part} does not exist relative to {doc_path.name}",
                                    span, line))
                continue
            if anchor and resolved.suffix.lower() in {".md", ".markdown"}:
                claims.append(_check_anchor(resolved, anchor, span, line, target))
                continue
            claims.append(Claim("link", f"link target {target} resolves", "pass",
                                f"found {path_part}", span, line))
        elif anchor:
            claims.append(_check_anchor(doc_path, anchor, span, line, target))
    return claims


def _check_anchor(path: Path, anchor: str, span: str, line: int, target: str) -> Claim:
    try:
        headings = HEADING.findall(path.read_text(encoding="utf-8"))
    except OSError as exc:
        return Claim("link", f"anchor #{anchor} exists", "skip", str(exc), span, line)
    if anchor in {_slug(h) for h in headings}:
        return Claim("link", f"anchor #{anchor} exists", "pass",
                     f"heading found in {path.name}", span, line)
    return Claim("link", f"anchor #{anchor} exists", "fail",
                 f"no heading in {path.name} slugs to #{anchor}", span, line)


def _check_url(url: str) -> tuple[str, str]:
    request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "bs-score"})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310
            return "pass", f"HTTP {response.status}"
    except Exception as exc:  # network errors are evidence of a dead link
        return "fail", f"{type(exc).__name__}: {exc}"


def check_code_blocks(text: str) -> list[Claim]:
    """Fenced python/json/bash blocks must parse; other languages are skipped."""
    claims: list[Claim] = []
    for match in FENCED_BLOCK.finditer(text):
        lang, body = match.group(1).lower(), match.group(2)
        line = _line_of(text, match.start())
        span = next((ln for ln in body.splitlines() if ln.strip()), f"```{lang}")
        label = f"```{lang}` block at line {line} parses"
        if lang in {"python", "py"}:
            try:
                ast.parse(body)
            except SyntaxError as exc:
                claims.append(Claim("code_block", label, "fail", f"SyntaxError: {exc}", span, line))
            else:
                claims.append(Claim("code_block", label, "pass", "ast.parse succeeded", span, line))
        elif lang == "json":
            try:
                json.loads(body)
            except json.JSONDecodeError as exc:
                claims.append(Claim("code_block", label, "fail", str(exc), span, line))
            else:
                claims.append(
                    Claim("code_block", label, "pass", "json.loads succeeded", span, line)
                )
        elif lang in {"bash", "sh", "shell", "zsh"}:
            claims.append(_check_shell(body, label, span, line))
        else:
            claims.append(Claim("code_block", label, "skip",
                                f"no parser for {lang or 'plain'} blocks", span, line))
    return claims


def _check_shell(body: str, label: str, span: str, line: int) -> Claim:
    bash = shutil.which("bash")
    if bash is None:
        return Claim("code_block", label, "skip", "bash is not available", span, line)
    result = subprocess.run(
        [bash, "-n"], input=body, capture_output=True, text=True, timeout=10
    )
    if result.returncode == 0:
        return Claim("code_block", label, "pass", "bash -n accepted it", span, line)
    detail = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "syntax error"
    return Claim("code_block", label, "fail", detail, span, line)


# --- entry points ---------------------------------------------------------------


def audit_document(
    doc_path: Path, repo_root: Path, *, check_urls: bool = False
) -> list[Claim]:
    """Run every mechanical check against one document. Sorted, deduped."""
    text = doc_path.read_text(encoding="utf-8", errors="replace")
    facts = load_project_facts(repo_root)
    claims = [
        *check_paths(text, repo_root),
        *check_commands(text, facts),
        *check_flags(text, facts),
        *check_versions(text, facts),
        *check_links(text, doc_path, repo_root, check_urls=check_urls),
        *check_code_blocks(text),
    ]
    unique: dict[tuple[str, str, str], Claim] = {}
    for claim in claims:
        unique.setdefault((claim.kind, claim.claim, claim.evidence), claim)
    return sorted(unique.values(), key=lambda c: (c.line, c.kind, c.claim))


def claims_as_findings(claims: list[Claim], doc_path: Path, repo_root: Path) -> dict[str, Any]:
    """Wrap failed checks as a findings payload of pre-verified wrong_claims."""
    try:
        relative = doc_path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        relative = doc_path.name
    findings = []
    for index, claim in enumerate(c for c in claims if c.verdict == "fail"):
        findings.append(
            {
                "id": f"claims-{index + 1}",
                "type": "wrong_claim",
                "title": f"{claim.claim} — {claim.evidence}",
                "path": f"{relative}:{claim.line}",
                "quote": claim.span,
                "claim": claim.claim,
                "target": "readme",
            }
        )
    return {
        "version": 2,
        "target_kind": "docs",
        "target_ref": relative,
        "findings": findings,
    }


__all__ = [
    "Claim",
    "ProjectFacts",
    "audit_document",
    "check_code_blocks",
    "check_commands",
    "check_flags",
    "check_links",
    "check_paths",
    "check_versions",
    "claims_as_findings",
    "load_project_facts",
]
