"""Documentation claims this repo can check itself: links and flags must be real."""

from __future__ import annotations

import re

import pytest
from conftest import REPO

from bs_score.cli import build_claims_parser, build_parser

SKIP_DIRS = {
    ".venv", ".git", ".pytest_cache", ".ruff_cache", "dist", "build",
    "fixture-repo", "fixture-docs", "fixture-i18n", "tinycache", "greetcli",
}

MARKDOWN = sorted(
    path for path in REPO.rglob("*.md") if not SKIP_DIRS & set(path.parts)
)
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")


#: Links into this repository's own README, however they are spelled.
OWN_README = ("https://github.com/alexhawat/bs-score#", "https://github.com/alexhawat/bs-score/#")


def _anchors(path) -> set[str]:
    """GitHub-style slugs of every heading in a Markdown file, fences excluded."""
    from bs_score.claims import _slug

    slugs: set[str] = set()
    in_fence = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence and (match := re.match(r"^#{1,6}\s+(.*?)\s*#*\s*$", line)):
            slugs.add(_slug(match.group(1)))
    return slugs


@pytest.mark.parametrize("document", MARKDOWN, ids=lambda p: str(p.relative_to(REPO)))
def test_relative_links_resolve(document):
    """A dead link in a project about phantom references would be embarrassing.

    Anchors count: `README.md#install` pointing at a heading that does not exist
    is a phantom reference that lands the reader somewhere else in silence. The
    absolute form of a link into this repo's own README is checked the same way —
    fifteen generated files pointed at a `#install` section that never existed.
    """
    broken = []
    for target in LINK.findall(document.read_text(encoding="utf-8")):
        if target.startswith(OWN_README):
            resolved, anchor = REPO / "README.md", target.split("#", 1)[1]
        elif target.startswith(("http://", "https://", "mailto:")):
            continue
        else:
            path_part, _, anchor = target.partition("#")
            resolved = (document.parent / path_part).resolve() if path_part else document
            if not resolved.exists():
                broken.append(target)
                continue
        if anchor and resolved.suffix.lower() == ".md" and anchor not in _anchors(resolved):
            broken.append(target)
    assert broken == [], f"{document.relative_to(REPO)} links to: {broken}"


# A flag only belongs to bs-score if it is written on a line that invokes it.
BS_SCORE_LINE = re.compile(r"\b(?:bs-score|score\.py|bs_score\.cli)\b")
FLAG = re.compile(r"(?<![\w-])(--[a-z][a-z0-9-]+)")


@pytest.mark.parametrize("document", MARKDOWN, ids=lambda p: str(p.relative_to(REPO)))
def test_documented_flags_exist(document):
    """Every `--flag` printed next to a `bs-score` invocation must be a real option.

    Scoped to fenced code blocks, and within them to the part of a line that
    follows the command name — so flags belonging to other tools (`rg
    --fixed-strings`, `uvx --from`) are not swept up, and a flag invented for
    bs-score cannot hide next to one that is real.
    """
    known: set[str] = set()
    for action in [*build_parser()._actions, *build_claims_parser()._actions]:
        known.update(action.option_strings)

    unknown: set[str] = set()
    in_fence = False
    for line in document.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            continue  # prose mentions a flag; a code block invokes it
        match = BS_SCORE_LINE.search(line)
        if match is None:
            continue
        # Only what follows the command name: `uvx --from … bs-score …` puts a
        # uv flag on the same line, and it is not ours.
        unknown |= set(FLAG.findall(line[match.end():])) - known
    assert unknown == set(), (
        f"{document.relative_to(REPO)} documents unknown bs-score flag(s): {sorted(unknown)}"
    )


def test_checklists_exist_for_every_review_type(schema):
    for kind in schema["properties"]["target_kind"]["enum"]:
        name = "pr" if kind == "branch" else kind
        assert (REPO / "checklists" / f"{name}.md").is_file(), kind


# A ```console block whose first line invokes the scorer is a claim about output.
# The `uv run` / `python3 score.py` spellings run the same CLI, so they are the
# same claim: scoping this to a bare `bs-score` once let two fabricated demo
# blocks sit in the README with CI green.
CONSOLE_COMMAND = re.compile(r"^\$\s+(?:uv run\s+)?(?:bs-score|python3?\s+score\.py)\s+(.*)$")


def _console_blocks(text: str) -> list[tuple[str, list[str]]]:
    """Return ``(args, expected_lines)`` for every ```console block in a document."""
    blocks: list[tuple[str, list[str]]] = []
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        if lines[index].strip() == "```console":
            body: list[str] = []
            index += 1
            while index < len(lines) and lines[index].strip() != "```":
                body.append(lines[index])
                index += 1
            if body:
                match = CONSOLE_COMMAND.match(body[0].strip())
                if match:
                    expected = [line for line in body[1:] if line.strip()]
                    blocks.append((match.group(1), expected))
        index += 1
    return blocks


@pytest.mark.parametrize("document", MARKDOWN, ids=lambda p: str(p.relative_to(REPO)))
def test_console_blocks_show_output_the_command_really_produces(document, monkeypatch, capsys):
    """Run each documented `$ bs-score …` and check the lines under it are real.

    A README once pasted a depth line from one example and a blast-radius line
    from another, producing output no single run ever emitted. Quoting the tool's
    output is a claim like any other, so it gets verified like any other.
    """
    import shlex

    from bs_score.cli import main as cli_main

    blocks = _console_blocks(document.read_text(encoding="utf-8"))
    if not blocks:
        pytest.skip("no console blocks")

    monkeypatch.chdir(REPO)
    for args, expected in blocks:
        cli_main([*shlex.split(args), "-q"])
        actual = capsys.readouterr().out
        for line in expected:
            assert line.strip() in actual, (
                f"{document.relative_to(REPO)}: `bs-score {args}` never prints "
                f"{line.strip()!r}"
            )
