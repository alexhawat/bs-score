"""The blast-radius sweep: how many places a defect really occurs."""

from __future__ import annotations

import pytest
from conftest import FIXTURE_REPO, REPO

from bs_score.locators import normalize_text
from bs_score.sweep import MAX_FILE_BYTES, TreeIndex, _normalize_with_lines


def test_joined_normalisation_equals_whole_file_normalisation():
    """Line mapping is only honest if the two forms are character-identical."""
    for path in (REPO / "README.md", REPO / "src" / "bs_score" / "report.py"):
        raw = path.read_text(encoding="utf-8")
        assert _normalize_with_lines(raw).text == normalize_text(raw), path


def test_reported_lines_are_the_real_lines():
    index = TreeIndex(FIXTURE_REPO)
    quote = "Run `demo install --fast` to set everything up."
    for occurrence in index.find(quote):
        line = (FIXTURE_REPO / occurrence.path).read_text(encoding="utf-8").splitlines()[
            occurrence.line - 1
        ]
        assert normalize_text(quote) in normalize_text(line)


def test_one_root_cause_is_found_in_every_file_that_carries_it():
    index = TreeIndex(FIXTURE_REPO)
    hits = index.find("Run `demo install --fast` to set everything up.")
    assert {hit.path for hit in hits} == {"README.md"}

    # The other two wordings live elsewhere; together they are the real radius.
    radius = {hit.path for wording in (
        "Run `demo install --fast` to set everything up.",
        "Start with `demo install`, then run the server.",
        "The installer subcommand handles dependencies for you.",
    ) for hit in index.find(wording)}
    assert radius == {"README.md", "docs/quickstart.md", "docs/install.md"}


def test_a_quote_that_is_nowhere_returns_nothing():
    assert TreeIndex(FIXTURE_REPO).find("this string is not in the fixture repo") == []


def test_empty_quote_returns_nothing():
    assert TreeIndex(FIXTURE_REPO).find("   ") == []


def test_index_skips_binary_and_oversized_files(tmp_path):
    (tmp_path / "ok.md").write_text("hello world", encoding="utf-8")
    (tmp_path / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    (tmp_path / "blob.dat").write_bytes(b"\x00\x01\x02" * 64)
    (tmp_path / "huge.md").write_text("x" * (MAX_FILE_BYTES + 1), encoding="utf-8")
    assert TreeIndex(tmp_path).paths() == ["ok.md"]


def test_index_walks_the_filesystem_when_there_is_no_git_checkout(tmp_path):
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "a.txt").write_text("needle", encoding="utf-8")
    index = TreeIndex(tmp_path)
    assert [hit.path for hit in index.find("needle")] == ["nested/a.txt"]


@pytest.mark.parametrize("skipped", [".git", "node_modules", "__pycache__", ".venv"])
def test_index_skips_noise_directories(tmp_path, skipped):
    (tmp_path / skipped).mkdir()
    (tmp_path / skipped / "a.md").write_text("needle", encoding="utf-8")
    assert TreeIndex(tmp_path).find("needle") == []


def test_listing_paths_does_not_read_file_contents(tmp_path):
    """The depth check only needs to know which paths exist.

    Normalising every file's contents to answer that was most of the cost of a
    `--no-scan` run, which is supposed to skip exactly that work.
    """
    (tmp_path / "a.py").write_text("print('hello')\n")
    (tmp_path / "b.md").write_text("# doc\n")
    tree = TreeIndex(tmp_path)

    assert tree.paths() == ["a.py", "b.md"]
    assert tree.file_count == 2
    assert tree._files is None, "paths() built the full content index"

    # The sweep still works, and sees the same files.
    assert [o.path for o in tree.find("print('hello')")] == ["a.py"]
    assert sorted(tree._files) == tree.paths()
