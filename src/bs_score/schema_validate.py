"""A dependency-free validator for the subset of JSON Schema that findings.schema.json uses.

The point is that bs_score's validation *is* the published schema rather than a
hand-maintained copy of it: this walks the schema document itself, so the two can
never drift. ``tests/test_schema_parity.py`` cross-checks every fixture against the
real ``jsonschema`` library to keep that claim honest.

Supported keywords: type, enum, const, required, properties, additionalProperties
(false), items, minLength, minimum, maximum.
"""

from __future__ import annotations

from typing import Any

_TYPE_CHECKS = {
    "object": lambda value: isinstance(value, dict),
    "array": lambda value: isinstance(value, list),
    "string": lambda value: isinstance(value, str),
    # JSON has no bool/int distinction in Python's eyes; the schema does.
    "integer": lambda value: isinstance(value, int) and not isinstance(value, bool),
    "number": lambda value: isinstance(value, (int, float)) and not isinstance(value, bool),
    "boolean": lambda value: isinstance(value, bool),
    "null": lambda value: value is None,
}

_UNSUPPORTED = frozenset(
    {"allOf", "anyOf", "oneOf", "not", "$ref", "if", "then", "else", "patternProperties"}
)


class SchemaSupportError(RuntimeError):
    """The schema uses a keyword this validator does not implement."""


def _label(pointer: str) -> str:
    return pointer or "<root>"


def validate(instance: Any, schema: dict[str, Any], pointer: str = "") -> list[str]:
    """Return a list of human-readable validation errors (empty means valid).

    Args:
        instance: The value to check.
        schema: A schema object using the supported keyword subset.
        pointer: Dotted path used in error messages.

    Raises:
        SchemaSupportError: The schema uses an unimplemented keyword, which would
            silently under-validate. Failing loudly is the only safe option.
    """
    unsupported = _UNSUPPORTED & set(schema)
    if unsupported:
        raise SchemaSupportError(
            f"{_label(pointer)}: schema uses unsupported keyword(s) {sorted(unsupported)}"
        )

    errors: list[str] = []

    expected = schema.get("type")
    if expected is not None:
        expected_types = [expected] if isinstance(expected, str) else list(expected)
        if not any(_TYPE_CHECKS[name](instance) for name in expected_types):
            got = type(instance).__name__
            return [f"{_label(pointer)}: expected {'/'.join(expected_types)}, got {got}"]

    if "const" in schema and instance != schema["const"]:
        errors.append(f"{_label(pointer)}: must equal {schema['const']!r}")

    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{_label(pointer)}: {instance!r} is not one of {schema['enum']}")

    minimum_length = schema.get("minLength")
    if isinstance(instance, str) and minimum_length is not None and len(instance) < minimum_length:
        errors.append(
            f"{_label(pointer)}: must be at least {minimum_length} character(s), "
            f"got {len(instance)}"
        )

    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append(f"{_label(pointer)}: must be >= {schema['minimum']}, got {instance}")
        if "maximum" in schema and instance > schema["maximum"]:
            errors.append(f"{_label(pointer)}: must be <= {schema['maximum']}, got {instance}")

    if isinstance(instance, dict):
        errors.extend(_validate_object(instance, schema, pointer))
    elif isinstance(instance, list) and "items" in schema:
        for index, item in enumerate(instance):
            errors.extend(validate(item, schema["items"], f"{_label(pointer)}[{index}]"))

    return errors


def _validate_object(instance: dict[str, Any], schema: dict[str, Any], pointer: str) -> list[str]:
    errors: list[str] = []
    properties: dict[str, Any] = schema.get("properties", {})

    for key in schema.get("required", []):
        if key not in instance:
            errors.append(f"{_label(pointer)}: missing required field {key!r}")

    if schema.get("additionalProperties") is False:
        unknown = sorted(set(instance) - set(properties))
        if unknown:
            errors.append(f"{_label(pointer)}: unknown field(s) {unknown}")

    for key, value in instance.items():
        subschema = properties.get(key)
        if isinstance(subschema, dict):
            child = f"{pointer}.{key}" if pointer else key
            errors.extend(validate(value, subschema, child))

    return errors


def envelope_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Return ``schema`` with the findings *items* schema stripped out.

    Findings are validated one at a time so a single malformed finding is rejected
    on its own instead of discarding an otherwise usable audit.
    """
    trimmed = dict(schema)
    properties = dict(trimmed.get("properties", {}))
    findings = dict(properties.get("findings", {}))
    findings.pop("items", None)
    properties["findings"] = findings
    trimmed["properties"] = properties
    return trimmed


def finding_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Return the schema for a single element of ``findings``."""
    return schema["properties"]["findings"]["items"]


__all__ = ["SchemaSupportError", "envelope_schema", "finding_schema", "validate"]
