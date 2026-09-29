"""action.yml contract: the outputs must work in every --format.

Caught in review: the first version only set score/band when format=json,
so the README's own `format: md` example produced empty outputs.
"""

from __future__ import annotations

import yaml
from conftest import REPO

ACTION = REPO / "action.yml"


def _load():
    return yaml.safe_load(ACTION.read_text(encoding="utf-8"))


def test_action_is_a_valid_composite_action():
    action = _load()
    assert action["runs"]["using"] == "composite"
    assert {"score", "band", "report"} <= set(action["outputs"])


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
    assert len(guarded) == 3  # score, band, report
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
    assert '[ "$fmt_code" -le 1 ] || exit "$fmt_code"' in block
    assert '[ ! -f "report.$FORMAT" ]' in block
