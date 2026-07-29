from hancode.providers.schema_validator import validate_instance


def test_schema_violations_are_stable_and_do_not_echo_untrusted_values() -> None:
    schema = {
        "type": "object",
        "required": ["items"],
        "properties": {
            "items": {
                "type": "array",
                "items": {"type": "object", "properties": {"kind": {"enum": ["safe"]}}},
            }
        },
        "additionalProperties": False,
    }

    violations = validate_instance(
        {"items": [{"kind": "sk-secret-value"}], "secret_field": "never expose"},
        schema,
    )

    assert [(item.path, item.validator) for item in violations] == [
        ((), "additionalProperties"),
        (("items", 0, "kind"), "enum"),
    ]
    assert all("secret" not in item.message for item in violations)
