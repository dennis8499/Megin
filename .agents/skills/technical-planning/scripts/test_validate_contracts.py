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


def bug_ready_example(target: str = "verified") -> dict:
    example = ready_example()
    example["sources"].append(
        {
            "source_id": "SRC-BUG-001",
            "kind": "bug",
            "location": "docs/bugs/bug-sample-failure/assessment-1.json",
            "revision": "1",
            "sha256": "b" * 64,
            "plan_refs": ["BUG-001", "BDD-001", "TEST-001"],
            "wp_refs": ["WP-001"],
        }
    )
    example["work_packages"][0]["source_refs"].append("SRC-BUG-001")
    for contract in example["contract_index"]:
        if contract["contract_id"] in {"BDD-001", "TEST-001", "WP-001"}:
            contract["source_refs"].append("SRC-BUG-001")
    command = {
        "command_id": "CMD-BUG-REPRO-001",
        "purpose": "bug-reproduction",
        "status": "Observed",
        "cwd": ".",
        "command": "tool reproduce-bug",
        "environment_prerequisites": [],
        "timeout_seconds": 30,
        "network_policy": "forbidden",
        "allowed_writes": [],
        "external_side_effects": [],
        "success_criteria": ["command distinguishes symptom present from absent"],
        "completeness_criteria": ["original symptom oracle executed"],
        "absence_evidence": [],
    }
    example["commands"].append(command)
    example["contract_index"].append(
        {
            "contract_id": "CMD-BUG-REPRO-001",
            "kind": "command",
            "source_refs": ["SRC-001", "SRC-BUG-001"],
            "wp_refs": ["WP-001"],
        }
    )
    example["work_packages"][0]["contract_refs"].append("CMD-BUG-REPRO-001")
    example["work_packages"][0]["command_refs"].append("CMD-BUG-REPRO-001")
    example["bug_context"] = {
        "bug_id": "bug-sample-failure",
        "assessment": {
            "path": "docs/bugs/bug-sample-failure/assessment-1.json",
            "sha256": "b" * 64,
            "markdown_path": "docs/bugs/bug-sample-failure/assessment-1.md",
            "markdown_sha256": "c" * 64,
        },
        "reproduction_status": "reproduced" if target == "verified" else "not-reproduced",
        "root_cause_status": "confirmed" if target == "verified" else "hypothesized",
        "root_cause_confidence": "high" if target == "verified" else "low",
        "verification_target": target,
        "original_reproduction_command_ref": "CMD-BUG-REPRO-001" if target == "verified" else None,
        "regression_bdd_refs": ["BDD-001"],
        "regression_test_refs": ["TEST-001"],
        "partial_safeguards": {
            "reason": None if target == "verified" else "The original symptom cannot be reproduced reliably.",
            "proxy_bdd_refs": [] if target == "verified" else ["BDD-001"],
            "proxy_test_refs": [] if target == "verified" else ["TEST-001"],
            "residual_risks": [] if target == "verified" else ["Original symptom may persist outside the proxy seam."],
            "follow_up": [] if target == "verified" else ["Run the original journey manually in staging."],
        },
    }
    example["candidate"]["payload_sha256"] = validator.ready_payload_sha256(example)
    return example


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

    def test_each_source_owns_direct_bdd_test_and_shared_wp_coverage(self) -> None:
        borrowed = copy.deepcopy(ready_example())
        borrowed["sources"].append(
            {
                "source_id": "SRC-002",
                "kind": "spec",
                "location": "docs/second-spec.md",
                "revision": "1",
                "sha256": HASH,
                "plan_refs": ["REQ-002"],
                "wp_refs": ["WP-001"],
            }
        )
        borrowed["work_packages"][0]["source_refs"].append("SRC-002")
        for contract in borrowed["contract_index"]:
            if contract["kind"] in {"bdd-scenario", "inner-test"}:
                contract["source_refs"] = ["SRC-002"]
        borrowed["candidate"]["payload_sha256"] = validator.ready_payload_sha256(borrowed)
        errors = validator.validate_ready_cross_references(borrowed)
        self.assertTrue(
            any("source SRC-001 has no direct bdd-scenario contract sharing a WP" in error for error in errors),
            errors,
        )
        self.assertTrue(
            any("source SRC-001 has no direct inner-test contract sharing a WP" in error for error in errors),
            errors,
        )

        disjoint = copy.deepcopy(ready_example())
        disjoint["contract_index"].append(
            {
                "contract_id": "WP-002",
                "kind": "work-package",
                "source_refs": [],
                "wp_refs": ["WP-002"],
            }
        )
        disjoint["work_packages"].append(
            {
                "wp_id": "WP-002",
                "blocked_by": [],
                "contract_refs": ["BDD-001", "TEST-001", "WP-002"],
                "source_refs": [],
                "command_refs": [],
            }
        )
        for contract in disjoint["contract_index"]:
            if contract["kind"] in {"bdd-scenario", "inner-test"}:
                contract["wp_refs"] = ["WP-002"]
                disjoint["work_packages"][0]["contract_refs"].remove(contract["contract_id"])
        disjoint["candidate"]["payload_sha256"] = validator.ready_payload_sha256(disjoint)
        errors = validator.validate_ready_cross_references(disjoint)
        self.assertTrue(
            any("source SRC-001 has no direct bdd-scenario contract sharing a WP" in error for error in errors),
            errors,
        )
        self.assertTrue(
            any("source SRC-001 has no direct inner-test contract sharing a WP" in error for error in errors),
            errors,
        )

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


class BugReadyPlanContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ready_schema = json.loads(
            (SKILLS_ROOT / "technical-planning/references/ready-plan.schema.json").read_text(encoding="utf-8")
        )

    def assert_valid(self, value: dict) -> None:
        self.assertEqual([], validator.validate_instance(value, self.ready_schema))
        self.assertEqual([], validator.validate_ready_cross_references(value))

    def test_verified_and_partial_bug_plans_are_conditionally_valid(self) -> None:
        self.assert_valid(bug_ready_example("verified"))
        self.assert_valid(bug_ready_example("partial"))
        self.assert_valid(ready_example())

    def test_bug_source_or_reproduction_command_requires_bug_context(self) -> None:
        missing = bug_ready_example()
        missing.pop("bug_context")
        missing["candidate"]["payload_sha256"] = validator.ready_payload_sha256(missing)
        errors = validator.validate_ready_cross_references(missing)
        self.assertTrue(any("bug_context" in error for error in errors), errors)

    def test_bug_context_binds_assessment_regression_and_reproduction(self) -> None:
        wrong_hash = bug_ready_example()
        wrong_hash["bug_context"]["assessment"]["sha256"] = "d" * 64
        wrong_hash["candidate"]["payload_sha256"] = validator.ready_payload_sha256(wrong_hash)
        errors = validator.validate_ready_cross_references(wrong_hash)
        self.assertTrue(any("assessment" in error and "source" in error for error in errors), errors)

        wrong_revision = bug_ready_example()
        next(source for source in wrong_revision["sources"] if source["kind"] == "bug")["revision"] = "2"
        wrong_revision["candidate"]["payload_sha256"] = validator.ready_payload_sha256(wrong_revision)
        errors = validator.validate_ready_cross_references(wrong_revision)
        self.assertTrue(any("one bug revision" in error for error in errors), errors)

        for invalid_revision in ("0", "01"):
            invalid = bug_ready_example()
            bug_source = next(source for source in invalid["sources"] if source["kind"] == "bug")
            bug_source["location"] = (
                f"docs/bugs/bug-sample-failure/assessment-{invalid_revision}.json"
            )
            bug_source["revision"] = invalid_revision
            invalid["bug_context"]["assessment"]["path"] = bug_source["location"]
            invalid["bug_context"]["assessment"]["markdown_path"] = (
                f"docs/bugs/bug-sample-failure/assessment-{invalid_revision}.md"
            )
            invalid["candidate"]["payload_sha256"] = validator.ready_payload_sha256(invalid)
            schema_errors = validator.validate_instance(invalid, self.ready_schema)
            semantic_errors = validator.validate_ready_cross_references(invalid)
            self.assertTrue(
                schema_errors or semantic_errors,
                (invalid_revision, schema_errors, semantic_errors),
            )
            self.assertTrue(
                any(
                    "positive" in error or "pattern" in error
                    for error in [*schema_errors, *semantic_errors]
                ),
                (invalid_revision, schema_errors, semantic_errors),
            )

        missing_regression = bug_ready_example()
        missing_regression["bug_context"]["regression_bdd_refs"] = ["BDD-MISSING"]
        missing_regression["candidate"]["payload_sha256"] = validator.ready_payload_sha256(missing_regression)
        errors = validator.validate_ready_cross_references(missing_regression)
        self.assertTrue(any("regression" in error and "unknown" in error for error in errors), errors)

        wrong_command = bug_ready_example()
        wrong_command["bug_context"]["original_reproduction_command_ref"] = "CMD-BDD-FULL-001"
        wrong_command["candidate"]["payload_sha256"] = validator.ready_payload_sha256(wrong_command)
        errors = validator.validate_ready_cross_references(wrong_command)
        self.assertTrue(any("bug-reproduction" in error for error in errors), errors)

    def test_partial_requires_proxy_red_green_residual_risk_and_follow_up(self) -> None:
        for field in ("reason", "proxy_bdd_refs", "proxy_test_refs", "residual_risks", "follow_up"):
            broken = bug_ready_example("partial")
            broken["bug_context"]["partial_safeguards"][field] = None if field == "reason" else []
            broken["candidate"]["payload_sha256"] = validator.ready_payload_sha256(broken)
            errors = validator.validate_ready_cross_references(broken)
            self.assertTrue(any("partial" in error for error in errors), (field, errors))

        for value in (
            "The BUG has been verified as fixed.",
            "The defect has been conclusively remediated and the repair conclusively validated.",
            "缺陷已徹底排除，修復結果已確認。",
        ):
            for field in ("reason", "residual_risks", "follow_up"):
                overclaim = bug_ready_example("partial")
                overclaim["bug_context"]["partial_safeguards"][field] = (
                    value if field == "reason" else [value]
                )
                overclaim["candidate"]["payload_sha256"] = validator.ready_payload_sha256(overclaim)
                errors = validator.validate_ready_cross_references(overclaim)
                self.assertTrue(any("overclaim" in error for error in errors), (value, field, errors))


if __name__ == "__main__":
    unittest.main(verbosity=2)
