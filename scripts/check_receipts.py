#!/usr/bin/env python3
"""Verify that every committed receipt matches a fresh run of its findings file.

A receipt is the reproducibility claim: same findings, same tree, same weights,
same number. If a receipt and a fresh run disagree, one of them is lying.

Usage:
    python3 scripts/check_receipts.py           # check
    python3 scripts/check_receipts.py --write   # regenerate
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

INVOCATIONS: dict[str, list[str]] = {
    "valid": ["--repo-root", "examples/fixture-repo"],
    "review": [
        "--repo-root",
        "examples/fixture-repo",
        "--sources",
        "examples/fixture-review/review.json",
    ],
    "skill": ["--repo-root", "examples/fixture-repo"],
    "agent": ["--repo-root", "examples/fixture-repo"],
    "prompt": ["--repo-root", ".", "--sources", "examples/fixture-prompts"],
    "hallucinated": ["--repo-root", "examples/fixture-repo"],
    "self": ["--repo-root", "."],
}


def main(argv: list[str] | None = None) -> int:
    """Check (or rewrite) every ``examples/score.*.json``."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Regenerate instead of checking")
    args = parser.parse_args(argv)

    failures: list[str] = []
    for name, extra in INVOCATIONS.items():
        findings = REPO / "examples" / f"findings.{name}.json"
        receipt = REPO / "examples" / f"score.{name}.json"
        if not findings.is_file():
            failures.append(f"missing {findings.relative_to(REPO)}")
            continue
        result = subprocess.run(
            [sys.executable, "-m", "bs_score", str(findings.relative_to(REPO)), *extra, "-q"],
            capture_output=True,
            text=True,
            cwd=REPO,
        )
        if result.returncode != 0:
            failures.append(f"{name}: exit {result.returncode}\n{result.stderr}")
            continue
        if args.write:
            receipt.write_text(result.stdout, encoding="utf-8")
            continue
        if not receipt.is_file():
            failures.append(f"missing {receipt.relative_to(REPO)}")
        elif json.loads(receipt.read_text(encoding="utf-8")) != json.loads(result.stdout):
            failures.append(f"{receipt.relative_to(REPO)} is stale")

    for failure in failures:
        print(failure, file=sys.stderr)
    if failures:
        print("run: python3 scripts/check_receipts.py --write", file=sys.stderr)
        return 1
    print(f"{len(INVOCATIONS)} receipt(s) reproduce exactly")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
