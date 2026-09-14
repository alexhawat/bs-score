"""Check whether an audit actually went where it claims to have gone.

`SKILL.md` has always said a docs-only pass is incomplete for `repo`, `pr`,
`branch` and `skill`. Saying it is not enforcing it: an audit that read three
files and declared a repository reviewed produced exactly the same report as one
that read sixty. A payload can now carry `audit.files_read`, and this module
turns that into a measurement — files that do not exist, whether any code was
opened at all, and what fraction of the tree was covered.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from loguru import logger

from .locators import canonical_file
from .scoring import DepthConfig
from .sweep import TreeIndex

NOT_REQUIRED = "not_required"
UNREPORTED = "unreported"
SHALLOW = "shallow"
DEEP = "deep"

#: Statuses that mean the audit did not prove it read implementation.
INSUFFICIENT = frozenset({UNREPORTED, SHALLOW})


@dataclass(frozen=True)
class DepthReport:
    """What the audit block claims, checked against the tree."""

    status: str
    requires_code_pass: bool
    files_read: int = 0
    code_files_read: int = 0
    doc_files_read: int = 0
    missing_files: tuple[str, ...] = ()
    tree_files: int | None = None
    coverage: float | None = None
    notes: str = ""

    @property
    def sufficient(self) -> bool:
        """True when the audit met its review type's depth obligation."""
        return self.status not in INSUFFICIENT and not self.missing_files

    def as_dict(self) -> dict[str, Any]:
        """JSON-ready form for the report."""
        payload: dict[str, Any] = {
            "status": self.status,
            # `status` answers "did they read code?"; `sufficient` answers "does
            # this audit meet its obligation?". They differ when a listed file
            # does not exist, and --require-depth gates on the second — so it has
            # to be readable without re-deriving the rule.
            "sufficient": self.sufficient,
            "requires_code_pass": self.requires_code_pass,
            "files_read": self.files_read,
            "code_files_read": self.code_files_read,
            "doc_files_read": self.doc_files_read,
            "missing_files": list(self.missing_files),
        }
        if self.tree_files is not None:
            payload["tree_files"] = self.tree_files
        if self.coverage is not None:
            payload["coverage"] = self.coverage
        if self.notes:
            payload["notes"] = self.notes
        return payload


def evaluate(
    payload: dict[str, Any],
    target_kind: str,
    config: DepthConfig,
    tree: TreeIndex | None,
) -> DepthReport:
    """Measure the payload's ``audit`` block against ``tree``.

    Args:
        payload: The findings payload (its ``audit`` block is optional).
        target_kind: The review type, which decides whether code was required.
        config: Which review types need a code pass, and what counts as a doc.
        tree: The indexed tree, used to check the listed files exist. When it is
            None the files are counted but not checked.
    """
    requires = target_kind in config.requires_code_pass
    audit = payload.get("audit")

    if audit is None:
        status = UNREPORTED if requires else NOT_REQUIRED
        if requires:
            logger.warning(
                "no audit.files_read block: depth for a {!r} audit is unverifiable", target_kind
            )
        return DepthReport(status=status, requires_code_pass=requires)

    listed = [canonical_file(str(item)) for item in audit.get("files_read", [])]
    unique = sorted({item for item in listed if item})

    missing: tuple[str, ...] = ()
    tree_files: int | None = None
    coverage: float | None = None
    counted = unique
    if tree is not None:
        known = set(tree.paths())
        tree_files = len(known)
        missing = tuple(item for item in unique if item not in known)
        # A file that does not exist was not read, so it earns no depth credit.
        counted = [item for item in unique if item in known]
        if tree_files:
            coverage = round(len(counted) / tree_files, 4)

    docs = [item for item in counted if config.is_doc(item)]
    code = [item for item in counted if not config.is_doc(item)]

    if not requires:
        status = NOT_REQUIRED
    elif not code:
        status = SHALLOW
        logger.warning(
            "audit.files_read lists {} file(s) but no implementation: this is a docs-only pass",
            len(unique),
        )
    else:
        status = DEEP

    if missing:
        logger.warning("audit.files_read names {} file(s) that do not exist", len(missing))

    return DepthReport(
        status=status,
        requires_code_pass=requires,
        files_read=len(counted),
        code_files_read=len(code),
        doc_files_read=len(docs),
        missing_files=missing,
        tree_files=tree_files,
        coverage=coverage,
        notes=str(audit.get("notes", "")),
    )


__all__ = [
    "DEEP",
    "INSUFFICIENT",
    "NOT_REQUIRED",
    "SHALLOW",
    "UNREPORTED",
    "DepthReport",
    "evaluate",
]
