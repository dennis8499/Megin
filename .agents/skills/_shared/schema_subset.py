"""Dependency-free validation for the repository's documented JSON Schema subset."""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any


ANNOTATION_KEYWORDS = frozenset(
    {
        "$schema",
        "$id",
        "$comment",
        "title",
        "description",
        "default",
        "examples",
        "deprecated",
        "readOnly",
        "writeOnly",
    }
)
VALIDATION_KEYWORDS = frozenset(
    {
        "$defs",
        "$ref",
        "type",
        "const",
        "enum",
        "allOf",
        "anyOf",
        "oneOf",
        "if",
        "then",
        "else",
        "required",
        "properties",
        "patternProperties",
        "additionalProperties",
        "minProperties",
        "maxProperties",
        "items",
        "minItems",
        "maxItems",
        "uniqueItems",
        "minLength",
        "maxLength",
        "pattern",
        "minimum",
        "maximum",
        "format",
    }
)
SUPPORTED_KEYWORDS = ANNOTATION_KEYWORDS | VALIDATION_KEYWORDS
SUPPORTED_TYPES = frozenset({"object", "array", "string", "integer", "number", "boolean", "null"})
SUPPORTED_FORMATS = frozenset({"date-time"})
_RFC3339_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)


def _child_path(path: str, keyword: str) -> str:
    return f"{path}.{keyword}"


def _schema_mapping_children(value: Any, path: str, errors: list[str]) -> list[tuple[Any, str]]:
    if not isinstance(value, dict):
        errors.append(f"{path}: expected a schema mapping")
        return []
    return [(child, _child_path(path, str(name))) for name, child in value.items()]


def schema_keyword_errors(schema: Any) -> list[str]:
    """Return contract errors for unsupported or malformed schema rules.

    Keys inside ``properties``, ``patternProperties`` and ``$defs`` are map
    identifiers, so the walker checks their values as schemas without
    classifying their names as Schema keywords.
    """
    errors: list[str] = []

    def walk(rule: Any, path: str) -> None:
        if not isinstance(rule, dict):
            errors.append(f"{path}: boolean and non-object schemas are unsupported")
            return

        for keyword in rule:
            if keyword in SUPPORTED_KEYWORDS or keyword.startswith("x-"):
                continue
            errors.append(f"{path}: unsupported schema keyword '{keyword}'")

        raw_types = rule.get("type")
        if raw_types is not None:
            choices = [raw_types] if isinstance(raw_types, str) else raw_types
            if not isinstance(choices, list) or not choices or any(
                not isinstance(choice, str) or choice not in SUPPORTED_TYPES for choice in choices
            ):
                errors.append(f"{_child_path(path, 'type')}: unsupported schema type")

        if "format" in rule and rule["format"] not in SUPPORTED_FORMATS:
            errors.append(f"{_child_path(path, 'format')}: unsupported schema format")
        if "$ref" in rule and (
            not isinstance(rule["$ref"], str) or not rule["$ref"].startswith("#/")
        ):
            errors.append(f"{_child_path(path, '$ref')}: only local references are supported")
        if "pattern" in rule:
            try:
                re.compile(rule["pattern"])
            except (TypeError, re.error):
                errors.append(f"{_child_path(path, 'pattern')}: invalid regular expression")

        for keyword in ("properties", "patternProperties", "$defs"):
            if keyword in rule:
                mapping_path = _child_path(path, keyword)
                children = _schema_mapping_children(rule[keyword], mapping_path, errors)
                if keyword == "patternProperties" and isinstance(rule[keyword], dict):
                    for pattern in rule[keyword]:
                        try:
                            re.compile(pattern)
                        except (TypeError, re.error):
                            errors.append(
                                f"{_child_path(mapping_path, str(pattern))}: invalid regular expression"
                            )
                for child, child_path in children:
                    walk(child, child_path)

        for keyword in ("items", "if", "then", "else"):
            if keyword in rule:
                walk(rule[keyword], _child_path(path, keyword))

        additional = rule.get("additionalProperties")
        if isinstance(additional, dict):
            walk(additional, _child_path(path, "additionalProperties"))
        elif additional is not None and not isinstance(additional, bool):
            errors.append(
                f"{_child_path(path, 'additionalProperties')}: expected boolean or schema"
            )

        for keyword in ("allOf", "anyOf", "oneOf"):
            if keyword not in rule:
                continue
            children = rule[keyword]
            if not isinstance(children, list) or not children:
                errors.append(f"{_child_path(path, keyword)}: expected a non-empty schema list")
                continue
            for index, child in enumerate(children):
                walk(child, f"{_child_path(path, keyword)}[{index}]")

    walk(schema, "$")
    return errors


def _pointer(document: Any, ref: str) -> Any:
    if not ref.startswith("#/"):
        raise KeyError("unsupported non-local reference")
    node = document
    for raw in ref[2:].split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        node = node[int(token)] if isinstance(node, list) else node[token]
    return node


def _type_matches(value: Any, expected: str) -> bool:
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "null": value is None,
    }.get(expected, False)


def _valid_datetime(value: str) -> bool:
    if not _RFC3339_RE.fullmatch(value):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def validate_instance(
    instance: Any,
    schema: dict[str, Any],
    definition: str | None = None,
) -> list[str]:
    """Validate an instance without accepting schema rules we do not execute."""
    contract_errors = schema_keyword_errors(schema)
    if contract_errors:
        return contract_errors

    root = schema
    if definition is not None:
        try:
            node = schema["$defs"][definition]
        except (KeyError, TypeError):
            return [f"$.$defs.{definition}: schema definition is missing"]
    else:
        node = schema

    def check(value: Any, rule: dict[str, Any], location: str, refs: frozenset[str]) -> list[str]:
        found: list[str] = []
        if "$ref" in rule:
            ref = rule["$ref"]
            if ref in refs:
                return [f"{location}: recursive schema reference is unsupported"]
            try:
                target = _pointer(root, ref)
            except (KeyError, IndexError, TypeError):
                return [f"{location}: unresolved local schema reference"]
            found.extend(check(value, target, location, refs | {ref}))
            if len(rule) == 1:
                return found

        for child in rule.get("allOf", []):
            found.extend(check(value, child, location, refs))

        for keyword in ("anyOf", "oneOf"):
            if keyword not in rule:
                continue
            matches = sum(
                not check(value, child, location, refs) for child in rule[keyword]
            )
            if matches == 0 or (keyword == "oneOf" and matches != 1):
                found.append(f"{location}: {keyword} matched {matches} branches")

        if "if" in rule:
            condition_matches = not check(value, rule["if"], location, refs)
            branch = rule.get("then" if condition_matches else "else")
            if branch is not None:
                found.extend(check(value, branch, location, refs))

        if "const" in rule and value != rule["const"]:
            found.append(f"{location}: value does not match const")
        if "enum" in rule and value not in rule["enum"]:
            found.append(f"{location}: value is outside enum")

        expected_types = rule.get("type")
        if expected_types:
            choices = [expected_types] if isinstance(expected_types, str) else expected_types
            if not any(_type_matches(value, choice) for choice in choices):
                found.append(f"{location}: expected type {choices}, got {type(value).__name__}")
                return found

        if isinstance(value, dict):
            for name in rule.get("required", []):
                if name not in value:
                    found.append(f"{location}: missing required property {name}")
            properties = rule.get("properties", {})
            pattern_properties = rule.get("patternProperties", {})
            additional_rule = rule.get("additionalProperties")
            if additional_rule is False:
                for name in value.keys() - properties.keys():
                    if not any(re.search(pattern, name) for pattern in pattern_properties):
                        found.append(f"{location}: unexpected property {name}")
            for name, child in value.items():
                child_rules = []
                if name in properties:
                    child_rules.append(properties[name])
                child_rules.extend(
                    child_rule
                    for pattern, child_rule in pattern_properties.items()
                    if re.search(pattern, name)
                )
                if not child_rules and isinstance(additional_rule, dict):
                    child_rules.append(additional_rule)
                for child_rule in child_rules:
                    found.extend(check(child, child_rule, f"{location}.{name}", refs))
            if len(value) < rule.get("minProperties", 0):
                found.append(f"{location}: too few properties")
            if "maxProperties" in rule and len(value) > rule["maxProperties"]:
                found.append(f"{location}: too many properties")

        if isinstance(value, list):
            if len(value) < rule.get("minItems", 0):
                found.append(f"{location}: too few items")
            if "maxItems" in rule and len(value) > rule["maxItems"]:
                found.append(f"{location}: too many items")
            if rule.get("uniqueItems"):
                encoded = [
                    json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                    for item in value
                ]
                if len(encoded) != len(set(encoded)):
                    found.append(f"{location}: duplicate items")
            if "items" in rule:
                for index, child in enumerate(value):
                    found.extend(check(child, rule["items"], f"{location}[{index}]", refs))

        if isinstance(value, str):
            if len(value) < rule.get("minLength", 0):
                found.append(f"{location}: string is too short")
            if "maxLength" in rule and len(value) > rule["maxLength"]:
                found.append(f"{location}: string is too long")
            if "pattern" in rule and not re.search(rule["pattern"], value):
                found.append(f"{location}: does not match required pattern")
            if rule.get("format") == "date-time" and not _valid_datetime(value):
                found.append(f"{location}: invalid RFC 3339 date-time")

        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if "minimum" in rule and value < rule["minimum"]:
                found.append(f"{location}: below minimum {rule['minimum']}")
            if "maximum" in rule and value > rule["maximum"]:
                found.append(f"{location}: above maximum {rule['maximum']}")
        return found

    return check(instance, node, definition or "$", frozenset())
