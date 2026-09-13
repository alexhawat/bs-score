"""The bundled validator must agree with a real JSON Schema implementation.

``score.py`` claiming to validate against ``findings.schema.json`` is only true
if the two never disagree, so this checks them against each other on the worked
examples and on a set of deliberately broken payloads.
"""

from __future__ import annotations

import pytest
from conftest import load_example

from bs_score import schema_validate

jsonschema = pytest.importorskip("jsonschema")

BROKEN_PAYLOADS = [
    {"version": 3, "target_kind": "repo", "findings": []},
    {"version": 2, "target_kind": "nonsense", "findings": []},
    {"version": 2, "target_kind": "repo", "findings": {}},
    {"version": 2, "target_kind": "repo", "findings": [], "score": 12},
    {
        "version": 2,
        "target_kind": "repo",
        "findings": [{"id": "a", "type": "bug", "title": "t", "path": "", "quote": "q",
                      "target": "code"}],
    },
    {
        "version": 2,
        "target_kind": "repo",
        "findings": [{"id": "a", "type": "nit", "title": "t", "path": "p", "quote": "q",
                      "target": "code"}],
    },
    {
        "version": 2,
        "target_kind": "prompt",
        "findings": [{"id": "a", "type": "bug", "title": "t", "path": "p", "quote": "q",
                      "target": "prompt", "confidence": 2}],
    },
    {
        "version": 2,
        "target_kind": "repo",
        "findings": [{"id": "a", "type": "bug", "title": "t", "path": "p", "quote": "q",
                      "target": "code", "points": 9}],
    },
]

VALID_PAYLOADS = [load_example(name) for name in
                  ("valid", "review", "skill", "agent", "prompt", "docs", "i18n",
                   "hallucinated", "self")]


@pytest.mark.parametrize("payload", VALID_PAYLOADS + BROKEN_PAYLOADS)
def test_bundled_validator_agrees_with_jsonschema(payload, schema):
    reference = list(jsonschema.Draft202012Validator(schema).iter_errors(payload))
    ours = schema_validate.validate(payload, schema)
    assert bool(ours) == bool(reference), (
        f"disagreement: bundled={ours!r} jsonschema={[e.message for e in reference]!r}"
    )


def test_unsupported_keywords_fail_loudly_instead_of_under_validating(schema):
    with pytest.raises(schema_validate.SchemaSupportError):
        schema_validate.validate({}, {"anyOf": [{"type": "string"}]})


def test_every_schema_keyword_used_is_implemented(schema):
    """A new keyword in the schema must not silently go unchecked."""

    def keywords(node):
        if isinstance(node, dict):
            for key, value in node.items():
                yield key
                yield from keywords(value)
        elif isinstance(node, list):
            for item in node:
                yield from keywords(item)

    supported = {
        "$schema", "$id", "title", "description", "type", "enum", "const", "required",
        "properties", "additionalProperties", "items", "minLength", "minimum", "maximum",
    }
    used = {k for k in keywords(schema) if k in schema_validate._UNSUPPORTED}
    assert used == set(), f"schema uses unimplemented keyword(s): {sorted(used)}"
    top_level = set(schema) - supported
    assert top_level == set(), f"unrecognised schema keyword(s): {sorted(top_level)}"
