from __future__ import annotations

import copy
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).with_name("validate_contracts.py")
SPEC = importlib.util.spec_from_file_location("validate_contracts", SCRIPT_PATH)
assert SPEC and SPEC.loader
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)

SKILLS_ROOT = SCRIPT_PATH.resolve().parents[2]
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


class ContractValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ready_schema = json.loads((SKILLS_ROOT / "technical-planning/references/ready-plan.schema.json").read_text(encoding="utf-8"))
        cls.execution_schema = json.loads((SKILLS_ROOT / "implementation-execution/references/execution-records.schema.json").read_text(encoding="utf-8"))

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

    def test_review_outcomes_and_advisory_are_representable(self) -> None:
        key_inputs = {
            "category": "quality",
            "source_refs": ["SRC-001"],
            "affected_loci": ["src/file.py:symbol"],
            "required_outcome": "Document the tradeoff",
        }
        report = {
            "schema": "implementation-review/v1",
            "round": 1,
            "verdict": "BLOCKED",
            "snapshot_before": HASH,
            "snapshot_after": HASH,
            "attestation": {
                "agent_id": "reviewer-1",
                "fresh_session": True,
                "read_only": True,
                "implementation_conversation_received": False,
                "delegation_used": False,
                "write_actions": False,
            },
            "command_outcomes": [
                {
                    "command_id": "CMD-TEST-FULL-001",
                    "outcome": "not_run",
                    "exit_code": None,
                    "failure_count": None,
                    "skipped_count": None,
                    "output_ref": None,
                    "not_run_reason": "runner unavailable",
                }
            ],
            "raw_output_refs": ["response://reviewer-1/report"],
            "requirement_coverage": [
                {
                    "source_ref": "SRC-001",
                    "obligation_ref": "REQ-001",
                    "bdd_refs": [],
                    "test_refs": [],
                    "wp_refs": ["WP-001"],
                    "code_evidence": [],
                    "result": "blocked",
                }
            ],
            "findings": [
                {
                    "finding_id": "R-1",
                    "finding_key": validator.finding_key(key_inputs),
                    "key_inputs": key_inputs,
                    "severity": "advisory",
                    "blocking": False,
                    "message": "Non-blocking note",
                    "evidence_refs": ["response://reviewer-1/finding-1"],
                    "wp_refs": ["WP-001"],
                    "bdd_refs": [],
                    "test_refs": [],
                }
            ],
            "summary": "Unable to complete independent commands.",
        }
        self.assertEqual([], validator.validate_instance(report, self.execution_schema, "reviewReport"))
        self.assertEqual([], validator.validate_execution_record_semantics(report))

        approved = copy.deepcopy(report)
        approved["verdict"] = "APPROVED"
        approved["command_outcomes"][0] = {
            "command_id": "CMD-TEST-FULL-001",
            "outcome": "passed",
            "exit_code": 0,
            "failure_count": 0,
            "skipped_count": 0,
            "output_ref": "response://reviewer-1/test-output",
            "not_run_reason": None,
        }
        for command_id, output_name in (
            ("CMD-BUILD-FULL-001", "build-output"),
            ("CMD-BDD-FULL-001", "bdd-output"),
        ):
            approved["command_outcomes"].append(
                {
                    "command_id": command_id,
                    "outcome": "passed",
                    "exit_code": 0,
                    "failure_count": 0,
                    "skipped_count": 0,
                    "output_ref": f"response://reviewer-1/{output_name}",
                    "not_run_reason": None,
                }
            )
        approved["raw_output_refs"].extend(
            [
                "response://reviewer-1/test-output",
                "response://reviewer-1/build-output",
                "response://reviewer-1/bdd-output",
            ]
        )
        approved["requirement_coverage"][0]["result"] = "covered"
        self.assertEqual([], validator.validate_instance(approved, self.execution_schema, "reviewReport"))
        self.assertEqual([], validator.validate_execution_record_semantics(approved))
        self.assertEqual([], validator.validate_review_against_ready(approved, ready_example()))
        self.assertEqual(validator.finding_key(key_inputs), validator.finding_key(copy.deepcopy(key_inputs)))

        invalid_approved = copy.deepcopy(report)
        invalid_approved["verdict"] = "APPROVED"
        errors = validator.validate_execution_record_semantics(invalid_approved)
        self.assertTrue(any("every command outcome" in error for error in errors), errors)

        missing_coverage = copy.deepcopy(approved)
        missing_coverage["requirement_coverage"] = []
        errors = validator.validate_review_against_ready(missing_coverage, ready_example())
        self.assertTrue(any("missing source obligations" in error for error in errors), errors)

        failed = copy.deepcopy(report)
        failed["verdict"] = "CHANGES_REQUIRED"
        failed["command_outcomes"][0] = {
            "command_id": "CMD-TEST-FULL-001",
            "outcome": "failed",
            "exit_code": None,
            "failure_count": 1,
            "skipped_count": None,
            "output_ref": "response://reviewer-1/failed-output",
            "not_run_reason": None,
        }
        failed["raw_output_refs"].append("response://reviewer-1/failed-output")
        failed["findings"][0]["severity"] = "high"
        failed["findings"][0]["blocking"] = True
        self.assertEqual([], validator.validate_instance(failed, self.execution_schema, "reviewReport"))
        self.assertEqual([], validator.validate_execution_record_semantics(failed))

        blocked = copy.deepcopy(report)
        blocked["command_outcomes"][0] = {
            "command_id": "CMD-TEST-FULL-001",
            "outcome": "blocked",
            "exit_code": None,
            "failure_count": None,
            "skipped_count": None,
            "output_ref": "response://reviewer-1/blocked-output",
            "not_run_reason": None,
        }
        blocked["raw_output_refs"].append("response://reviewer-1/blocked-output")
        self.assertEqual([], validator.validate_instance(blocked, self.execution_schema, "reviewReport"))
        self.assertEqual([], validator.validate_execution_record_semantics(blocked))

    def test_ledger_and_snapshot_shapes_are_representable(self) -> None:
        binding = {
            "repo_id": HASH,
            "canonical_worktree": "C:/repo-worktree",
            "worktree_key": HASH,
            "branch": "feature/example",
            "initial_base_sha": GIT_SHA,
            "run_id": HASH,
        }
        ledger = {
            "schema": "implementation-ledger/v1",
            "run_id": HASH,
            "binding": binding,
            "handoff_path": "docs/plans/example/handoff.json",
            "capability_evidence_refs": ["evidence/capability.json"],
            "baseline_evidence_refs": [],
            "attempts": [
                {
                    "attempt_id": "attempt-1",
                    "candidate_revision": "candidate-1",
                    "state": "Preflight",
                    "wp_states": {"WP-001": "Pending"},
                    "state_history": [
                        {
                            "sequence": 1,
                            "from": None,
                            "to": "Preflight",
                            "evidence_refs": ["evidence/preflight-start.json"],
                        }
                    ],
                }
            ],
            "current_attempt_id": "attempt-1",
        }
        snapshot = {
            "schema": "implementation-snapshot/v1",
            "repo_id": HASH,
            "worktree_key": HASH,
            "base_sha": GIT_SHA,
            "head_sha": GIT_SHA,
            "ready_hashes": [{"ref": "handoff.json", "sha256": HASH}, {"ref": "plan.md", "sha256": HASH}],
            "source_hashes": [{"ref": "SRC-001", "sha256": HASH}],
            "tracked_diff_sha256": HASH,
            "unignored_files": [{"path": "src/new.py", "sha256": HASH}],
            "snapshot_id": HASH,
        }
        snapshot["snapshot_id"] = validator.canonical_sha256(
            {key: value for key, value in snapshot.items() if key != "snapshot_id"}
        )
        self.assertEqual([], validator.validate_instance(ledger, self.execution_schema, "ledger"))
        self.assertEqual([], validator.validate_instance(snapshot, self.execution_schema, "snapshot"))
        self.assertEqual([], validator.validate_execution_record_semantics(ledger))
        self.assertEqual([], validator.validate_execution_record_semantics(snapshot))

        illegal_ledger = copy.deepcopy(ledger)
        illegal_ledger["attempts"][0]["state"] = "Complete"
        illegal_ledger["attempts"][0]["state_history"].append(
            {
                "sequence": 2,
                "from": "Preflight",
                "to": "Complete",
                "evidence_refs": ["evidence/invalid-complete.json"],
            }
        )
        errors = validator.validate_execution_record_semantics(illegal_ledger)
        self.assertTrue(any("illegal transition" in error for error in errors), errors)

        drifted = copy.deepcopy(snapshot)
        drifted["tracked_diff_sha256"] = "1" * 64
        errors = validator.validate_execution_record_semantics(drifted)
        self.assertTrue(any("snapshot_id" in error for error in errors), errors)

    def test_mutations_are_detected_without_wording_checks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            copied = Path(temp_dir) / "skills"
            shutil.copytree(SKILLS_ROOT / "technical-planning", copied / "technical-planning")
            shutil.copytree(SKILLS_ROOT / "implementation-execution", copied / "implementation-execution")

            ready_path = copied / "technical-planning/references/ready-plan.schema.json"
            ready = json.loads(ready_path.read_text(encoding="utf-8"))
            ready["required"].remove("planning_baseline")
            ready["$defs"]["normalizedPath"]["pattern"] = "^[^\\\\]+$"
            ready_path.write_text(json.dumps(ready), encoding="utf-8")

            execution_path = copied / "implementation-execution/references/execution-records.schema.json"
            execution = json.loads(execution_path.read_text(encoding="utf-8"))
            execution["x-state-transitions"]["Verifying"].remove("Fixing")
            execution_path.write_text(json.dumps(execution), encoding="utf-8")

            skill_path = copied / "technical-planning/SKILL.md"
            skill_path.write_text(
                skill_path.read_text(encoding="utf-8")
                + "\n[broken contract](references/missing-contract.md)\n"
                + "<!-- authority: ready-plan -->\n",
                encoding="utf-8",
            )

            errors = validator.validate_all(copied)
            self.assertTrue(any("planning_baseline" in error for error in errors), errors)
            self.assertTrue(any("normalized path pattern accepts unsafe value" in error for error in errors), errors)
            self.assertTrue(any("Verifying" in error and "Fixing" in error for error in errors), errors)
            self.assertTrue(any("broken local link" in error for error in errors), errors)
            self.assertTrue(any("authority 'ready-plan'" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
