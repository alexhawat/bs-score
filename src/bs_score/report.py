"""Turn a findings payload into one score and one reproducible receipt.

Order of operations per finding: schema → evidence present → evidence verified →
dedupe → points. A finding that fails any earlier gate never reaches the later
ones, and a finding that fails is reported with the reason rather than silently
dropped. A single malformed finding is rejected on its own; only a malformed
*envelope* aborts the run.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from typing import Any

from loguru import logger

from . import locators, schema_validate
from .evidence import Verdict, Verifier
from .scoring import Scoring

SCHEMA_INVALID = "schema_invalid"
MISSING_EVIDENCE = "missing_evidence"
UNVERIFIED_EVIDENCE = "unverified_evidence"
UNVERIFIABLE_EVIDENCE = "unverifiable_evidence"
DUPLICATE = "duplicate"
CROSS_PATH_DUPLICATE = "duplicate_across_paths"


class PayloadError(ValueError):
    """The findings envelope is unusable, so no score can be produced."""


@dataclass(frozen=True)
class Options:
    """Knobs that change a report's meaning, recorded in the receipt."""

    require_evidence: bool = False
    strict_lines: bool = False
    fail_over: int | None = None


def _evidence_ok(finding: dict[str, Any], required: tuple[str, ...]) -> str | None:
    for key in required:
        value = finding.get(key)
        if not isinstance(value, str) or not value.strip():
            return key
    return None


def _dedupe_key(
    finding: dict[str, Any],
    locator: locators.Locator,
    fingerprint: str,
    scoring: Scoring,
) -> tuple[str, ...]:
    values: list[str] = []
    for key in scoring.dedupe.keys:
        if key == "file":
            values.append(
                locator.ref if scoring.dedupe.canonicalize_paths else str(finding["path"])
            )
        elif key == "path":
            values.append(str(finding.get("path", "")))
        elif key == "quote_fingerprint":
            values.append(fingerprint)
        else:
            values.append(str(finding.get(key, "")))
    return tuple(values)


def build_report(
    payload: Any,
    scoring: Scoring,
    schema: dict[str, Any],
    schema_sha256: str,
    verifier: Verifier,
    options: Options | None = None,
    *,
    findings_sha256: str = "",
) -> dict[str, Any]:
    """Score a payload and return the full report document.

    Raises:
        PayloadError: The envelope (version, target_kind, findings list) is invalid.
    """
    from . import __version__

    options = options or Options()

    if not isinstance(payload, dict):
        raise PayloadError("findings payload must be a JSON object")
    envelope_errors = schema_validate.validate(payload, schema_validate.envelope_schema(schema))
    if envelope_errors:
        raise PayloadError("; ".join(envelope_errors))

    finding_schema = schema_validate.finding_schema(schema)
    target_kind = str(payload["target_kind"])
    profile = scoring.profile_for(target_kind)
    logger.info(
        "scoring {} finding(s) with the {!r} profile", len(payload["findings"]), profile.name
    )

    kept: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    deduped: list[dict[str, Any]] = []
    by_type: Counter[str] = Counter()
    count_by_type: Counter[str] = Counter()
    evidence_counts: Counter[str] = Counter()
    seen_ids: set[str] = set()
    seen_keys: dict[tuple[str, ...], int] = {}
    seen_clusters: dict[tuple[str, str], int] = {}
    total = 0

    def reject(index: int, finding: Any, reason: str, detail: str) -> None:
        entry: dict[str, Any] = {"index": index, "reason": reason, "detail": detail}
        if isinstance(finding, dict) and isinstance(finding.get("id"), str):
            entry["id"] = finding["id"]
        entry["finding"] = finding
        rejected.append(entry)
        logger.debug("rejected findings[{}] ({}): {}", index, reason, detail)

    for index, finding in enumerate(payload["findings"]):
        errors = schema_validate.validate(finding, finding_schema, f"findings[{index}]")
        if errors:
            reject(index, finding, SCHEMA_INVALID, "; ".join(errors))
            continue

        finding_id = str(finding["id"])
        if finding_id in seen_ids:
            reject(index, finding, SCHEMA_INVALID, f"duplicate finding id {finding_id!r}")
            continue
        seen_ids.add(finding_id)

        missing = _evidence_ok(finding, scoring.evidence_required)
        if missing:
            reject(index, finding, MISSING_EVIDENCE, f"{missing} is blank")
            continue

        verdict: Verdict = verifier.verify(finding)
        evidence_counts[verdict.status] += 1
        if verdict.failing:
            reject(index, finding, UNVERIFIED_EVIDENCE, f"{verdict.status}: {verdict.detail}")
            continue
        if options.strict_lines and verdict.status == "verified_wrong_line":
            reject(index, finding, UNVERIFIED_EVIDENCE, f"{verdict.status}: {verdict.detail}")
            continue
        if options.require_evidence and not verdict.passing:
            reject(index, finding, UNVERIFIABLE_EVIDENCE, f"{verdict.status}: {verdict.detail}")
            continue

        locator = locators.parse(str(finding["path"]))
        fingerprint = locators.quote_fingerprint(str(finding["quote"]))
        key = _dedupe_key(finding, locator, fingerprint, scoring)

        target_index = seen_keys.get(key)
        reason = DUPLICATE
        if target_index is None and scoring.dedupe.cluster_cross_path:
            target_index = seen_clusters.get((str(finding["type"]), fingerprint))
            reason = CROSS_PATH_DUPLICATE
        if target_index is not None:
            occurrence = {"id": finding_id, "path": str(finding["path"])}
            kept[target_index].setdefault("occurrences", []).append(occurrence)
            deduped.append(
                {
                    "index": index,
                    "id": finding_id,
                    "reason": reason,
                    "merged_into": kept[target_index]["id"],
                    "finding": finding,
                }
            )
            continue

        points = profile.points(str(finding["type"]))
        by_type[str(finding["type"])] += points
        count_by_type[str(finding["type"])] += 1
        total += points
        kept.append(
            {
                **finding,
                "canonical_file": locator.ref,
                "quote_fingerprint": fingerprint,
                "evidence": verdict.as_dict(),
                "points": points,
            }
        )
        seen_keys[key] = len(kept) - 1
        seen_clusters.setdefault((str(finding["type"]), fingerprint), len(kept) - 1)

    verdict_label = "pass"
    if options.fail_over is not None and total > options.fail_over:
        verdict_label = "fail"

    report: dict[str, Any] = {
        "bs_score_version": __version__,
        "label": scoring.label,
        "score": total,
        "verdict": verdict_label,
        "fail_over": options.fail_over,
        "target_kind": target_kind,
        "target_ref": payload.get("target_ref"),
        "profile": profile.name,
        "profile_description": profile.description,
        "weights": dict(sorted(profile.weights.items())),
        "by_type": dict(sorted(by_type.items())),
        "count_by_type": dict(sorted(count_by_type.items())),
        "kept_count": len(kept),
        "rejected_count": len(rejected),
        "deduped_count": len(deduped),
        "evidence": {
            "mode": "verified" if verifier.enabled else "skipped",
            "repo_root": verifier.given_root.as_posix() if verifier.given_root else None,
            "sources": verifier.sources.ids,
            "line_window": verifier.line_window,
            "require_evidence": options.require_evidence,
            "strict_lines": options.strict_lines,
            "by_status": dict(sorted(evidence_counts.items())),
        },
        "scoring_version": scoring.version,
        "scoring_sha256": scoring.sha256,
        "schema_sha256": schema_sha256,
        "findings_sha256": findings_sha256,
        "confidence_affects_score": scoring.confidence_affects_score,
        "kept": kept,
        "rejected": rejected,
        "deduped": deduped,
    }
    logger.info(
        "score {} ({} kept, {} rejected, {} deduped)",
        total,
        len(kept),
        len(rejected),
        len(deduped),
    )
    return report


def sha256_of_document(document: Any) -> str:
    """Digest of a payload's canonical JSON form, for the receipt."""
    canonical = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def render_markdown(report: dict[str, Any]) -> str:
    """Render a report as a short Markdown summary an agent can paste verbatim."""
    lines = [
        f"## {report['label']}: **{report['score']}**",
        "",
        f"- review type: `{report['target_kind']}` (profile `{report['profile']}`)",
        f"- target: `{report.get('target_ref') or 'unspecified'}`",
        f"- kept {report['kept_count']} · rejected {report['rejected_count']} "
        f"· deduped {report['deduped_count']}",
        f"- evidence: {report['evidence']['mode']} "
        f"({', '.join(f'{k} {v}' for k, v in report['evidence']['by_status'].items()) or 'n/a'})",
        f"- scoring `{report['scoring_sha256'][:12]}` · schema `{report['schema_sha256'][:12]}`",
        "",
    ]
    if report["by_type"]:
        lines += ["| type | count | points |", "|------|------:|-------:|"]
        for name, points in report["by_type"].items():
            lines.append(f"| `{name}` | {report['count_by_type'][name]} | {points} |")
        lines.append("")
    if report["kept"]:
        lines += ["### Kept", "", "| type | points | path | title |", "|---|--:|---|---|"]
        for finding in report["kept"]:
            occurrences = len(finding.get("occurrences", []))
            suffix = f" (+{occurrences} more)" if occurrences else ""
            lines.append(
                f"| `{finding['type']}` | {finding['points']} | `{finding['path']}`{suffix} "
                f"| {finding['title']} |"
            )
        lines.append("")
    if report["rejected"]:
        lines += ["### Rejected (not scored)", ""]
        for entry in report["rejected"]:
            label = entry.get("id", entry["index"])
            lines.append(f"- `{label}` — {entry['reason']}: {entry['detail']}")
        lines.append("")
    return "\n".join(lines)


__all__ = [
    "CROSS_PATH_DUPLICATE",
    "DUPLICATE",
    "MISSING_EVIDENCE",
    "Options",
    "PayloadError",
    "SCHEMA_INVALID",
    "UNVERIFIABLE_EVIDENCE",
    "UNVERIFIED_EVIDENCE",
    "build_report",
    "render_markdown",
    "sha256_of_document",
]
