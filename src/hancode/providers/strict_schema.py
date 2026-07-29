"""Pure JSON Schema projection for strict structured-output providers."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Mapping

from hancode.providers.schema_validator import check_schema, require_valid

SchemaPath = tuple[str, ...]


class StrictSchemaValidationError(ValueError):
    """Raised when a strict response cannot be normalized to the canonical schema."""


@dataclass(frozen=True, slots=True)
class StrictSchemaProjection:
    original_schema: Mapping[str, object]
    provider_schema: Mapping[str, object]
    promoted_optional_paths: frozenset[SchemaPath]
    synthetic_nullable_paths: frozenset[SchemaPath]

    @property
    def canonical_schema(self) -> Mapping[str, object]:
        """Compatibility alias for the original ToolSpec schema."""
        return self.original_schema

    @property
    def strict_schema(self) -> Mapping[str, object]:
        """Compatibility alias for the strict provider request schema."""
        return self.provider_schema

    @classmethod
    def project(cls, canonical_schema: Mapping[str, object]) -> StrictSchemaProjection:
        canonical = deepcopy(dict(canonical_schema))
        _check_schema(canonical)
        promoted: set[SchemaPath] = set()
        synthetic_nullable: set[SchemaPath] = set()
        strict = _project_schema(canonical, (), promoted, synthetic_nullable)
        _check_schema(strict)
        return cls(
            original_schema=canonical,
            provider_schema=strict,
            promoted_optional_paths=frozenset(promoted),
            synthetic_nullable_paths=frozenset(synthetic_nullable),
        )

    def normalize(self, payload: Mapping[str, object]) -> dict[str, object]:
        strict_payload = deepcopy(dict(payload))
        if not _is_valid(strict_payload, self.provider_schema):
            raise StrictSchemaValidationError("Strict provider response does not match schema.")
        _remove_synthetic_nulls(strict_payload, (), self.synthetic_nullable_paths)
        if not _is_valid(strict_payload, self.original_schema):
            raise StrictSchemaValidationError("Normalized provider response does not match schema.")
        return strict_payload


def _project_schema(
    schema: Mapping[str, object],
    data_path: SchemaPath,
    promoted: set[SchemaPath],
    synthetic_nullable: set[SchemaPath],
) -> dict[str, object]:
    projected = deepcopy(dict(schema))

    for keyword in ("allOf", "anyOf", "oneOf"):
        branches = projected.get(keyword)
        if isinstance(branches, list):
            projected[keyword] = [
                _project_schema(branch, data_path, promoted, synthetic_nullable)
                if isinstance(branch, Mapping)
                else branch
                for branch in branches
            ]

    if projected.get("type") == "array":
        items = projected.get("items")
        if isinstance(items, Mapping):
            projected["items"] = _project_schema(
                items, data_path + ("*",), promoted, synthetic_nullable
            )

    if projected.get("type") != "object":
        return projected

    raw_properties = projected.get("properties")
    properties = raw_properties if isinstance(raw_properties, Mapping) else {}
    original_required = projected.get("required")
    required = {
        item for item in original_required if isinstance(item, str)
    } if isinstance(original_required, list) else set()

    projected_properties: dict[str, object] = {}
    for name, value in properties.items():
        if not isinstance(name, str):
            continue
        property_path = data_path + (name,)
        property_schema = (
            _project_schema(value, property_path, promoted, synthetic_nullable)
            if isinstance(value, Mapping)
            else value
        )
        if name not in required:
            promoted.add(property_path)
            if isinstance(property_schema, Mapping) and not _allows_null(property_schema):
                property_schema = {"oneOf": [property_schema, {"type": "null"}]}
                synthetic_nullable.add(property_path)
        projected_properties[name] = property_schema

    projected["properties"] = projected_properties
    projected["required"] = list(projected_properties)
    projected["additionalProperties"] = False
    return projected


def _allows_null(schema: Mapping[str, object]) -> bool:
    return _is_valid(None, schema)


def _is_valid(instance: object, schema: Mapping[str, object]) -> bool:
    try:
        require_valid(instance, schema)
        return True
    except ValueError:
        return False


def _check_schema(schema: Mapping[str, object]) -> None:
    try:
        check_schema(schema)
    except ValueError as exc:
        raise StrictSchemaValidationError("Action schema is invalid.") from exc


def _remove_synthetic_nulls(
    value: object,
    data_path: SchemaPath,
    synthetic_nullable_paths: frozenset[SchemaPath],
) -> None:
    if isinstance(value, dict):
        for key in list(value):
            child_path = data_path + (key,)
            child = value[key]
            if child is None and child_path in synthetic_nullable_paths:
                del value[key]
                continue
            _remove_synthetic_nulls(child, child_path, synthetic_nullable_paths)
    elif isinstance(value, list):
        for child in value:
            _remove_synthetic_nulls(
                child, data_path + ("*",), synthetic_nullable_paths
            )
