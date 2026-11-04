"""action.yml contract: the outputs must work in every --format.

Caught in review: the first version only set score/band when format=json,
so the README's own `format: md` example produced empty outputs.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys

import pytest
import yaml
from conftest import EXAMPLES, FIXTURE_REPO, REPO

ACTION = REPO / "action.yml"


def _load():
    return yaml.safe_load(ACTION.read_text(encoding="utf-8"))


def test_action_is_a_valid_composite_action():
    action = _load()
    assert action["runs"]["using"] == "composite"
    assert {"score", "band", "verdict", "report"} <= set(action["outputs"])


def test_score_and_band_outputs_are_set_regardless_of_format():
    """The step always writes report.json and reads the outputs from it."""
    action = _load()
    step = next(s for s in action["runs"]["steps"] if s.get("id") == "score")
    script = step["run"]
    assert "--format json -o report.json" in script
    for output in ("score", "band"):
        assert f'"{output}=$(python3' in script
    # No conditional may guard the output extraction lines.
    tail = script.split("--format json -o report.json", 1)[1]
    guarded = [ln for ln in tail.splitlines() if "GITHUB_OUTPUT" in ln]
    assert len(guarded) == 4  # score, band, verdict, report
    assert not any(ln.strip().startswith("if ") for ln in tail.splitlines() if "score=" in ln)


def test_readme_action_example_uses_declared_inputs():
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    action = _load()
    declared = set(action["inputs"])
    # Every `with:` key printed in the README workflow snippet must exist.
    import re

    snippet = re.search(r"uses: alexhawat/bs-score@main\n(.*?)\n```", readme, re.DOTALL)
    assert snippet, "README is missing the action example"
    used = set(re.findall(r"^\s{4,}(\w[\w-]*):", snippet.group(1), re.MULTILINE)) - {"with"}
    assert used <= declared, f"README uses undeclared input(s): {sorted(used - declared)}"


def test_the_scorer_ref_defaults_to_the_actions_own_ref():
    """`uses: alexhawat/bs-score@<sha>` must pin the scorer to that sha too.

    `ref` defaulted to `main`, so a pinned action still installed whatever main
    happened to be — the action was pinned and the code it ran was not.
    """
    action = _load()
    assert action["inputs"]["ref"]["default"] == ""
    step = next(s for s in action["runs"]["steps"] if s.get("id") == "score")
    assert step["env"]["ACTION_REF"] == "${{ github.action_ref }}"
    assert 'REF="${REF:-${ACTION_REF:-main}}"' in step["run"]


def test_the_scorer_is_installed_from_the_actions_own_repository():
    """The uvx URL hardcoded alexhawat/bs-score, so a fork's pinned action
    installed upstream's scorer instead of the fork's ref."""
    action = _load()
    step = next(s for s in action["runs"]["steps"] if s.get("id") == "score")
    assert step["env"]["ACTION_REPO"] == "${{ github.action_repository }}"
    installs = [ln for ln in step["run"].splitlines() if "uvx --from" in ln]
    assert len(installs) == 2
    for line in installs:
        assert "alexhawat/bs-score@" not in line
        assert "git+https://github.com/${ACTION_REPO}@${REF}" in line


def test_the_second_uvx_run_fails_the_step_when_it_fails():
    """The non-json format run's exit code was ignored and its report never
    checked: the step stayed green while report.$FORMAT did not exist."""
    action = _load()
    step = next(s for s in action["runs"]["steps"] if s.get("id") == "score")
    script = step["run"]
    block = script.split('if [ "$FORMAT" != json ]', 1)[1]
    assert "fmt_code=$?" in block
    assert 'case "$fmt_code" in 0|1|3) ;; *) exit "$fmt_code" ;; esac' in block
    assert '[ ! -f "report.$FORMAT" ]' in block


@pytest.fixture
def run_action(tmp_path):
    """Run the full step with GitHub's shell flags and the local, real CLI."""
    script = next(s["run"] for s in _load()["runs"]["steps"] if s.get("id") == "score")
    script_path = tmp_path / "step.sh"
    script_path.write_text(script, encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    # Replace only uvx's network installation; keep scoring and rendering real.
    uvx = bin_dir / "uvx"
    uvx.write_text(
        "#!/bin/bash\nshift 3\nexec " + shlex.quote(sys.executable)
        + " -c 'from bs_score.cli import run; run()' \"$@\"\n",
        encoding="utf-8",
    )
    uvx.chmod(0o755)
    output = tmp_path / "outputs"
    output.touch()

    def run(fixture="valid", report_format="json", fail_over=""):
        env = {
            **os.environ,
            "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"],
            "FINDINGS": str(EXAMPLES / f"findings.{fixture}.json"),
            "REPO_ROOT": str(FIXTURE_REPO),
            "SOURCES": "",
            "FAIL_OVER": fail_over,
            "BASELINE": "",
            "REQUIRE_DEPTH": "",
            "NO_SCAN": "",
            "FORMAT": report_format,
            "REF": "",
            "ACTION_REF": "",
            "ACTION_REPO": "",
            "GITHUB_OUTPUT": str(output),
        }
        result = subprocess.run(
            ["bash", "--noprofile", "--norc", "-eo", "pipefail", str(script_path)],
            cwd=tmp_path, env=env, capture_output=True, text=True, check=False,
        )
        values = dict(line.split("=", 1) for line in output.read_text().splitlines())
        return result, values

    return run


@pytest.mark.parametrize("report_format", ["json", "md", "sarif"])
@pytest.mark.parametrize(
    ("fixture", "fail_over", "exit_code", "score", "band", "verdict"),
    [
        ("valid", "", 0, "17", "bullshit", "pass"),
        ("valid", "0", 1, "17", "bullshit", "fail"),
        ("hallucinated", "", 3, "", "NOT_VALID", "not_valid"),
    ],
)
def test_action_writes_outputs_before_returning_verdict(
    run_action, tmp_path, report_format, fixture, fail_over, exit_code, score, band, verdict,
):
    result, values = run_action(fixture, report_format, fail_over)
    assert result.returncode == exit_code, result.stderr
    assert values == {
        "score": score, "band": band, "verdict": verdict, "report": f"report.{report_format}",
    }
    assert (tmp_path / "report.json").is_file()
    assert (tmp_path / f"report.{report_format}").stat().st_size > 0


@pytest.mark.parametrize(
    ("fixture", "report_format", "json_exists"),
    [("missing", "md", False), ("valid", "invalid-format", True)],
)
def test_action_stops_on_unusable_input(run_action, tmp_path, fixture, report_format, json_exists):
    result, values = run_action(fixture, report_format)
    assert result.returncode == 2, result.stderr
    assert values == {}
    assert (tmp_path / "report.json").exists() == json_exists
    assert not (tmp_path / f"report.{report_format}").exists()
