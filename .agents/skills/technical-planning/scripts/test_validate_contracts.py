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


class SchemaSubsetContractTests(unittest.TestCase):
    def keyword_errors(self, schema: dict) -> list[str]:
        self.assertTrue(
            hasattr(validator, "schema_keyword_errors"),
            "the supported Schema subset is not exposed",
        )
        return validator.schema_keyword_errors(schema)


    def test_all_repository_schemas_use_only_the_supported_subset(self) -> None:
        paths = sorted(SKILLS_ROOT.glob("**/*schema.json"))
        self.assertEqual(6, len(paths), [path.as_posix() for path in paths])
        for path in paths:
            with self.subTest(path=path):
                schema = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual([], self.keyword_errors(schema))

    def test_unknown_validation_keyword_fails_with_location_without_data_value(self) -> None:
        secret_value = "PRIVATE_VALUE_MUST_NOT_APPEAR"
        schema = {
            "type": "object",
            "properties": {
                "display_name": {
                    "type": "string",
                    "unevaluatedProperties": False,
                }
            },
        }
        errors = validator.validate_instance({"display_name": secret_value}, schema)
        self.assertTrue(
            any(
                "$.properties.display_name" in error
                and "unevaluatedProperties" in error
                for error in errors
            ),
            errors,
        )
        self.assertNotIn(secret_value, "\n".join(errors))

    def test_property_names_are_not_misclassified_as_schema_keywords(self) -> None:
        schema = {
            "type": "object",
            "required": ["unknownBusinessKeyword"],
            "additionalProperties": False,
            "properties": {
                "unknownBusinessKeyword": {"type": "string", "minLength": 1}
            },
        }
        self.assertEqual([], self.keyword_errors(schema))
        self.assertEqual(
            [],
            validator.validate_instance(
                {"unknownBusinessKeyword": "valid"}, schema
            ),
        )

    def test_pattern_property_names_are_schema_map_keys_and_rules_are_enforced(self) -> None:
        schema = {
            "type": "object",
            "additionalProperties": False,
            "patternProperties": {
                r"^feature_[a-z]+$": {"type": "integer", "minimum": 1}
            },
        }
        self.assertEqual([], self.keyword_errors(schema))
        self.assertEqual([], validator.validate_instance({"feature_alpha": 1}, schema))
        self.assertTrue(
            any(
                "below minimum" in error
                for error in validator.validate_instance({"feature_alpha": 0}, schema)
            )
        )
        self.assertTrue(
            any(
                "unexpected property" in error
                for error in validator.validate_instance({"other": 1}, schema)
            )
        )
        invalid_pattern = copy.deepcopy(schema)
        invalid_pattern["patternProperties"] = {"[": {"type": "integer"}}
        self.assertTrue(
            any("invalid regular expression" in error for error in self.keyword_errors(invalid_pattern))
        )

    def test_type_composition_required_extra_and_boundaries_are_enforced(self) -> None:
        schema = {
            "type": "object",
            "required": ["kind", "values", "created_at"],
            "additionalProperties": False,
            "properties": {
                "kind": {"oneOf": [{"const": "a"}, {"const": "b"}]},
                "values": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 2,
                    "uniqueItems": True,
                    "items": {"type": "integer", "minimum": 1, "maximum": 3},
                },
                "created_at": {"type": "string", "format": "date-time"},
            },
        }
        valid = {
            "kind": "a",
            "values": [1, 3],
            "created_at": "2026-09-06T12:00:00Z",
        }
        self.assertEqual([], validator.validate_instance(valid, schema))
        invalid_values = (
            {},
            {**valid, "extra": True},
            {**valid, "kind": "c"},
            {**valid, "values": []},
            {**valid, "values": [1, 1]},
            {**valid, "values": [0]},
            {**valid, "values": [4]},
            {**valid, "created_at": "2026-09-06"},
        )
        for value in invalid_values:
            with self.subTest(value=value):
                self.assertTrue(validator.validate_instance(value, schema))


class ValidationProfileContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ready_schema = json.loads(
            (
                SKILLS_ROOT
                / "technical-planning/references/ready-plan.schema.json"
            ).read_text(encoding="utf-8")
        )

    @staticmethod
    def validation(profile: str = "local") -> dict:
        return {
            "schema": "validation-plan/v1",
            "profile": profile,
            "target_environment": {
                "os": "windows" if profile == "local" else "github",
                "python": "3.14.6",
                "git": "2.51.0.windows.1",
                "tools": ["rg 15.2.0"],
            },
            "required_obligations": [
                {"obligation_id": value, "command_ref": value}
                for value in (
                    "CMD-BDD-FULL-001",
                    "CMD-BUILD-FULL-001",
                    "CMD-TEST-FULL-001",
                )
            ],
            "coverage_edges": [
                {
                    "producer_command_ref": "CMD-TEST-FULL-001",
                    "covered_command_ref": value,
                    "required_child_ids": [child],
                    "inventory": "complete",
                }
                for value, child in (
                    ("CMD-BDD-FULL-001", "BDD-FULL"),
                    ("CMD-BUILD-FULL-001", "BUILD-FULL"),
                )
            ],
            "release_requirements": {
                "profile": "release",
                "platforms": ["windows", "linux"],
                "hosted": True,
            },
            "reuse_policy": {
                "terminal_only_paths": [
                    "docs/work/{work_id}/implementation/outcome*.json"
                ],
                "executable_input_globs": [
                    ".agents/skills/**",
                    "**/*.py",
                    "**/*.json",
                    "**/*.md",
                ],
            },
        }

    def ready(self, profile: str = "local") -> dict:
        value = ready_example()
        for command in value["commands"]:
            if command["command_id"] in {
                "CMD-BDD-FULL-001",
                "CMD-BUILD-FULL-001",
                "CMD-TEST-FULL-001",
            }:
                command["command"] = "tool full-suite --profile " + profile
        value["validation"] = self.validation(profile)
        value["candidate"]["payload_sha256"] = validator.ready_payload_sha256(value)
        return value

    def test_validation_capability_is_complete_when_present_and_legacy_is_valid(self) -> None:
        legacy = ready_example()
        self.assertEqual([], validator.validate_instance(legacy, self.ready_schema))
        self.assertEqual([], validator.validate_ready_cross_references(legacy))
        for profile in ("local", "release"):
            with self.subTest(profile=profile):
                value = self.ready(profile)
                self.assertEqual([], validator.validate_instance(value, self.ready_schema))
                self.assertEqual([], validator.validate_ready_cross_references(value))

    def test_incomplete_profile_and_unproven_coverage_fail_closed(self) -> None:
        incomplete = self.ready()
        del incomplete["validation"]["target_environment"]
        self.assertTrue(validator.validate_instance(incomplete, self.ready_schema))

        mismatched = self.ready()
        for command in mismatched["commands"]:
            if command["command_id"] == "CMD-BDD-FULL-001":
                command["command"] = "tool bdd-only"
        mismatched["candidate"]["payload_sha256"] = validator.ready_payload_sha256(
            mismatched
        )
        errors = validator.validate_ready_cross_references(mismatched)
        self.assertTrue(any("coverage command identity" in error for error in errors), errors)


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

    def test_stage_authorization_guard_is_required(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            copied = Path(temp_dir) / "skills"
            shutil.copytree(
                SKILLS_ROOT / "technical-planning",
                copied / "technical-planning",
            )
            skill_path = copied / "technical-planning/SKILL.md"
            text = skill_path.read_text(encoding="utf-8")
            self.assertIn("--phase planning", text)
            skill_path.write_text(
                text.replace("--phase planning", "--phase requirements", 1),
                encoding="utf-8",
                newline="\n",
            )
            errors = validator.validate_all(copied)
            self.assertTrue(
                any("stage authorization guard" in error for error in errors),
                errors,
            )

    def test_stage_authorization_guard_requires_file_first_seal_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            copied = Path(temp_dir) / "skills"
            shutil.copytree(
                SKILLS_ROOT / "technical-planning",
                copied / "technical-planning",
            )
            skill_path = copied / "technical-planning/SKILL.md"
            text = skill_path.read_text(encoding="utf-8")
            required = "第一次寫入或seal Candidate前"
            self.assertIn(required, text)
            skill_path.write_text(
                text.replace(required, "第一次寫入或展示 Candidate 前", 1),
                encoding="utf-8",
                newline="\n",
            )
            errors = validator.validate_all(copied)
            self.assertTrue(
                any("stage authorization guard" in error for error in errors),
                errors,
            )

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
