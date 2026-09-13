#!/usr/bin/env python3
"""Deterministic bs_score scorer.

Reads an LLM findings JSON file and scoring.json. Never trusts model-computed
scores — rejects any payload `score`/`points` fields. Validates against
findings.schema.json (required fields + enums); rejects missing evidence;
dedupes on (type, path). The printed `score` comes only from this script.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
DEFAULT_SCORING = HERE / "scoring.json"
DEFAULT_SCHEMA = HERE / "findings.schema.json"

# Enums / required fields mirrored from findings.schema.json (stdlib — no jsonschema dep).
ALLOWED_TARGET_KINDS = frozenset({"repo", "pr", "branch", "review", "skill", "agent"})
ALLOWED_FINDING_TARGETS = frozenset(
    {"readme", "code", "diff", "review", "skill", "agent", "other"}
)
ALLOWED_FINDING_TYPES = frozenset(
    {"breaking_bug", "security_issue", "missing_feature", "wrong_claim", "bug"}
)


ALLOWED_PAYLOAD_KEYS = frozenset({"version", "target_kind", "target_ref", "findings"})
ALLOWED_FINDING_KEYS = frozenset(
    {"id", "type", "title", "path", "quote", "target", "claim", "confidence"}
)


def validate_payload_against_schema(payload: dict[str, Any]) -> None:
    """Reject payloads that violate findings.schema.json (required + enums).

    Raises ValueError with a short reason. Does not require the jsonschema package.
    The numeric score is computed only by this script — reject any model-supplied
    `score` (or other unknown top-level keys).
    """
    if "score" in payload:
        raise ValueError(
            "payload must not include 'score' — only score.py computes the score"
        )
    unknown = set(payload.keys()) - ALLOWED_PAYLOAD_KEYS
    if unknown:
        raise ValueError(f"payload has unknown keys: {sorted(unknown)}")
    if payload.get("version") != 1:
        raise ValueError("payload.version must be 1")
    kind = payload.get("target_kind")
    if kind not in ALLOWED_TARGET_KINDS:
        raise ValueError(
            f"payload.target_kind must be one of {sorted(ALLOWED_TARGET_KINDS)}; got {kind!r}"
        )
    raw = payload.get("findings")
    if not isinstance(raw, list):
        raise ValueError("payload.findings must be a list")
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"findings[{index}] must be an object")
        if "score" in item or "points" in item:
            raise ValueError(
                f"findings[{index}] must not include score/points — score.py assigns points"
            )
        bad_keys = set(item.keys()) - ALLOWED_FINDING_KEYS
        if bad_keys:
            raise ValueError(
                f"findings[{index}] has unknown keys: {sorted(bad_keys)}"
            )
        for key in ("id", "type", "title", "path", "quote", "target"):
            if key not in item:
                raise ValueError(f"findings[{index}] missing required field {key!r}")
        if item.get("type") not in ALLOWED_FINDING_TYPES:
            raise ValueError(
                f"findings[{index}].type invalid: {item.get('type')!r}"
            )
        if item.get("target") not in ALLOWED_FINDING_TARGETS:
            raise ValueError(
                f"findings[{index}].target invalid: {item.get('target')!r}"
            )



def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def normalize_path(path: str) -> str:
    return path.strip().replace("\\", "/")


def evidence_ok(finding: dict[str, Any], required: list[str]) -> bool:
    for key in required:
        value = finding.get(key)
        if not isinstance(value, str) or not value.strip():
            return False
    return True


def score_findings(
    payload: dict[str, Any],
    scoring: dict[str, Any],
) -> dict[str, Any]:
    validate_payload_against_schema(payload)
    types = scoring.get("types") or {}
    required = list(scoring.get("evidence_required") or ["path", "quote"])
    dedupe_keys = list(scoring.get("dedupe_keys") or ["type", "path"])

    raw = payload.get("findings")
    if not isinstance(raw, list):
        raise ValueError("payload.findings must be a list")

    kept: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    by_type: Counter[str] = Counter()
    total = 0

    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            rejected.append(
                {
                    "index": index,
                    "reason": "not_an_object",
                    "finding": item,
                }
            )
            continue

        finding_type = item.get("type")
        if finding_type not in types:
            rejected.append(
                {
                    "index": index,
                    "id": item.get("id"),
                    "reason": "unknown_type",
                    "finding": item,
                }
            )
            continue

        if not evidence_ok(item, required):
            rejected.append(
                {
                    "index": index,
                    "id": item.get("id"),
                    "reason": "missing_evidence",
                    "finding": item,
                }
            )
            continue

        path = normalize_path(str(item["path"]))
        key_values: list[str] = []
        for key in dedupe_keys:
            if key == "path":
                key_values.append(path)
            else:
                key_values.append(str(item.get(key, "")))
        dedupe_key = tuple(key_values)
        if dedupe_key in seen:
            deduped.append(
                {
                    "index": index,
                    "id": item.get("id"),
                    "reason": "duplicate_type_path",
                    "finding": item,
                }
            )
            continue
        seen.add(dedupe_key)

        points = int(types[finding_type]["points"])
        by_type[finding_type] += points
        total += points
        kept.append(
            {
                **item,
                "path": path,
                "points": points,
            }
        )

    return {
        "version": scoring.get("version", 1),
        "score": total,
        "by_type": dict(sorted(by_type.items())),
        "kept_count": len(kept),
        "rejected_count": len(rejected),
        "deduped_count": len(deduped),
        "kept": kept,
        "rejected": rejected,
        "deduped": deduped,
        "target_kind": payload.get("target_kind"),
        "target_ref": payload.get("target_ref"),
        "scoring_version": scoring.get("version"),
        "confidence_affects_score": bool(scoring.get("confidence_affects_score")),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Score Bullshit Score (bs_score) findings deterministically."
    )
    parser.add_argument(
        "findings",
        type=Path,
        help="Path to LLM findings JSON (version/target_kind/findings)",
    )
    parser.add_argument(
        "--scoring",
        type=Path,
        default=DEFAULT_SCORING,
        help=f"Path to scoring.json (default: {DEFAULT_SCORING})",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Optional path to write the score report JSON",
    )
    args = parser.parse_args(argv)

    payload = load_json(args.findings)
    scoring = load_json(args.scoring)
    if not isinstance(payload, dict) or not isinstance(scoring, dict):
        print("findings and scoring must be JSON objects", file=sys.stderr)
        return 2

    try:
        report = score_findings(payload, scoring)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
