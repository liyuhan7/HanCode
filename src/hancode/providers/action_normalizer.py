"""Normalize strict-provider arguments back to their original tool schema."""

from __future__ import annotations

from typing import Mapping

from hancode.providers.tool_schema import StrictSchemaProjection


def normalize_provider_arguments(
    projection: StrictSchemaProjection, arguments: Mapping[str, object]
) -> dict[str, object]:
    return projection.normalize(arguments)
