"""Command line front-end: ``bs-score findings.json``.

Exit codes:
    0  scored, and at or under ``--fail-over`` when given
    1  scored, and over ``--fail-over``
    2  unusable input (bad payload envelope, bad scoring file, bad --sources)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from loguru import logger

from . import __version__
from .baseline import BaselineError, load_baseline, write_baseline
from .claims import audit_document, claims_as_findings
from .evidence import DEFAULT_LINE_WINDOW, Verifier
from .logging_setup import configure
from .report import Options, PayloadError, build_report, render_markdown, sha256_of_document
from .resources import (
    SCHEMA_FILENAME,
    SCORING_FILENAME,
    DataFileError,
    load_json_file,
    locate,
)
from .sarif import render_sarif
from .scoring import ScoringError, load_scoring
from .sources import SourceError, load_sources
from .sweep import TreeIndex

EXIT_OK = 0
EXIT_OVER_THRESHOLD = 1
EXIT_INVALID = 2


def build_parser() -> argparse.ArgumentParser:
    """Return the argument parser."""
    parser = argparse.ArgumentParser(
        prog="bs-score",
        description=(
            "Score Bullshit Score findings deterministically. Quotes are verified "
            "against the artifacts they name before any points are assigned."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  bs-score findings.json                       # verify against the cwd, print JSON\n"
            "  bs-score findings.json --repo-root ../app    # audit another checkout\n"
            "  bs-score findings.json --sources prompts/    # prompt audit\n"
            "  bs-score findings.json --require-depth        # refuse a docs-only pass\n"
            "  bs-score findings.json --format md --fail-over 10\n"
        ),
    )
    parser.add_argument("findings", type=Path, help="Path to the findings JSON")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path("."),
        help="Tree that file locators resolve against (default: the current directory)",
    )
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="Skip evidence verification entirely. The report is stamped 'skipped'.",
    )
    parser.add_argument(
        "--sources",
        type=Path,
        action="append",
        default=[],
        metavar="PATH",
        help=(
            "Where non-file evidence lives: a directory of prompt files, a JSON/JSONL "
            "manifest of {id, text}, or a single text file. Repeatable."
        ),
    )
    parser.add_argument(
        "--require-evidence",
        action="store_true",
        help="Also reject findings whose evidence could not be checked at all",
    )
    parser.add_argument(
        "--strict-lines",
        action="store_true",
        help="Reject findings whose quote is real but is not near the stated line",
    )
    parser.add_argument(
        "--no-scan",
        action="store_true",
        help=(
            "Skip the blast-radius sweep. By default every verified quote is searched "
            "for across the tree, so the occurrence count is measured, not asserted."
        ),
    )
    parser.add_argument(
        "--require-depth",
        action="store_true",
        help=(
            "Fail when a review type that needs a code pass cannot prove one: no "
            "audit.files_read block, no implementation file in it, or a listed file "
            "that does not exist."
        ),
    )
    parser.add_argument(
        "--line-window",
        type=int,
        default=DEFAULT_LINE_WINDOW,
        metavar="N",
        help=f"Lines of slack allowed around a stated line number (default: {DEFAULT_LINE_WINDOW})",
    )
    parser.add_argument(
        "--fold-case",
        action="store_true",
        help="Match quotes case-insensitively (str.casefold). Off by default: a "
        "quote that changes case is a changed quote.",
    )
    parser.add_argument(
        "--fail-over",
        type=int,
        metavar="N",
        help="Exit 1 when the score exceeds N (for CI gates)",
    )
    parser.add_argument(
        "--format",
        choices=("json", "md", "sarif"),
        default="json",
        help="Report format on stdout (default: json; sarif for GitHub code scanning)",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        metavar="FILE",
        help="Suppress findings already in this baseline file; only new findings score",
    )
    parser.add_argument(
        "--write-baseline",
        type=Path,
        metavar="FILE",
        help="Write the kept findings as a baseline file for future --baseline runs",
    )
    parser.add_argument("-o", "--output", type=Path, help="Also write the report here")
    parser.add_argument(
        "--scoring",
        type=Path,
        help="Alternative scoring.json (requires --allow-custom-scoring)",
    )
    parser.add_argument(
        "--allow-custom-scoring",
        action="store_true",
        help="Acknowledge that --scoring produces a score the published weights do not define",
    )
    parser.add_argument("-v", "--verbose", action="count", default=0, help="Repeat for more logs")
    parser.add_argument("-q", "--quiet", action="store_true", help="Silence logging")
    parser.add_argument("--version", action="version", version=f"bs-score {__version__}")
    return parser


def build_claims_parser() -> argparse.ArgumentParser:
    """Return the parser for ``bs-score claims``."""
    parser = argparse.ArgumentParser(
        prog="bs-score claims",
        description=(
            "Mechanically check a document's checkable claims — paths, commands, "
            "flags, versions, links, fenced code — without an LLM. Output is JSON: "
            "one {kind, claim, verdict, evidence, line} per check. Fails are the "
            "claims the document gets provably wrong."
        ),
    )
    parser.add_argument("document", type=Path, help="The document to check (e.g. README.md)")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path("."),
        help="Tree that paths and packaging metadata resolve against (default: .)",
    )
    parser.add_argument(
        "--check-links",
        action="store_true",
        help="Also fetch http(s) link targets (off by default; needs network)",
    )
    parser.add_argument(
        "--emit-findings",
        action="store_true",
        help="Emit a findings payload (target_kind=docs) of the failed checks, "
        "ready to score with: bs-score findings.json --repo-root .",
    )
    parser.add_argument("-v", "--verbose", action="count", default=0, help="Repeat for more logs")
    parser.add_argument("-q", "--quiet", action="store_true", help="Silence logging")
    return parser


def claims_main(argv: list[str]) -> int:
    """Run ``bs-score claims`` and return a process exit code."""
    args = build_claims_parser().parse_args(argv)
    configure(args.verbose, quiet=args.quiet)
    logger.enable("bs_score")

    if not args.document.is_file():
        logger.error("not a file: {}", args.document)
        return EXIT_INVALID
    if not args.repo_root.is_dir():
        logger.error("--repo-root is not a directory: {}", args.repo_root)
        return EXIT_INVALID

    claims = audit_document(args.document, args.repo_root, check_urls=args.check_links)
    if args.emit_findings:
        payload = claims_as_findings(claims, args.document, args.repo_root)
    else:
        payload = [claim.as_dict() for claim in claims]
    sys.stdout.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    failed = sum(1 for claim in claims if claim.verdict == "fail")
    logger.info(
        "{} check(s): {} pass, {} fail, {} skip",
        len(claims),
        sum(1 for c in claims if c.verdict == "pass"),
        failed,
        sum(1 for c in claims if c.verdict == "skip"),
    )
    return EXIT_OVER_THRESHOLD if failed else EXIT_OK


def main(argv: list[str] | None = None) -> int:
    """Run the CLI and return a process exit code."""
    argv = list(sys.argv[1:]) if argv is None else list(argv)
    if argv and argv[0] == "claims":
        return claims_main(argv[1:])
    args = build_parser().parse_args(argv)
    configure(args.verbose, quiet=args.quiet)
    logger.enable("bs_score")

    if args.scoring and not args.allow_custom_scoring:
        logger.error(
            "--scoring changes the published weights; pass --allow-custom-scoring to confirm. "
            "The resulting number is not comparable to a default bs_score."
        )
        return EXIT_INVALID
    if args.line_window < 0:
        logger.error("--line-window must be >= 0")
        return EXIT_INVALID
    if args.require_evidence and args.no_verify:
        logger.error("--require-evidence contradicts --no-verify")
        return EXIT_INVALID
    if args.require_depth and args.no_verify:
        logger.error("--require-depth needs a --repo-root to check files_read against")
        return EXIT_INVALID

    try:
        scoring_path = args.scoring or locate(SCORING_FILENAME)
        schema_path = locate(SCHEMA_FILENAME)
        scoring_document, scoring_sha = load_json_file(scoring_path)
        schema, schema_sha = load_json_file(schema_path)
        payload, _ = load_json_file(args.findings)
        scoring = load_scoring(scoring_document, scoring_sha)
    except (DataFileError, ScoringError) as exc:
        logger.error(str(exc))
        return EXIT_INVALID

    if args.scoring:
        logger.warning("using custom weights from {} — this score is not comparable", scoring_path)

    repo_root: Path | None = None
    if not args.no_verify:
        repo_root = args.repo_root
        if not repo_root.is_dir():
            logger.error("--repo-root is not a directory: {}", repo_root)
            return EXIT_INVALID

    try:
        sources = load_sources(list(args.sources))
    except SourceError as exc:
        logger.error(str(exc))
        return EXIT_INVALID

    tree = (
        TreeIndex(repo_root, fold_case=args.fold_case) if repo_root is not None else None
    )
    verifier = Verifier(
        repo_root, sources, line_window=args.line_window, fold_case=args.fold_case
    )
    if not verifier.enabled:
        logger.warning(
            "evidence verification is off; the score reflects what the model asserted, "
            "not what it proved"
        )

    baseline_keys: frozenset[tuple[str, str, str]] = frozenset()
    if args.baseline:
        try:
            baseline_keys = load_baseline(args.baseline)
        except BaselineError as exc:
            logger.error(str(exc))
            return EXIT_INVALID

    options = Options(
        require_evidence=args.require_evidence,
        strict_lines=args.strict_lines,
        require_depth=args.require_depth,
        scan=not args.no_scan,
        fail_over=args.fail_over,
        fold_case=args.fold_case,
        baseline=baseline_keys,
    )
    try:
        report = build_report(
            payload,
            scoring,
            schema,
            schema_sha,
            verifier,
            options,
            findings_sha256=sha256_of_document(payload),
            tree=tree,
        )
    except PayloadError as exc:
        logger.error("findings payload is unusable: {}", exc)
        return EXIT_INVALID

    if args.write_baseline:
        write_baseline(args.write_baseline, report)

    if args.format == "md":
        text = render_markdown(report)
    elif args.format == "sarif":
        text = json.dumps(render_sarif(report), indent=2, ensure_ascii=False) + "\n"
    else:
        text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
        logger.info("wrote {}", args.output)
    sys.stdout.write(text if text.endswith("\n") else text + "\n")

    return EXIT_OVER_THRESHOLD if report["verdict"] == "fail" else EXIT_OK


def run() -> None:
    """Console-script entry point."""
    raise SystemExit(main())


__all__ = [
    "EXIT_INVALID",
    "EXIT_OK",
    "EXIT_OVER_THRESHOLD",
    "build_claims_parser",
    "build_parser",
    "claims_main",
    "main",
    "run",
]
