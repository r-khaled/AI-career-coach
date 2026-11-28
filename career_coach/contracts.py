"""Strict structural validation for version 1 application contracts.

Business invariants, authorization and provenance require separate validation.
"""
import json
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


class ContractError(ValueError):
    """A safe error that never includes submitted values or provider details."""


@lru_cache(maxsize=None)
def _validator(name):
    if not isinstance(name, str) or not name or any(
        character not in "abcdefghijklmnopqrstuvwxyz-" for character in name
    ):
        raise ContractError("Unknown contract")
    path = Path(__file__).parent / "schemas" / (name + ".json")
    if not path.is_file():
        raise ContractError("Unknown contract")
    with path.open(encoding="utf-8") as source:
        schema = json.load(source)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def validate(name, value):
    """Validate a JSON-compatible value, raising ContractError on failure."""
    if not _validator(name).is_valid(value):
        raise ContractError("Invalid contract value")
