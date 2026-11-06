"""JSON Schema and Structured Tool Call validation guardrail."""

import json
from typing import Any, Dict, List, Tuple


class SchemaValidationError(Exception):
    """Raised when an AI tool call or structured output violates strict schema types."""
    pass


class StructuredOutputValidator:
    """Type-safe validator for LLM structured outputs and function tool arguments."""

    @staticmethod
    def validate_object(data: Dict[str, Any], schema: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Validate a dictionary against a JSON schema-like specification."""
        errors: List[str] = []
        required_fields = schema.get("required", [])

        # Check required fields
        for req in required_fields:
            if req not in data:
                errors.append(f"Missing required property: '{req}'")

        properties = schema.get("properties", {})
        type_mapping = {
            "string": str,
            "integer": int,
            "number": (int, float),
            "boolean": bool,
            "array": list,
            "object": dict,
        }

        for prop_name, prop_spec in properties.items():
            if prop_name in data:
                val = data[prop_name]
                expected_type = prop_spec.get("type")
                if expected_type in type_mapping:
                    valid_types = type_mapping[expected_type]
                    # boolean is a subclass of int in Python, handle carefully
                    if expected_type in ("integer", "number") and isinstance(val, bool):
                        errors.append(f"Property '{prop_name}' must be {expected_type}, got boolean")
                    elif not isinstance(val, valid_types):
                        errors.append(f"Property '{prop_name}' must be {expected_type}, got {type(val).__name__}")

        return len(errors) == 0, errors
