"""Shared, deterministic JSON Schema validation at the provider boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from jsonschema.exceptions import SchemaError  # type: ignore[import-untyped]

SchemaPath = tuple[str | int, ...]


@dataclass(frozen=True, slots=True)
class SchemaViolation:
    """A redacted JSON Schema violation safe to retain in traces or feedback."""

    path: SchemaPath
    validator: str
    message: str


class SchemaValidationError(ValueError):
    def __init__(self, violations: tuple[SchemaViolation, ...]) -> None:
        super().__init__("JSON value does not match the expected schema.")
        self.violations = violations


def validate_instance(
    instance: object, schema: Mapping[str, object]
) -> tuple[SchemaViolation, ...]:
    """Return stably ordered, non-sensitive validation metadata."""
    try:
        validator = Draft202012Validator(dict(schema))
    except SchemaError as exc:
        raise SchemaValidationError(()) from exc
    violations = tuple(_violation(error) for error in validator.iter_errors(instance))
    return tuple(sorted(violations, key=_violation_sort_key))


def require_valid(instance: object, schema: Mapping[str, object]) -> None:
    violations = validate_instance(instance, schema)
    if violations:
        raise SchemaValidationError(violations)


def check_schema(schema: Mapping[str, object]) -> None:
    try:
        Draft202012Validator.check_schema(dict(schema))
    except SchemaError as exc:
        raise SchemaValidationError(()) from exc


def _violation(error: object) -> SchemaViolation:
    path = tuple(
        part for part in getattr(error, "absolute_path", ()) if isinstance(part, (str, int))
    )
    validator = getattr(error, "validator", None)
    safe_validator = validator if isinstance(validator, str) else "schema"
    return SchemaViolation(
        path=path,
        validator=safe_validator,
        message=f"{safe_validator} validation failed.",
    )


def _violation_sort_key(violation: SchemaViolation) -> tuple[tuple[str, ...], str, str]:
    return (
        tuple(str(part) for part in violation.path),
        violation.validator,
        violation.message,
    )
