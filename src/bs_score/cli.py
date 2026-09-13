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
from .scoring import ScoringError, load_scoring
from .sources import SourceError, load_sources

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
        choices=("json", "md"),
        default="json",
        help="Report format on stdout (default: json)",
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


def main(argv: list[str] | None = None) -> int:
    """Run the CLI and return a process exit code."""
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

    verifier = Verifier(
        repo_root, sources, line_window=args.line_window, fold_case=args.fold_case
    )
    if not verifier.enabled:
        logger.warning(
            "evidence verification is off; the score reflects what the model asserted, "
            "not what it proved"
        )

    options = Options(
        require_evidence=args.require_evidence,
        strict_lines=args.strict_lines,
        fail_over=args.fail_over,
        fold_case=args.fold_case,
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
        )
    except PayloadError as exc:
        logger.error("findings payload is unusable: {}", exc)
        return EXIT_INVALID

    text = (
        render_markdown(report)
        if args.format == "md"
        else json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
        logger.info("wrote {}", args.output)
    sys.stdout.write(text if text.endswith("\n") else text + "\n")

    return EXIT_OVER_THRESHOLD if report["verdict"] == "fail" else EXIT_OK


def run() -> None:
    """Console-script entry point."""
    raise SystemExit(main())


__all__ = ["EXIT_INVALID", "EXIT_OK", "EXIT_OVER_THRESHOLD", "build_parser", "main", "run"]
