"""Load, validate, and resolve scoring profiles.

One score, but the weights depend on the review type: a breaking bug about to
land in a PR is not worth the same as a stale sentence in a README, and a
reviewer's false claim is not worth the same as a library's. ``scoring.json``
holds one weight table per ``target_kind``; this module refuses to load a table
that could produce a score the documentation does not describe (negative,
fractional, or missing weights).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from loguru import logger

SCORING_VERSION = 2

DEFAULT_DEDUPE_KEYS = ("type", "file", "quote_fingerprint")
DEFAULT_CLUSTER_KEYS = ("type", "cluster")
DEFAULT_DOC_SUFFIXES = (".md", ".rst", ".txt", ".adoc", ".org")


class ScoringError(ValueError):
    """scoring.json is missing, malformed, or would produce an undefined score."""


@dataclass(frozen=True)
class DedupeConfig:
    """How findings are collapsed before scoring."""

    canonicalize_paths: bool = True
    cluster_cross_path: bool = True
    keys: tuple[str, ...] = DEFAULT_DEDUPE_KEYS
    cluster_keys: tuple[str, ...] = DEFAULT_CLUSTER_KEYS


@dataclass(frozen=True)
class DepthConfig:
    """Which review types are incomplete without a code pass."""

    requires_code_pass: frozenset[str] = frozenset({"repo", "pr", "branch", "skill"})
    doc_suffixes: frozenset[str] = frozenset(DEFAULT_DOC_SUFFIXES)

    def is_doc(self, path: str) -> bool:
        """True when ``path`` looks like prose rather than implementation."""
        lowered = path.lower()
        return any(lowered.endswith(suffix) for suffix in self.doc_suffixes)


@dataclass(frozen=True)
class Profile:
    """A resolved weight table for one review type."""

    name: str
    description: str
    weights: dict[str, int]
    type_notes: dict[str, str]

    def points(self, finding_type: str) -> int:
        """Points for ``finding_type`` under this profile."""
        return self.weights[finding_type]


@dataclass(frozen=True)
class Scoring:
    """A validated scoring.json."""

    version: int
    label: str
    types: dict[str, str]
    profiles: dict[str, Profile]
    default_profile: str
    evidence_required: tuple[str, ...]
    confidence_affects_score: bool
    dedupe: DedupeConfig
    depth: DepthConfig
    sha256: str

    def profile_for(self, target_kind: str | None) -> Profile:
        """Resolve the weight table for ``target_kind``, falling back to the default."""
        if target_kind in self.profiles:
            return self.profiles[target_kind]
        logger.warning(
            "no profile for target_kind {!r}; falling back to {!r}",
            target_kind,
            self.default_profile,
        )
        return self.profiles[self.default_profile]


def _require_mapping(document: Any, field: str) -> dict[str, Any]:
    value = document.get(field)
    if not isinstance(value, dict) or not value:
        raise ScoringError(f"scoring.{field} must be a non-empty object")
    return value


def _weight(profile_name: str, finding_type: str, raw: Any) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise ScoringError(
            f"scoring.profiles.{profile_name}.weights.{finding_type} must be an integer, "
            f"got {raw!r} — fractional weights are silently truncated and would make the "
            f"score irreproducible"
        )
    if raw < 0:
        raise ScoringError(
            f"scoring.profiles.{profile_name}.weights.{finding_type} must be >= 0, got {raw} — "
            f"the documented score starts at 0 and only increases"
        )
    return raw


def load_scoring(document: Any, sha256: str) -> Scoring:
    """Validate a parsed scoring.json and return a :class:`Scoring`.

    Raises:
        ScoringError: with a single actionable sentence describing the problem.
    """
    if not isinstance(document, dict):
        raise ScoringError("scoring.json must be a JSON object")
    if document.get("version") != SCORING_VERSION:
        raise ScoringError(
            f"scoring.version must be {SCORING_VERSION}; got {document.get('version')!r}"
        )

    types = _require_mapping(document, "types")
    for name, description in types.items():
        if not isinstance(description, str) or not description.strip():
            raise ScoringError(f"scoring.types.{name} must be a non-empty description string")

    raw_profiles = _require_mapping(document, "profiles")
    profiles: dict[str, Profile] = {}
    for name, raw in raw_profiles.items():
        if not isinstance(raw, dict):
            raise ScoringError(f"scoring.profiles.{name} must be an object")
        raw_weights = raw.get("weights")
        if not isinstance(raw_weights, dict):
            raise ScoringError(f"scoring.profiles.{name}.weights must be an object")
        missing = sorted(set(types) - set(raw_weights))
        if missing:
            raise ScoringError(f"scoring.profiles.{name}.weights is missing type(s): {missing}")
        extra = sorted(set(raw_weights) - set(types))
        if extra:
            raise ScoringError(
                f"scoring.profiles.{name}.weights has type(s) absent from scoring.types: {extra}"
            )
        weights = {t: _weight(name, t, raw_weights[t]) for t in sorted(raw_weights)}
        notes = raw.get("type_notes") or {}
        if not isinstance(notes, dict):
            raise ScoringError(f"scoring.profiles.{name}.type_notes must be an object")
        profiles[name] = Profile(
            name=name,
            description=str(raw.get("description", "")),
            weights=weights,
            type_notes={str(k): str(v) for k, v in notes.items()},
        )

    default_profile = document.get("default_profile")
    if default_profile not in profiles:
        raise ScoringError(
            f"scoring.default_profile must name a profile; got {default_profile!r}"
        )

    evidence_required = document.get("evidence_required") or ["path", "quote"]
    if not isinstance(evidence_required, list) or not all(
        isinstance(item, str) for item in evidence_required
    ):
        raise ScoringError("scoring.evidence_required must be a list of field names")
    if not {"path", "quote"} <= set(evidence_required):
        raise ScoringError(
            "scoring.evidence_required must include both 'path' and 'quote' — evidence is not "
            "optional in bs_score"
        )

    raw_dedupe = document.get("dedupe") or {}
    if not isinstance(raw_dedupe, dict):
        raise ScoringError("scoring.dedupe must be an object")
    allowed_keys = {"type", "file", "path", "quote_fingerprint", "target", "cluster"}
    keys = tuple(raw_dedupe.get("keys") or DEFAULT_DEDUPE_KEYS)
    cluster_keys = tuple(raw_dedupe.get("cluster_keys") or DEFAULT_CLUSTER_KEYS)
    for field, values in (("keys", keys), ("cluster_keys", cluster_keys)):
        unknown = sorted(set(values) - allowed_keys)
        if unknown:
            raise ScoringError(f"scoring.dedupe.{field} has unknown key(s): {unknown}")
    if "cluster" not in cluster_keys:
        raise ScoringError("scoring.dedupe.cluster_keys must include 'cluster'")

    dedupe = DedupeConfig(
        canonicalize_paths=bool(raw_dedupe.get("canonicalize_paths", True)),
        cluster_cross_path=bool(raw_dedupe.get("cluster_cross_path", True)),
        keys=keys,
        cluster_keys=cluster_keys,
    )

    raw_depth = document.get("depth") or {}
    if not isinstance(raw_depth, dict):
        raise ScoringError("scoring.depth must be an object")
    requires = raw_depth.get("requires_code_pass", ["repo", "pr", "branch", "skill"])
    if not isinstance(requires, list) or not all(isinstance(item, str) for item in requires):
        raise ScoringError("scoring.depth.requires_code_pass must be a list of review types")
    unknown_kinds = sorted(set(requires) - set(profiles))
    if unknown_kinds:
        raise ScoringError(
            f"scoring.depth.requires_code_pass names unknown review type(s): {unknown_kinds}"
        )
    suffixes = raw_depth.get("doc_suffixes") or list(DEFAULT_DOC_SUFFIXES)
    if not isinstance(suffixes, list) or not all(isinstance(item, str) for item in suffixes):
        raise ScoringError("scoring.depth.doc_suffixes must be a list of file suffixes")
    depth = DepthConfig(
        requires_code_pass=frozenset(requires),
        doc_suffixes=frozenset(suffix.lower() for suffix in suffixes),
    )

    logger.debug("loaded scoring v{} with profiles {}", SCORING_VERSION, sorted(profiles))
    return Scoring(
        version=SCORING_VERSION,
        label=str(document.get("label", "Bullshit Score")),
        types={str(k): str(v) for k, v in types.items()},
        profiles=profiles,
        default_profile=str(default_profile),
        evidence_required=tuple(evidence_required),
        confidence_affects_score=bool(document.get("confidence_affects_score", False)),
        dedupe=dedupe,
        depth=depth,
        sha256=sha256,
    )


__all__ = [
    "SCORING_VERSION",
    "DedupeConfig",
    "DepthConfig",
    "Profile",
    "Scoring",
    "ScoringError",
    "load_scoring",
]
