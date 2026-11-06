import pytest
from agent_mesh.schema_validator import StructuredOutputValidator


def test_schema_validator_success():
    schema = {
        "required": ["city", "temperature"],
        "properties": {
            "city": {"type": "string"},
            "temperature": {"type": "number"},
            "units": {"type": "string"},
        },
    }

    valid_payload = {"city": "Seattle", "temperature": 18.5, "units": "celsius"}
    is_valid, errors = StructuredOutputValidator.validate_object(valid_payload, schema)
    assert is_valid is True
    assert errors == []


def test_schema_validator_missing_and_wrong_types():
    schema = {
        "required": ["user_id", "email"],
        "properties": {
            "user_id": {"type": "integer"},
            "email": {"type": "string"},
        },
    }

    invalid_payload = {"user_id": "not_an_int"}  # missing email, user_id is str
    is_valid, errors = StructuredOutputValidator.validate_object(invalid_payload, schema)
    assert is_valid is False
    assert any("Missing required property: 'email'" in e for e in errors)
    assert any("Property 'user_id' must be integer" in e for e in errors)
