#!/usr/bin/env python3
"""Producer-owned ready-plan/v1 fixture shared by maintenance suites."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).with_name("validate_contracts.py")
SPEC = importlib.util.spec_from_file_location("ready_fixture_validator", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot import {SCRIPT_PATH}")
validator = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = validator
SPEC.loader.exec_module(validator)

HASH = "0" * 64
GIT_SHA = "a" * 40


def ready_example() -> dict:
    command_specs = [
        ("CMD-BDD-DISCOVERY-001", "bdd-discovery"),
        ("CMD-BDD-FOCUSED-001", "bdd-focused"),
        ("CMD-BDD-FULL-001", "bdd-full"),
        ("CMD-TDD-FOCUSED-001", "tdd-focused"),
        ("CMD-RELATED-001", "related"),
        ("CMD-BUILD-FULL-001", "build-full"),
        ("CMD-TEST-FULL-001", "test-full"),
    ]
    commands = [
        {
            "command_id": command_id,
            "purpose": purpose,
            "status": "Observed",
            "cwd": ".",
            "command": f"tool {purpose}",
            "environment_prerequisites": [],
            "timeout_seconds": 30,
            "network_policy": "forbidden",
            "allowed_writes": [],
            "external_side_effects": [],
            "success_criteria": ["exit 0"],
            "completeness_criteria": ["inventory complete"],
            "absence_evidence": [],
        }
        for command_id, purpose in command_specs
    ]
    contracts = [
        {"contract_id": "BDD-FWK-001", "kind": "bdd-framework", "source_refs": ["SRC-001"], "wp_refs": ["WP-001"]},
        {"contract_id": "BDD-001", "kind": "bdd-scenario", "source_refs": ["SRC-001"], "wp_refs": ["WP-001"]},
        {"contract_id": "TEST-001", "kind": "inner-test", "source_refs": ["SRC-001"], "wp_refs": ["WP-001"]},
        {"contract_id": "WP-001", "kind": "work-package", "source_refs": ["SRC-001"], "wp_refs": ["WP-001"]},
    ]
    contracts.extend(
        {"contract_id": command_id, "kind": "command", "source_refs": ["SRC-001"], "wp_refs": ["WP-001"]}
        for command_id, _ in command_specs
    )
    example = {
        "schema": "ready-plan/v1",
        "candidate": {"revision": "candidate-1", "payload_sha256": HASH},
        "approval": {"status": "Ready", "actor": "user", "confirmed_at": "2026-08-28T00:00:00Z", "evidence": "conversation:1"},
        "planning_baseline": {"repo_id": HASH, "head_sha": GIT_SHA, "status_sha256": HASH},
        "primary_plan": {"path": "docs/plans/example/plan.md", "sha256": HASH},
        "artifacts": [
            {"path": "docs/plans/example/plan.md", "role": "primary", "approval_status": "Ready", "sha256": HASH},
            {"path": "docs/plans/example/handoff.json", "role": "handoff", "approval_status": "Ready", "sha256": None},
        ],
        "sources": [
            {"source_id": "SRC-001", "kind": "spec", "location": "docs/spec.md", "revision": "1", "sha256": HASH, "plan_refs": ["REQ-001"], "wp_refs": ["WP-001"]}
        ],
        "contract_index": contracts,
        "commands": commands,
        "work_packages": [
            {
                "wp_id": "WP-001",
                "blocked_by": [],
                "contract_refs": [item["contract_id"] for item in contracts],
                "source_refs": ["SRC-001"],
                "command_refs": [item[0] for item in command_specs],
            }
        ],
        "revision_impact": {
            "revision": "candidate-1",
            "changes": [{"changed_ref": "BDD-001", "scope": "wp-local", "affected_wp_refs": ["WP-001"]}],
        },
    }
    example["candidate"]["payload_sha256"] = validator.ready_payload_sha256(example)
    return example
