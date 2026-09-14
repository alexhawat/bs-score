"""Render a bs_score report as SARIF 2.1.0 for GitHub code scanning.

Only *kept* findings become results: a rejected finding proved nothing, and a
baselined one was explicitly accepted. The rule id is the finding type, so the
weight profile stays visible in the rule metadata.
"""

from __future__ import annotations

from typing import Any

from . import __version__, locators

INFORMATION_URI = "https://github.com/alexhawat/bs-score"

# SARIF level per finding type: how loudly code scanning should present it.
_LEVELS = {
    "breaking_bug": "error",
    "security_issue": "error",
    "bug": "warning",
    "missing_feature": "warning",
    "wrong_claim": "note",
}


def _location(finding: dict[str, Any]) -> dict[str, Any]:
    locator = locators.parse(str(finding["path"]))
    artifact: dict[str, Any] = {"uri": locator.ref or str(finding["path"])}
    if locator.kind != locators.FILE:
        # prompt:/review: locators are not repo files; mark the URI scheme.
        artifact["uri"] = str(finding["path"])
        artifact["uriBaseId"] = "BS_SCORE_SOURCES"
    physical: dict[str, Any] = {"artifactLocation": artifact}
    if locator.line_start is not None:
        region: dict[str, Any] = {"startLine": locator.line_start}
        if locator.line_end:
            region["endLine"] = locator.line_end
        physical["region"] = region
    return {"physicalLocation": physical}


def render_sarif(report: dict[str, Any]) -> dict[str, Any]:
    """Convert a report document into a SARIF 2.1.0 log."""
    weights = report.get("weights", {})
    rules = [
        {
            "id": finding_type,
            "name": finding_type,
            "shortDescription": {"text": f"{finding_type} ({weights.get(finding_type, '?')} pts)"},
            "defaultConfiguration": {"level": _LEVELS.get(finding_type, "warning")},
        }
        for finding_type in sorted(report.get("count_by_type", {}))
    ]
    results = []
    for finding in report.get("kept", []):
        message = finding["title"]
        if finding.get("claim"):
            message = f"{message} — claim: {finding['claim']}"
        results.append(
            {
                "ruleId": finding["type"],
                "level": _LEVELS.get(finding["type"], "warning"),
                "message": {"text": message},
                "locations": [_location(finding)],
                "partialFingerprints": {
                    "bs_score/quote": finding.get("quote_fingerprint", ""),
                },
            }
        )
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "bs-score",
                        "version": __version__,
                        "informationUri": INFORMATION_URI,
                        "rules": rules,
                    }
                },
                "results": results,
                "properties": {
                    "bs_score": report["score"],
                    "band": report["band"],
                    "scoring_sha256": report["scoring_sha256"],
                },
            }
        ],
    }


__all__ = ["INFORMATION_URI", "render_sarif"]
