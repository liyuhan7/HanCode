from __future__ import annotations

from copy import deepcopy

from hancode.providers.strict_schema import StrictSchemaProjection


def test_strict_projection_preserves_native_null_and_removes_only_synthetic_null() -> None:
    canonical = {
        "type": "object",
        "properties": {
            "required_value": {"type": "string"},
            "optional_value": {"type": "string"},
            "native_nullable": {"oneOf": [{"type": "string"}, {"type": "null"}]},
            "entries": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"optional_value": {"type": "string"}},
                },
            },
        },
        "required": ["required_value"],
        "additionalProperties": False,
    }
    original = deepcopy(canonical)

    projection = StrictSchemaProjection.project(canonical)
    normalized = projection.normalize(
        {
            "required_value": "ok",
            "optional_value": None,
            "native_nullable": None,
            "entries": [{"optional_value": None}],
        }
    )

    assert canonical == original
    assert projection.strict_schema["required"] == [
        "required_value",
        "optional_value",
        "native_nullable",
        "entries",
    ]
    assert projection.provider_schema == projection.strict_schema
    assert projection.strict_schema["additionalProperties"] is False
    entries_schema = projection.strict_schema["properties"]["entries"]["oneOf"][0]
    assert entries_schema["items"]["additionalProperties"] is False
    assert normalized == {
        "required_value": "ok",
        "native_nullable": None,
        "entries": [{}],
    }
