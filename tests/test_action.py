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


def _extraction_snippets(script: str) -> dict[str, str]:
    """The ``python3 -c '...'`` one-liners the step runs to produce each output."""
    import re

    found = {}
    for name, code in re.findall(r'echo "(\w+)=\$\(python3 -c \'(.*?)\'\)"', script):
        found[name] = code
    return found


def test_a_not_valid_run_still_writes_every_output(tmp_path, capsys):
    """exit 3 must pass the gate, and `score` must not be the string "None".

    The gate was `[ "$code" -le 1 ] || exit`, written before NOT_VALID existed:
    a run that exited 3 wrote no outputs and no report.md, so the documented
    `if: always()` comment step read a file that was never created.
    """
    import subprocess
    import sys

    from conftest import EXAMPLES, FIXTURE_REPO

    from bs_score.cli import EXIT_NOT_VALID, main

    action = _load()
    step = next(s for s in action["runs"]["steps"] if s.get("id") == "score")
    script = step["run"]
    assert 'case "$code" in 0|1|3) ;; *) exit "$code" ;; esac' in script
    assert '[ "$code" -le 1 ]' not in script

    # A real NOT_VALID run, exactly as the step produces report.json.
    report = tmp_path / "report.json"
    code = main([
        str(EXAMPLES / "findings.hallucinated.json"),
        "--repo-root", str(FIXTURE_REPO), "-o", str(report), "-q",
    ])
    capsys.readouterr()
    assert code == EXIT_NOT_VALID
    assert report.is_file(), "the report must exist before the exit code is returned"

    # Run the step's own extraction one-liners against it.
    snippets = _extraction_snippets(script)
    assert set(snippets) == {"score", "band", "verdict"}
    values = {
        name: subprocess.run(
            [sys.executable, "-c", code], cwd=tmp_path, capture_output=True, text=True,
            check=True,
        ).stdout.strip()
        for name, code in snippets.items()
    }
    assert values == {"score": "", "band": "NOT_VALID", "verdict": "not_valid"}
    assert "None" not in values.values()
