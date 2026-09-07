#!/usr/bin/env python3
"""Central adapter for producer-owned validators and their versioned schemas."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

from _delivery_runtime import DeliveryError


class OwnerValidatorAdapter:
    """Load each owner implementation once without copying its validation rules."""

    def __init__(self, skills_root: Path | None = None) -> None:
        self.skills_root = skills_root or Path(__file__).resolve().parents[2]
        self._validators: dict[str, Any] = {}
        self._schemas: dict[str, dict[str, Any]] = {}

    def validator(self, owner: str) -> Any:
        cached = self._validators.get(owner)
        if cached is not None:
            return cached
        relative = {
            "planning": "technical-planning/scripts/validate_contracts.py",
            "bug": "bug-diagnosis/scripts/validate_contracts.py",
            "implementation": "implementation-execution/scripts/validate_contracts.py",
            "knowledge": "project-knowledge/scripts/knowledge_delivery.py",
        }.get(owner)
        if relative is None:
            raise DeliveryError(
                f"unknown validator owner: {owner}",
                code="CONTRACT_VALIDATOR_UNAVAILABLE",
            )
        module_path = self.skills_root / Path(*relative.split("/"))
        if str(module_path.parent) not in sys.path:
            sys.path.insert(0, str(module_path.parent))
        spec = importlib.util.spec_from_file_location(
            f"delivery_{owner}_contract_validator", module_path
        )
        if spec is None or spec.loader is None:
            raise DeliveryError(
                f"{owner} contract validator cannot be loaded",
                code="CONTRACT_VALIDATOR_UNAVAILABLE",
            )
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except (OSError, ImportError, SyntaxError) as exc:
            raise DeliveryError(
                f"{owner} contract validator cannot be loaded",
                code="CONTRACT_VALIDATOR_UNAVAILABLE",
            ) from exc
        self._validators[owner] = module
        return module

    def schema(self, name: str) -> dict[str, Any]:
        cached = self._schemas.get(name)
        if cached is not None:
            return cached
        relative = {
            "ready-plan/v1": "technical-planning/references/ready-plan.schema.json",
            "delivery-run/v1": "delivery-orchestrator/references/delivery-run.schema.json",
            "implementation-records": "implementation-execution/references/execution-records.schema.json",
        }.get(name)
        if relative is None:
            raise DeliveryError(
                f"unknown contract schema: {name}",
                code="CONTRACT_SCHEMA_UNAVAILABLE",
            )
        path = self.skills_root / Path(*relative.split("/"))
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise DeliveryError(
                f"{name} schema cannot be loaded",
                code="CONTRACT_SCHEMA_UNAVAILABLE",
            ) from exc
        if not isinstance(value, dict):
            raise DeliveryError(
                f"{name} schema is not an object",
                code="CONTRACT_SCHEMA_UNAVAILABLE",
            )
        self._schemas[name] = value
        return value


DEFAULT_VALIDATOR_ADAPTER = OwnerValidatorAdapter()
