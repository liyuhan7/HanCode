"""Validate and normalize native Function Tool arguments."""

from __future__ import annotations

from typing import Mapping

from hancode.core.schema_validator import SchemaValidationError, validate_instance
from hancode.providers.tool_schema import StrictSchemaProjection


def normalize_provider_arguments(
    arguments: Mapping[str, object],
    request_schema: Mapping[str, object],
    projection: StrictSchemaProjection | None = None,
) -> dict[str, object]:
    if projection is not None:
        return projection.normalize(arguments)
    if validate_instance(arguments, request_schema):
        raise SchemaValidationError(())
    return dict(arguments)
