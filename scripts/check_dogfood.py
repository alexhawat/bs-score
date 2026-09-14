#!/usr/bin/env python3
"""Run bs_score against itself and assert the properties that make it worth using.

These are the claims a reader of the README would want checked before trusting a
number: a fabricated audit is NOT_VALID (not a clean 0), a root cause is charged once but
counted everywhere, a docs-only pass cannot pass the depth gate, and the v1
defects stay fixed. Each one runs the real CLI.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def score(findings: str, *args: str) -> dict:
    """Run the CLI and return the parsed report."""
    result = subprocess.run(
        [sys.executable, "-m", "bs_score", findings, *args, "-q"],
        capture_output=True,
        text=True,
        cwd=REPO,
    )
    if result.returncode not in (0, 1, 3):
        raise SystemExit(f"{findings}: exit {result.returncode}\n{result.stderr}")
    return json.loads(result.stdout)


def exit_code(findings: str, *args: str) -> int:
    """Run the CLI and return only its exit code."""
    return subprocess.run(
        [sys.executable, "-m", "bs_score", findings, *args, "-q"],
        capture_output=True,
        text=True,
        cwd=REPO,
    ).returncode


def main() -> int:
    """Assert every dogfood property, reporting each one."""
    checks: list[tuple[str, bool, str]] = []

    fabricated = score(
        "examples/findings.hallucinated.json", "--repo-root", "examples/fixture-repo"
    )
    checks.append(
        (
            "a fabricated audit is NOT_VALID",
            fabricated["verdict"] == "not_valid"
            and fabricated["score"] is None
            and fabricated["kept_count"] == 0,
            (
                f"verdict={fabricated['verdict']} score={fabricated['score']} "
                f"kept={fabricated['kept_count']}"
            ),
        )
    )

    self_audit = score("examples/findings.self.json", "--repo-root", ".", "--no-scan")
    checks.append(
        (
            "the v1 defects stay fixed",
            self_audit["verdict"] == "not_valid"
            and self_audit["score"] is None
            and self_audit["rejected_count"] == 8,
            (
                f"verdict={self_audit['verdict']} score={self_audit['score']} "
                f"rejected={self_audit['rejected_count']}"
            ),
        )
    )

    blast = score("examples/findings.blast.json", "--repo-root", "examples/fixture-repo")
    cause = {finding["id"]: finding for finding in blast["kept"]}["install-readme"]
    checks.append(
        (
            "one root cause is charged once and counted everywhere",
            cause["points"] == 3 and cause["files_affected"] == 3 and len(cause["merged"]) == 2,
            f"points={cause['points']} files={cause['files_affected']} "
            f"merged={len(cause['merged'])}",
        )
    )
    checks.append(
        (
            "a deep audit passes --require-depth",
            exit_code(
                "examples/findings.blast.json",
                "--repo-root",
                "examples/fixture-repo",
                "--require-depth",
            )
            == 0,
            "",
        )
    )
    checks.append(
        (
            "a docs-only audit fails --require-depth",
            exit_code(
                "examples/findings.shallow.json",
                "--repo-root",
                "examples/fixture-repo",
                "--require-depth",
            )
            == 1,
            "",
        )
    )

    failed = 0
    for name, passed, detail in checks:
        mark = "ok  " if passed else "FAIL"
        suffix = f"  ({detail})" if detail else ""
        print(f"{mark} {name}{suffix}")
        failed += not passed
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
