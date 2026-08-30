#!/usr/bin/env python3
"""Producer-owned ready-plan/v1 validation tests."""

from __future__ import annotations

import copy
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
from _ready_fixture import HASH, ready_example, validator

SKILLS_ROOT = SCRIPT_DIR.parents[1]


class ReadyPlanContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ready_schema = json.loads(
            (
                SKILLS_ROOT
                / "technical-planning/references/ready-plan.schema.json"
            ).read_text(encoding="utf-8")
        )

    def test_repository_contracts_pass(self) -> None:
        self.assertEqual([], validator.validate_all(SKILLS_ROOT))

    def test_ready_instance_and_cross_references(self) -> None:
        example = ready_example()
        self.assertEqual([], validator.validate_instance(example, self.ready_schema))
        self.assertEqual([], validator.validate_ready_cross_references(example))

        broken = copy.deepcopy(example)
        broken["sources"][0]["wp_refs"] = ["WP-MISSING"]
        errors = validator.validate_ready_cross_references(broken)
        self.assertTrue(any("unknown WP-MISSING" in error for error in errors), errors)

        broken_digest = copy.deepcopy(example)
        broken_digest["candidate"]["payload_sha256"] = HASH
        errors = validator.validate_ready_cross_references(broken_digest)
        self.assertTrue(any("payload digest" in error for error in errors), errors)

        broken_kind = copy.deepcopy(example)
        broken_kind["contract_index"][0]["kind"] = "command"
        errors = validator.validate_ready_cross_references(broken_kind)
        self.assertTrue(any("kind does not match" in error for error in errors), errors)

        local_time = copy.deepcopy(example)
        local_time["approval"]["confirmed_at"] = "2026-08-28T00:00:00"
        local_time["candidate"]["payload_sha256"] = validator.ready_payload_sha256(local_time)
        errors = validator.validate_ready_cross_references(local_time)
        self.assertTrue(any("has no timezone" in error for error in errors), errors)

        session_source = copy.deepcopy(example)
        session_source["sources"][0]["location"] = "conversation://request/1"
        session_source["candidate"]["payload_sha256"] = validator.ready_payload_sha256(session_source)
        errors = validator.validate_ready_cross_references(session_source)
        self.assertTrue(any("session-bound location" in error for error in errors), errors)

        materialized = copy.deepcopy(example)
        materialized["artifacts"].insert(
            1,
            {
                "path": "docs/plans/example/source-request.md",
                "role": "supporting",
                "approval_status": "Ready",
                "sha256": HASH,
            },
        )
        materialized["sources"][0]["location"] = "docs/plans/example/source-request.md"
        materialized["candidate"]["payload_sha256"] = validator.ready_payload_sha256(materialized)
        self.assertEqual([], validator.validate_ready_cross_references(materialized))

        candidate_form = copy.deepcopy(example)
        candidate_form["approval"] = {"status": "Candidate", "actor": None, "confirmed_at": None, "evidence": None}
        for artifact in candidate_form["artifacts"]:
            artifact["approval_status"] = "Candidate"
        self.assertEqual(example["candidate"]["payload_sha256"], validator.ready_payload_sha256(candidate_form))
        changed_contract = copy.deepcopy(example)
        changed_contract["commands"][0]["timeout_seconds"] += 1
        self.assertNotEqual(example["candidate"]["payload_sha256"], validator.ready_payload_sha256(changed_contract))

        escaped = copy.deepcopy(example)
        escaped["primary_plan"]["path"] = "../outside/plan.md"
        escaped["artifacts"][0]["path"] = "../outside/plan.md"
        escaped["sources"][0]["location"] = "../../source.md"
        escaped["commands"][0]["cwd"] = "../outside"
        escaped["commands"][0]["allowed_writes"] = [
            {"path": "../../escape/", "kind": "temporary", "cleanup": "remove after command"}
        ]
        escaped["candidate"]["payload_sha256"] = validator.ready_payload_sha256(escaped)
        schema_errors = validator.validate_instance(escaped, self.ready_schema)
        self.assertTrue(any("primary_plan.path" in error for error in schema_errors), schema_errors)
        self.assertTrue(any("commands[0].cwd" in error for error in schema_errors), schema_errors)
        errors = validator.validate_ready_cross_references(escaped)
        for fragment in ("artifact path", "source SRC-001 location", "cwd", "allowed write"):
            self.assertTrue(any(fragment in error for error in errors), errors)

        missing_command_mapping = copy.deepcopy(example)
        missing_command_mapping["work_packages"][0]["command_refs"].remove("CMD-BDD-DISCOVERY-001")
        missing_command_mapping["candidate"]["payload_sha256"] = validator.ready_payload_sha256(missing_command_mapping)
        errors = validator.validate_ready_cross_references(missing_command_mapping)
        self.assertTrue(any("command mapping is not symmetric" in error for error in errors), errors)

        ghost_command = copy.deepcopy(example)
        ghost_command["contract_index"].append(
            {"contract_id": "CMD-GHOST-001", "kind": "command", "source_refs": ["SRC-001"], "wp_refs": ["WP-001"]}
        )
        ghost_command["work_packages"][0]["contract_refs"].append("CMD-GHOST-001")
        ghost_command["candidate"]["payload_sha256"] = validator.ready_payload_sha256(ghost_command)
        errors = validator.validate_ready_cross_references(ghost_command)
        self.assertTrue(any("CMD-GHOST-001 has no command object" in error for error in errors), errors)
        self.assertTrue(any("CMD-GHOST-001 and WP-001 command mapping is not symmetric" in error for error in errors), errors)

        local_framework = copy.deepcopy(example)
        local_framework["revision_impact"]["changes"] = [
            {"changed_ref": "BDD-FWK-001", "scope": "wp-local", "affected_wp_refs": ["WP-001"]}
        ]
        local_framework["candidate"]["payload_sha256"] = validator.ready_payload_sha256(local_framework)
        errors = validator.validate_ready_cross_references(local_framework)
        self.assertTrue(any("BDD-FWK-001 requires global-baseline" in error for error in errors), errors)

        local_observed_baseline = copy.deepcopy(example)
        local_observed_baseline["revision_impact"]["changes"] = [
            {"changed_ref": "CMD-BDD-FULL-001", "scope": "wp-local", "affected_wp_refs": ["WP-001"]}
        ]
        local_observed_baseline["candidate"]["payload_sha256"] = validator.ready_payload_sha256(local_observed_baseline)
        errors = validator.validate_ready_cross_references(local_observed_baseline)
        self.assertTrue(any("CMD-BDD-FULL-001 requires global-baseline" in error for error in errors), errors)

    def test_ready_mutations_are_detected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            copied = Path(temp_dir) / "skills"
            shutil.copytree(
                SKILLS_ROOT / "technical-planning",
                copied / "technical-planning",
            )
            ready_path = copied / "technical-planning/references/ready-plan.schema.json"
            ready = json.loads(ready_path.read_text(encoding="utf-8"))
            ready["required"].remove("planning_baseline")
            ready["$defs"]["normalizedPath"]["pattern"] = "^[^\\\\]+$"
            ready_path.write_text(json.dumps(ready), encoding="utf-8", newline="\n")
            skill_path = copied / "technical-planning/SKILL.md"
            skill_path.write_text(
                skill_path.read_text(encoding="utf-8")
                + "\n[broken contract](references/missing-contract.md)\n"
                + "<!-- authority: ready-plan -->\n",
                encoding="utf-8",
                newline="\n",
            )
            errors = validator.validate_all(copied)
            self.assertTrue(any("schema bytes drifted" in error for error in errors), errors)
            self.assertTrue(any("planning_baseline" in error for error in errors), errors)
            self.assertTrue(
                any("normalized path pattern accepts unsafe value" in error for error in errors),
                errors,
            )
            self.assertTrue(any("broken local link" in error for error in errors), errors)
            self.assertTrue(any("authority 'ready-plan'" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main(verbosity=2)
