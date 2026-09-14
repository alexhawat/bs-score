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

from . import baseline as baseline_mod
from . import depth as depth_module
from . import locators, schema_validate
from .evidence import Verdict, Verifier
from .scoring import Scoring
from .sweep import TreeIndex

SCHEMA_INVALID = "schema_invalid"
MISSING_EVIDENCE = "missing_evidence"
UNVERIFIED_EVIDENCE = "unverified_evidence"
UNVERIFIABLE_EVIDENCE = "unverifiable_evidence"
DUPLICATE = "duplicate"
CROSS_PATH_DUPLICATE = "duplicate_across_paths"
SAME_CLUSTER = "same_root_cause"
NOT_VALID_BAND = "NOT_VALID"
NOT_VALID_VERDICT = "not_valid"


class PayloadError(ValueError):
    """The findings envelope is unusable, so no score can be produced."""


#: Score bands, display-only. The raw sum is the score; the band is a label for
#: humans reading a report in isolation. ``(upper_bound, label)``; the last
#: band is unbounded.
BANDS: tuple[tuple[int | None, str], ...] = (
    (0, "clean"),
    (5, "minor drift"),
    (15, "misleading"),
    (None, "bullshit"),
)


def score_band(score: int) -> str:
    """Display label for a score: 0 clean · 1–5 minor drift · 6–15 misleading · 16+ bullshit."""
    for upper, label in BANDS:
        if upper is None or score <= upper:
            return label
    raise AssertionError("unreachable")  # pragma: no cover


@dataclass(frozen=True)
class Options:
    """Knobs that change a report's meaning, recorded in the receipt."""

    require_evidence: bool = False
    strict_lines: bool = False
    require_depth: bool = False
    scan: bool = True
    fail_over: int | None = None
    fold_case: bool = False
    #: Dedupe keys of accepted findings, loaded from --baseline.
    baseline: frozenset[tuple[str, str, str]] = frozenset()


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


def _cluster_key(finding: dict[str, Any], scoring: Scoring) -> tuple[str, ...] | None:
    """Key that collapses differently-worded reports of one root cause."""
    if not finding.get("cluster"):
        return None
    return tuple(str(finding.get(key, "")) for key in scoring.dedupe.cluster_keys)


def build_report(
    payload: Any,
    scoring: Scoring,
    schema: dict[str, Any],
    schema_sha256: str,
    verifier: Verifier,
    options: Options | None = None,
    *,
    findings_sha256: str = "",
    tree: TreeIndex | None = None,
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
    baselined: list[dict[str, Any]] = []
    by_type: Counter[str] = Counter()
    count_by_type: Counter[str] = Counter()
    evidence_counts: Counter[str] = Counter()
    seen_ids: set[str] = set()
    # Merge targets are (bucket, index): a duplicate of a baselined finding is a
    # duplicate, not a second baselined finding. Registering only `kept` made the
    # same payload report `deduped 1` normally and `baselined 6` under a
    # baseline that covered it.
    seen_keys: dict[tuple[str, ...], tuple[str, int]] = {}
    seen_quotes: dict[tuple[str, str], tuple[str, int]] = {}
    seen_clusters: dict[tuple[str, ...], tuple[str, int]] = {}
    buckets = {"kept": kept, "baselined": baselined}
    total = 0

    def reject(index: int, finding: Any, reason: str, detail: str) -> None:
        entry: dict[str, Any] = {"index": index, "reason": reason, "detail": detail}
        if isinstance(finding, dict) and isinstance(finding.get("id"), str):
            entry["id"] = finding["id"]
        entry["finding"] = finding
        rejected.append(entry)
        logger.debug("rejected findings[{}] ({}): {}", index, reason, detail)

    def register(
        key: tuple[str, ...],
        quote_key: tuple[str, str],
        cluster_key: tuple[str, ...] | None,
        bucket: str,
        position: int,
    ) -> None:
        """Make this finding the merge target for later duplicates of it."""
        seen_keys[key] = (bucket, position)
        seen_quotes.setdefault(quote_key, (bucket, position))
        if cluster_key is not None:
            seen_clusters.setdefault(cluster_key, (bucket, position))

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
        fingerprint = locators.quote_fingerprint(
            str(finding["quote"]), fold_case=options.fold_case
        )
        key = _dedupe_key(finding, locator, fingerprint, scoring)

        cluster_key = _cluster_key(finding, scoring)

        target = seen_keys.get(key)
        reason = DUPLICATE
        if target is None and cluster_key is not None:
            target = seen_clusters.get(cluster_key)
            reason = SAME_CLUSTER
        if target is None and scoring.dedupe.cluster_cross_path:
            target = seen_quotes.get((str(finding["type"]), fingerprint))
            reason = CROSS_PATH_DUPLICATE
        if target is not None:
            bucket, target_index = target
            entry = buckets[bucket][target_index]
            entry.setdefault("merged", []).append(
                {"id": finding_id, "path": str(finding["path"])}
            )
            if bucket == "kept":
                # A cluster's blast radius is the union of its members' quotes,
                # so a root cause worded three ways is still counted everywhere
                # it lands. Baselined findings are not swept — they score nothing.
                entry.setdefault("_merged_quotes", []).append(str(finding["quote"]))
            deduped.append(
                {
                    "index": index,
                    "id": finding_id,
                    "reason": reason,
                    "merged_into": entry["id"],
                    "merged_into_bucket": bucket,
                    "finding": finding,
                }
            )
            continue

        quote_key = (str(finding["type"]), fingerprint)

        if baseline_mod.key_of(
            {"type": finding["type"], "canonical_file": locator.ref,
             "quote_fingerprint": fingerprint}
        ) in options.baseline:
            baselined.append(
                {
                    **finding,
                    "canonical_file": locator.ref,
                    "quote_fingerprint": fingerprint,
                    "evidence": verdict.as_dict(),
                }
            )
            register(key, quote_key, cluster_key, "baselined", len(baselined) - 1)
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
        register(key, quote_key, cluster_key, "kept", len(kept) - 1)

    if tree is not None and options.scan:
        _attach_blast_radius(kept, tree)
    else:
        for finding in kept:
            finding.pop("_merged_quotes", None)

    depth_report = depth_module.evaluate(payload, target_kind, scoring.depth, tree)

    findings_count = len(payload["findings"])
    # 0 means clean (no problem). Findings present with nothing kept/baselined
    # under an enabled verifier means nothing verified — NOT_VALID, not clean.
    not_valid = (
        verifier.enabled
        and findings_count > 0
        and len(kept) == 0
        and len(baselined) == 0
    )

    verdict_label = "pass"
    if not_valid:
        verdict_label = NOT_VALID_VERDICT
    elif options.fail_over is not None and total > options.fail_over:
        verdict_label = "fail"
    if options.require_depth and not depth_report.sufficient:
        verdict_label = "fail"

    report: dict[str, Any] = {
        "bs_score_version": __version__,
        "label": scoring.label,
        "score": None if not_valid else total,
        "band": NOT_VALID_BAND if not_valid else score_band(total),
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
        "baselined_count": len(baselined),
        "blast_radius": {
            "mode": "scanned" if (tree is not None and options.scan) else "not_scanned",
            "tree_files": tree.file_count if (tree is not None and options.scan) else None,
            "files_affected": sorted(
                {
                    occurrence["path"]
                    for finding in kept
                    for occurrence in finding.get("occurrences", [])
                }
            ),
        },
        "depth": depth_report.as_dict(),
        "evidence": {
            "mode": "verified" if verifier.enabled else "skipped",
            "repo_root": verifier.given_root.as_posix() if verifier.given_root else None,
            "sources": verifier.sources.ids,
            "line_window": verifier.line_window,
            "fold_case": options.fold_case,
            "require_evidence": options.require_evidence,
            "strict_lines": options.strict_lines,
            "require_depth": options.require_depth,
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
        "baselined": baselined,
    }
    logger.info(
        "{} ({} kept, {} rejected, {} deduped)",
        "NOT_VALID" if not_valid else f"score {total}",
        len(kept),
        len(rejected),
        len(deduped),
    )
    return report


def _attach_blast_radius(kept: list[dict[str, Any]], tree: TreeIndex) -> None:
    """Record every place each kept finding's quote appears in the tree.

    The score is unchanged — a defect is still worth its points once. What
    changes is that the count stops depending on how hard the model looked.
    """
    for finding in kept:
        quotes = [str(finding["quote"]), *finding.pop("_merged_quotes", [])]
        seen: set[tuple[str, int]] = set()
        occurrences: list[dict[str, Any]] = []
        for quote in quotes:
            for occurrence in tree.find(quote):
                key = (occurrence.path, occurrence.line)
                if key in seen:
                    continue
                seen.add(key)
                occurrences.append(occurrence.as_dict())
        occurrences.sort(key=lambda item: (item["path"], item["line"]))
        finding["occurrences"] = occurrences
        finding["occurrence_count"] = len(occurrences)
        files = {occurrence["path"] for occurrence in occurrences}
        finding["files_affected"] = len(files)
        if len(files) > 1:
            logger.info("{}: quote appears in {} files", finding["id"], len(files))


def sha256_of_document(document: Any) -> str:
    """Digest of a payload's canonical JSON form, for the receipt."""
    canonical = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def render_markdown(report: dict[str, Any]) -> str:
    """Render a report as a short Markdown summary an agent can paste verbatim."""
    evidence = report["evidence"]
    statuses = ", ".join(f"{k} {v}" for k, v in evidence["by_status"].items()) or "n/a"
    if report.get("verdict") == NOT_VALID_VERDICT:
        score_display = report["band"]
    else:
        score_display = report["score"]
    lines = [
        f"## {report['label']}: **{score_display}** ({report['band']})",
        "",
        f"- review type: `{report['target_kind']}` (profile `{report['profile']}`)",
        f"- target: `{report.get('target_ref') or 'unspecified'}`",
        f"- kept {report['kept_count']} · rejected {report['rejected_count']} "
        f"· deduped {report['deduped_count']} · baselined {report['baselined_count']}",
        f"- evidence: {evidence['mode']} ({statuses})",
        f"- depth: {_describe_depth(report['depth'])}",
        f"- blast radius: {_describe_blast_radius(report['blast_radius'])}",
        f"- scoring `{report['scoring_sha256'][:12]}` · schema `{report['schema_sha256'][:12]}`",
        "",
    ]
    if report["by_type"]:
        lines += ["| type | count | points |", "|------|------:|-------:|"]
        for name, points in report["by_type"].items():
            lines.append(f"| `{name}` | {report['count_by_type'][name]} | {points} |")
        lines.append("")
    if report["kept"]:
        lines += [
            "### Kept",
            "",
            "| type | points | path | files | title |",
            "|---|--:|---|--:|---|",
        ]
        for finding in report["kept"]:
            affected = finding.get("files_affected")
            files = str(affected) if affected is not None else "—"
            merged = len(finding.get("merged", []))
            title = finding["title"]
            if merged:
                title += f" _(merged {merged} report(s) of the same root cause)_"
            lines.append(
                f"| `{finding['type']}` | {finding['points']} | `{finding['path']}` "
                f"| {files} | {title} |"
            )
        lines.append("")
    if report["rejected"]:
        lines += ["### Rejected (not scored)", ""]
        for entry in report["rejected"]:
            label = entry.get("id", entry["index"])
            lines.append(f"- `{label}` — {entry['reason']}: {entry['detail']}")
        lines.append("")
    if report["baselined"]:
        lines += ["### Baselined (accepted, not scored)", ""]
        for finding in report["baselined"]:
            lines.append(f"- `{finding['id']}` — {finding['title']} (`{finding['path']}`)")
        lines.append("")
    return "\n".join(lines)


def _describe_depth(depth: dict[str, Any]) -> str:
    """One-line summary of the audit-depth check."""
    status = depth["status"]
    if status == depth_module.NOT_REQUIRED:
        return "not required for this review type"
    if status == depth_module.UNREPORTED:
        return "**unreported** — no `audit.files_read` block, so depth is unverifiable"
    detail = (
        f"{depth['files_read']} file(s) read, {depth['code_files_read']} of them implementation"
    )
    if depth.get("coverage") is not None:
        detail += f" ({depth['coverage']:.0%} of the tree)"
    if depth["missing_files"]:
        detail += f"; **{len(depth['missing_files'])} listed file(s) do not exist**"
    prefix = "**shallow**" if status == depth_module.SHALLOW else "deep"
    return f"{prefix} — {detail}"


def _describe_blast_radius(blast: dict[str, Any]) -> str:
    """One-line summary of how far the kept findings reach."""
    if blast["mode"] != "scanned":
        return "not scanned (`--no-scan`, or no `--repo-root`)"
    affected = len(blast["files_affected"])
    return f"{affected} file(s) affected across {blast['tree_files']} scanned"


__all__ = [
    "BANDS",
    "NOT_VALID_BAND",
    "NOT_VALID_VERDICT",
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
    "score_band",
    "sha256_of_document",
]
