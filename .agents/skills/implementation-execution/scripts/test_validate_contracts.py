#!/usr/bin/env python3
"""Consumer-owned execution schema, Ledger, and review tests."""

from __future__ import annotations

import copy
import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).with_name("validate_contracts.py")
SPEC = importlib.util.spec_from_file_location("implementation_contract_validator", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot import {SCRIPT_PATH}")
validator = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = validator
SPEC.loader.exec_module(validator)

TECHNICAL_SCRIPTS = (
    SCRIPT_PATH.resolve().parents[2] / "technical-planning" / "scripts"
)
if str(TECHNICAL_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(TECHNICAL_SCRIPTS))
from _ready_fixture import GIT_SHA, HASH, ready_example

SKILLS_ROOT = SCRIPT_PATH.resolve().parents[2]


def _snapshot_example() -> dict:
    snapshot = {
        "schema": "implementation-snapshot/v1",
        "repo_id": HASH,
        "worktree_key": HASH,
        "base_sha": GIT_SHA,
        "head_sha": GIT_SHA,
        "ready_hashes": [
            {"ref": "docs/plans/example/handoff.json", "sha256": HASH},
            {"ref": "docs/plans/example/plan.md", "sha256": HASH},
        ],
        "source_hashes": [{"ref": "SRC-001", "sha256": HASH}],
        "tracked_diff_sha256": HASH,
        "unignored_files": [],
    }
    snapshot["snapshot_id"] = validator.canonical_sha256(snapshot)
    return snapshot


def _persist_terminal_evidence(
    root: Path,
    ledger: dict,
    ready: dict,
    report: dict,
) -> None:
    snapshot = _snapshot_example()
    report["snapshot_before"] = snapshot["snapshot_id"]
    report["snapshot_after"] = snapshot["snapshot_id"]
    history = ledger["attempts"][0]["state_history"]
    refs = {
        ref
        for transition in history
        for ref in transition["evidence_refs"]
    }
    refs.update(ledger["capability_evidence_refs"])
    refs.update(ledger["baseline_evidence_refs"])
    main_commands = [
        {
            "command_id": outcome["command_id"],
            "outcome": "passed",
            "exit_code": 0,
            "failure_count": 0,
            "skipped_count": 0,
            "stdout_ref": f"commands/sequence/{outcome['command_id']}.stdout.txt",
            "stderr_ref": f"commands/sequence/{outcome['command_id']}.stderr.txt",
        }
        for outcome in report["command_outcomes"]
    ]
    raw_response_ref = "reviews/round-1/raw-response.txt"
    report_ref = "reviews/round-1/report.json"
    snapshot_ref = "diffs/reviewed-snapshot.json"
    witness_evidence = {
        "review_received": [raw_response_ref],
        "snapshot_recomputed_before_persist": [snapshot_ref],
        "snapshot_matched_before_persist": [snapshot_ref],
        "report_persisted": [
            raw_response_ref,
            *sorted(report["raw_output_refs"]),
            report_ref,
        ],
        "snapshot_recomputed_after_persist": [snapshot_ref],
        "snapshot_matched_after_persist": [snapshot_ref],
    }
    payloads = {
        "source-manifest.json": ready["sources"],
        "wp-ledger.json": ledger["attempts"][0]["wp_states"],
        "breaker.json": {
            "schema": "implementation-breaker/v1",
            "findings": [],
            "global_no_progress_rounds": 0,
        },
        "commands/full-verification.json": {"commands": main_commands},
        "evidence/capability.json": {
            "schema": "implementation-capability/v1",
            "run_id": ledger["run_id"],
            "checks": {
                "fresh_reviewer": "passed",
                "git_workspace": "passed",
                "toolchain": "passed",
            },
            "evidence_refs": ledger["capability_evidence_refs"][1:],
        },
        "evidence/baseline.json": {
            "schema": "implementation-baseline/v1",
            "run_id": ledger["run_id"],
            "outcome": "passed",
            "evidence_refs": ledger["baseline_evidence_refs"][1:],
        },
        snapshot_ref: snapshot,
        report_ref: report,
    }
    source_hashes = sorted(
        (
            {"ref": source["source_id"], "sha256": source["sha256"]}
            for source in ready["sources"]
        ),
        key=lambda item: item["ref"],
    )
    for transition in history:
        for relative in transition["evidence_refs"]:
            if relative.startswith("integrity/") and relative.endswith("ready-source.json"):
                payloads[relative] = {
                    "schema": "implementation-integrity/v1",
                    "scope": relative,
                    "attempt_id": ledger["attempts"][0]["attempt_id"],
                    "transition_sequence": transition["sequence"],
                    "ready_sha256": validator.canonical_sha256(ready),
                    "source_hashes": source_hashes,
                }
    payloads.update(
        {
            relative: {
                "sequence": sequence,
                "step": step,
                "evidence_refs": witness_evidence[step],
            }
            for sequence, (step, relative) in enumerate(
                zip(validator.TERMINAL_WITNESS_STEPS, validator.TERMINAL_WITNESS_REFS),
                1,
            )
        }
    )
    for relative in refs:
        path = root.joinpath(*relative.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        if relative in payloads:
            path.write_text(
                json.dumps(payloads[relative], ensure_ascii=False, sort_keys=True) + "\n",
                encoding="utf-8",
                newline="\n",
            )
        else:
            path.write_text("evidence\n", encoding="utf-8", newline="\n")


class ImplementationContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.execution_schema = json.loads(
            (
                SKILLS_ROOT
                / "implementation-execution/references/execution-records.schema.json"
            ).read_text(encoding="utf-8")
        )

    def test_repository_contracts_pass(self) -> None:
        self.assertEqual([], validator.validate_all(SKILLS_ROOT))

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
                    "bdd_refs": ["BDD-001"],
                    "test_refs": ["TEST-001"],
                    "wp_refs": ["WP-001"],
                    "code_evidence": ["diff://src/file.py:symbol"],
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
        shared_output = copy.deepcopy(approved)
        shared_output["command_outcomes"][1]["output_ref"] = shared_output["command_outcomes"][0]["output_ref"]
        self.assertTrue(
            any(
                "reuse a raw output ref" in error
                for error in validator.validate_execution_record_semantics(shared_output)
            )
        )
        duplicate_raw_ref = copy.deepcopy(approved)
        duplicate_raw_ref["raw_output_refs"].append(duplicate_raw_ref["raw_output_refs"][0])
        self.assertTrue(
            any(
                "duplicate raw_output_refs" in error
                for error in validator.validate_execution_record_semantics(duplicate_raw_ref)
            )
        )

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
        drifted_failed = copy.deepcopy(failed)
        drifted_failed["snapshot_after"] = "1" * 64
        self.assertTrue(
            any(
                "accepted report requires identical" in error
                for error in validator.validate_execution_record_semantics(drifted_failed)
            )
        )

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
                            "evidence_refs": [
                                "evidence/preflight-start.json",
                                "integrity/global-1-ready-source.json",
                            ],
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

    def test_terminal_trace_breaker_freeze_and_secret_semantics(self) -> None:
        ready = ready_example()
        output_refs = [
            f"reviews/round-1/outputs/{command['command_id']}.txt"
            for command in ready["commands"]
            if command["purpose"] in {"build-full", "test-full", "bdd-full", "governance", "ci"}
        ]
        report = {
            "schema": "implementation-review/v1",
            "round": 1,
            "verdict": "APPROVED",
            "snapshot_before": HASH,
            "snapshot_after": HASH,
            "attestation": {
                "agent_id": "fresh-reviewer",
                "fresh_session": True,
                "read_only": True,
                "implementation_conversation_received": False,
                "delegation_used": False,
                "write_actions": False,
            },
            "command_outcomes": [
                {
                    "command_id": command["command_id"],
                    "outcome": "passed",
                    "exit_code": 0,
                    "failure_count": 0,
                    "skipped_count": 0,
                    "output_ref": output_ref,
                    "not_run_reason": None,
                }
                for command, output_ref in zip(
                    [
                        command
                        for command in ready["commands"]
                        if command["purpose"] in {"build-full", "test-full", "bdd-full", "governance", "ci"}
                    ],
                    output_refs,
                )
            ],
            "raw_output_refs": output_refs,
            "requirement_coverage": [
                {
                    "source_ref": "SRC-001",
                    "obligation_ref": "REQ-001",
                    "bdd_refs": ["BDD-001"],
                    "test_refs": ["TEST-001"],
                    "wp_refs": ["WP-001"],
                    "code_evidence": ["diff://src/file.py:symbol"],
                    "result": "covered",
                }
            ],
            "findings": [],
            "summary": "All required outcomes are independently covered.",
        }
        self.assertEqual([], validator.validate_execution_record_semantics(report))
        self.assertEqual([], validator.validate_review_against_ready(report, ready))

        main_output_refs = [
            f"commands/sequence/{outcome['command_id']}.{stream}.txt"
            for outcome in report["command_outcomes"]
            for stream in ("stdout", "stderr")
        ]
        terminal_refs = [
            "source-manifest.json",
            "wp-ledger.json",
            "breaker.json",
            "commands/full-verification.json",
            *main_output_refs,
            "diffs/reviewed-snapshot.json",
            "reviews/round-1/raw-response.txt",
            *output_refs,
            "reviews/round-1/report.json",
            *validator.TERMINAL_WITNESS_REFS,
            "integrity/global-5-ready-source.json",
            "integrity/WP-001/start-ready-source.json",
            "integrity/WP-001/complete-ready-source.json",
        ]
        ledger = {
            "schema": "implementation-ledger/v1",
            "run_id": HASH,
            "binding": {
                "repo_id": HASH,
                "canonical_worktree": "C:/repo-worktree",
                "worktree_key": HASH,
                "branch": "feature/example",
                "initial_base_sha": GIT_SHA,
                "run_id": HASH,
            },
            "handoff_path": "docs/plans/example/handoff.json",
            "capability_evidence_refs": [
                "evidence/capability.json",
                "evidence/capability-output.txt",
            ],
            "baseline_evidence_refs": [
                "evidence/baseline.json",
                "evidence/baseline-output.txt",
            ],
            "attempts": [
                {
                    "attempt_id": "attempt-1",
                    "candidate_revision": "candidate-1",
                    "state": "Complete",
                    "wp_states": {"WP-001": "Verified"},
                    "state_history": [
                        {"sequence": 1, "from": None, "to": "Preflight", "evidence_refs": ["integrity/global-1-ready-source.json"]},
                        {"sequence": 2, "from": "Preflight", "to": "Executing", "evidence_refs": ["integrity/global-2-ready-source.json"]},
                        {"sequence": 3, "from": "Executing", "to": "Verifying", "evidence_refs": ["integrity/global-3-ready-source.json"]},
                        {"sequence": 4, "from": "Verifying", "to": "Reviewing", "evidence_refs": ["integrity/global-4-ready-source.json"]},
                        {"sequence": 5, "from": "Reviewing", "to": "Complete", "evidence_refs": terminal_refs},
                    ],
                }
            ],
            "current_attempt_id": "attempt-1",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_root = Path(temp_dir)
            _persist_terminal_evidence(evidence_root, ledger, ready, report)
            self.assertEqual(
                [],
                validator.validate_execution_record_semantics(
                    ledger,
                    evidence_root=evidence_root,
                    ready=ready,
                ),
            )
            self.assertTrue(
                any(
                    "persisted evidence root" in error
                    for error in validator.validate_execution_record_semantics(ledger)
                )
            )
            incomplete = copy.deepcopy(ledger)
            incomplete["attempts"][0]["state_history"][-1]["evidence_refs"].remove(
                "commands/full-verification.json"
            )
            self.assertTrue(
                any(
                    "full command index" in error
                    for error in validator.validate_execution_record_semantics(
                        incomplete,
                        evidence_root=evidence_root,
                        ready=ready,
                    )
                )
            )
            reopened = copy.deepcopy(ledger)
            reopened["attempts"].append(
                {
                    "attempt_id": "attempt-2",
                    "candidate_revision": "candidate-2",
                    "state": "Preflight",
                    "wp_states": {"WP-001": "Pending"},
                    "state_history": [
                        {"sequence": 1, "from": None, "to": "Preflight", "evidence_refs": ["integrity/reopen-ready-source.json"]}
                    ],
                }
            )
            reopened["current_attempt_id"] = "attempt-2"
            self.assertTrue(
                any(
                    "not frozen" in error
                    for error in validator.validate_execution_record_semantics(
                        reopened,
                        evidence_root=evidence_root,
                        ready=ready,
                    )
                )
            )

            reused = copy.deepcopy(ledger)
            for transition in reused["attempts"][0]["state_history"]:
                transition["evidence_refs"] = ["integrity/global-1-ready-source.json"]
            self.assertTrue(
                any(
                    "reused across transitions" in error
                    for error in validator.validate_execution_record_semantics(
                        reused,
                        evidence_root=evidence_root,
                        ready=ready,
                    )
                )
            )

            missing_output = copy.deepcopy(ledger)
            missing_output["attempts"][0]["state_history"][-1]["evidence_refs"].remove(
                output_refs[-1]
            )
            self.assertTrue(
                any(
                    "every raw output" in error
                    for error in validator.validate_execution_record_semantics(
                        missing_output,
                        evidence_root=evidence_root,
                        ready=ready,
                    )
                )
            )

            missing_response = copy.deepcopy(ledger)
            missing_response["attempts"][0]["state_history"][-1]["evidence_refs"].remove(
                "reviews/round-1/raw-response.txt"
            )
            self.assertTrue(
                any(
                    "raw response" in error
                    for error in validator.validate_execution_record_semantics(
                        missing_response,
                        evidence_root=evidence_root,
                        ready=ready,
                    )
                )
            )

            missing_main_output = copy.deepcopy(ledger)
            missing_main_output["attempts"][0]["state_history"][-1]["evidence_refs"].remove(
                main_output_refs[-1]
            )
            self.assertTrue(
                any(
                    "every main command raw output" in error
                    for error in validator.validate_execution_record_semantics(
                        missing_main_output,
                        evidence_root=evidence_root,
                        ready=ready,
                    )
                )
            )

            missing_witness = copy.deepcopy(ledger)
            missing_witness["attempts"][0]["state_history"][-1]["evidence_refs"].remove(
                validator.TERMINAL_WITNESS_REFS[-1]
            )
            self.assertTrue(
                any(
                    "ordering witness" in error
                    for error in validator.validate_execution_record_semantics(
                        missing_witness,
                        evidence_root=evidence_root,
                        ready=ready,
                    )
                )
            )

            capability_path = evidence_root / "evidence/capability.json"
            capability_text = capability_path.read_text(encoding="utf-8")
            capability_path.unlink()
            self.assertTrue(
                any(
                    "not persisted" in error
                    for error in validator.validate_execution_record_semantics(
                        ledger,
                        evidence_root=evidence_root,
                        ready=ready,
                    )
                )
            )
            capability_path.write_text(capability_text, encoding="utf-8", newline="\n")

            integrity_path = evidence_root / "integrity/global-1-ready-source.json"
            integrity_text = integrity_path.read_text(encoding="utf-8")
            integrity_path.write_text("evidence\n", encoding="utf-8", newline="\n")
            self.assertTrue(
                any(
                    "integrity witness" in error
                    for error in validator.validate_execution_record_semantics(
                        ledger,
                        evidence_root=evidence_root,
                        ready=ready,
                    )
                )
            )
            integrity_path.write_text(integrity_text, encoding="utf-8", newline="\n")

            manifest_path = evidence_root / "source-manifest.json"
            manifest_path.write_text("[]\n", encoding="utf-8", newline="\n")
            self.assertTrue(
                any(
                    "source manifest differs" in error
                    for error in validator.validate_execution_record_semantics(
                        ledger,
                        evidence_root=evidence_root,
                        ready=ready,
                    )
                )
            )
            manifest_path.write_text(
                json.dumps(ready["sources"], sort_keys=True) + "\n",
                encoding="utf-8",
                newline="\n",
            )

            phantom_root = evidence_root / "phantom"
            phantom_root.mkdir()
            self.assertTrue(
                any(
                    "not persisted" in error
                    for error in validator.validate_execution_record_semantics(
                        ledger,
                        evidence_root=phantom_root,
                        ready=ready,
                    )
                )
            )

        empty_trace = copy.deepcopy(report)
        for field in ("bdd_refs", "test_refs", "wp_refs", "code_evidence"):
            empty_trace["requirement_coverage"][0][field] = []
        self.assertTrue(
            any("covered obligation" in error for error in validator.validate_execution_record_semantics(empty_trace))
        )
        secret = "EVAL_SECRET_DO_NOT_PERSIST_123456"
        secret_report = copy.deepcopy(report)
        secret_report["summary"] = secret
        self.assertTrue(validator.validate_execution_record_semantics(secret_report))
        secret_ready = copy.deepcopy(ready)
        secret_ready["approval"]["evidence"] = secret
        self.assertTrue(validator.validate_review_against_ready(report, secret_ready))

        key_inputs = {
            "category": "quality",
            "source_refs": ["SRC-001"],
            "affected_loci": ["src/file.py:symbol"],
            "required_outcome": "Restore the required behavior",
        }
        blocking_reports = []
        for round_number in (1, 2, 3):
            current = copy.deepcopy(report)
            current["round"] = round_number
            current["verdict"] = "CHANGES_REQUIRED"
            for outcome in current["command_outcomes"]:
                outcome["output_ref"] = outcome["output_ref"].replace(
                    "round-1",
                    f"round-{round_number}",
                )
            current["raw_output_refs"] = [
                ref.replace("round-1", f"round-{round_number}")
                for ref in current["raw_output_refs"]
            ]
            current["findings"] = [
                {
                    "finding_id": f"R-{round_number}",
                    "finding_key": validator.finding_key(key_inputs),
                    "key_inputs": key_inputs,
                    "severity": "high",
                    "blocking": True,
                    "message": "Required behavior is absent.",
                    "evidence_refs": ["evidence/finding.json"],
                    "wp_refs": ["WP-001"],
                    "bdd_refs": ["BDD-001"],
                    "test_refs": ["TEST-001"],
                }
            ]
            blocking_reports.append(current)
        key = validator.finding_key(key_inputs)
        breaker = {
            "schema": "implementation-breaker/v1",
            "findings": [
                {
                    "finding_key": key,
                    "consecutive_unresolved_rounds": 3,
                    "no_progress_rounds": 2,
                    "last_evidence_sha256": validator._breaker_evidence_sha(blocking_reports[-1], key),
                }
            ],
            "global_no_progress_rounds": 2,
        }
        self.assertTrue(validator.validate_execution_record_semantics(breaker))
        self.assertEqual([], validator.validate_breaker_against_reports(breaker, blocking_reports))
        self.assertTrue(validator.validate_breaker_against_reports(breaker, []))
        duplicate_inputs = copy.deepcopy(key_inputs)
        duplicate_inputs["source_refs"].append("SRC-001")
        self.assertEqual(
            validator.finding_key(key_inputs),
            validator.finding_key(duplicate_inputs),
        )
        duplicate_report = copy.deepcopy(blocking_reports[1])
        duplicate_report["findings"][0]["key_inputs"] = duplicate_inputs
        duplicate_report["findings"][0]["finding_key"] = validator.finding_key(duplicate_inputs)
        self.assertTrue(
            any(
                "duplicate normalized source_refs" in error
                for error in validator.validate_execution_record_semantics(duplicate_report)
            )
        )
        rotating_reports = []
        for index, current in enumerate(blocking_reports, 1):
            rotated = copy.deepcopy(current)
            rotated_inputs = copy.deepcopy(key_inputs)
            rotated_inputs["affected_loci"] = [f"src/file-{index}.py:symbol"]
            rotated["findings"][0]["key_inputs"] = rotated_inputs
            rotated["findings"][0]["finding_key"] = validator.finding_key(rotated_inputs)
            rotating_reports.append(rotated)
        latest_key = rotating_reports[-1]["findings"][0]["finding_key"]
        rotating_breaker = {
            "schema": "implementation-breaker/v1",
            "findings": [
                {
                    "finding_key": latest_key,
                    "consecutive_unresolved_rounds": 1,
                    "no_progress_rounds": 0,
                    "last_evidence_sha256": validator._breaker_evidence_sha(
                        rotating_reports[-1],
                        latest_key,
                    ),
                }
            ],
            "global_no_progress_rounds": 2,
        }
        self.assertEqual(
            [],
            validator.validate_breaker_against_reports(
                rotating_breaker,
                rotating_reports,
            ),
        )
        escaped_rotation = copy.deepcopy(rotating_breaker)
        escaped_rotation["global_no_progress_rounds"] = 0
        self.assertTrue(
            any(
                "global no-progress" in error
                for error in validator.validate_breaker_against_reports(
                    escaped_rotation,
                    rotating_reports,
                )
            )
        )

    def test_execution_mutations_are_detected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            copied = Path(temp_dir) / "skills"
            shutil.copytree(
                SKILLS_ROOT / "technical-planning",
                copied / "technical-planning",
            )
            shutil.copytree(
                SKILLS_ROOT / "implementation-execution",
                copied / "implementation-execution",
            )
            execution_path = (
                copied
                / "implementation-execution/references/execution-records.schema.json"
            )
            execution = json.loads(execution_path.read_text(encoding="utf-8"))
            execution["x-state-transitions"]["Verifying"].remove("Fixing")
            execution_path.write_text(
                json.dumps(execution),
                encoding="utf-8",
                newline="\n",
            )
            skill_path = copied / "implementation-execution/SKILL.md"
            skill_path.write_text(
                skill_path.read_text(encoding="utf-8")
                + "\n[broken contract](references/missing-contract.md)\n"
                + "<!-- authority: execution-review -->\n",
                encoding="utf-8",
                newline="\n",
            )
            errors = validator.validate_all(copied)
            self.assertTrue(
                any("implementation-records schema bytes drifted" in error for error in errors),
                errors,
            )
            self.assertTrue(
                any("Verifying" in error and "Fixing" in error for error in errors),
                errors,
            )
            self.assertTrue(any("broken local link" in error for error in errors), errors)
            self.assertTrue(
                any("authority 'execution-review'" in error for error in errors),
                errors,
            )

    def test_coverage_refs_are_owned_by_the_covered_source(self) -> None:
        ready = ready_example()
        ready["sources"].append(
            {
                "source_id": "SRC-002",
                "kind": "spec",
                "location": "docs/spec-2.md",
                "revision": "1",
                "sha256": HASH,
                "plan_refs": ["REQ-002"],
                "wp_refs": ["WP-002"],
            }
        )
        ready["contract_index"].extend(
            [
                {"contract_id": "BDD-002", "kind": "bdd-scenario", "source_refs": ["SRC-002"], "wp_refs": ["WP-002"]},
                {"contract_id": "TEST-002", "kind": "inner-test", "source_refs": ["SRC-002"], "wp_refs": ["WP-002"]},
                {"contract_id": "WP-002", "kind": "work-package", "source_refs": ["SRC-002"], "wp_refs": ["WP-002"]},
            ]
        )
        ready["work_packages"].append(
            {
                "wp_id": "WP-002",
                "blocked_by": ["WP-001"],
                "contract_refs": ["BDD-002", "TEST-002", "WP-002"],
                "source_refs": ["SRC-002"],
                "command_refs": [],
            }
        )
        outcomes = [
            {
                "command_id": command["command_id"],
                "outcome": "passed",
                "exit_code": 0,
                "failure_count": 0,
                "skipped_count": 0,
                "output_ref": f"reviews/round-1/outputs/{command['command_id']}.txt",
                "not_run_reason": None,
            }
            for command in ready["commands"]
            if command["purpose"] in {"build-full", "test-full", "bdd-full", "governance", "ci"}
        ]
        report = {
            "schema": "implementation-review/v1",
            "command_outcomes": outcomes,
            "requirement_coverage": [
                {
                    "source_ref": "SRC-001",
                    "obligation_ref": "REQ-001",
                    "bdd_refs": ["BDD-001"],
                    "test_refs": ["TEST-001"],
                    "wp_refs": ["WP-001"],
                    "code_evidence": ["diff://src/one.py"],
                    "result": "covered",
                },
                {
                    "source_ref": "SRC-002",
                    "obligation_ref": "REQ-002",
                    "bdd_refs": ["BDD-002"],
                    "test_refs": ["TEST-002"],
                    "wp_refs": ["WP-002"],
                    "code_evidence": ["diff://src/two.py"],
                    "result": "covered",
                },
            ],
            "findings": [],
        }
        self.assertEqual([], validator.validate_review_against_ready(report, ready))
        misbound = copy.deepcopy(report)
        misbound["requirement_coverage"][1].update(
            {
                "bdd_refs": ["BDD-001"],
                "test_refs": ["TEST-001"],
                "wp_refs": ["WP-001"],
            }
        )
        errors = validator.validate_review_against_ready(misbound, ready)
        self.assertTrue(any("misbinds bdd-scenario" in error for error in errors), errors)
        self.assertTrue(any("misbinds inner-test" in error for error in errors), errors)
        self.assertTrue(any("misbinds work package" in error for error in errors), errors)

    def test_executor_secret_and_rehash_mutations_are_detected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            copied = Path(temp_dir) / "skills"
            shutil.copytree(
                SKILLS_ROOT / "technical-planning",
                copied / "technical-planning",
            )
            shutil.copytree(
                SKILLS_ROOT / "implementation-execution",
                copied / "implementation-execution",
            )
            preflight_path = (
                copied
                / "implementation-execution/references/preflight-and-ledger.md"
            )
            preflight = preflight_path.read_text(encoding="utf-8")
            preflight = preflight.replace("只遮蔽該秘密值", "保存該秘密值")
            preflight = preflight.replace(
                "已知秘密值集合",
                "秘密值集合",
            )
            preflight = preflight.replace(
                "known_secret_values",
                "redacted_values",
            )
            preflight = preflight.replace(
                "每個WP開始／完成、global transition與snapshot前重算Ready／source hashes",
                "只在Preflight重算Ready／source hashes",
            )
            preflight = preflight.replace("未被其他transition重用", "可被其他transition重用")
            preflight = preflight.replace("canonical run root", "run root")
            preflight = preflight.replace("commands/full-verification.json", "commands/latest.json")
            preflight = preflight.replace("terminal/01-review_received.json", "terminal/review.json")
            preflight = preflight.replace("capability／baseline refs", "preflight refs")
            preflight = preflight.replace("implementation-capability/v1", "capability/v0")
            preflight = preflight.replace("implementation-integrity/v1", "integrity/v0")
            preflight_path.write_text(preflight, encoding="utf-8", newline="\n")
            orchestrated_path = (
                copied
                / "implementation-execution/references/orchestrated-delivery.md"
            )
            orchestrated_path.write_text(
                orchestrated_path.read_text(encoding="utf-8").replace(
                    "已遮蔽的approval evidence refs非空",
                    "approval evidence refs非空",
                ),
                encoding="utf-8",
                newline="\n",
            )
            reviewer_path = (
                copied
                / "implementation-execution/references/reviewer-contract.md"
            )
            reviewer_text = reviewer_path.read_text(encoding="utf-8").replace(
                "直接擁有同一`source_ref`",
                "使用任一`source_ref`",
            )
            reviewer_text = reviewer_text.replace(
                "`output_ref`只是傳輸位置",
                "`output_ref`代表進展",
            )
            reviewer_text = reviewer_text.replace(
                "duplicate normalized refs",
                "duplicate refs",
            )
            reviewer_text = reviewer_text.replace(
                "raw_output_refs`自身也不得重複",
                "raw_output_refs`可以重複",
            )
            reviewer_text = reviewer_text.replace(
                "A→B→C無證據輪換",
                "A→B→C輪換",
            )
            reviewer_path.write_text(
                reviewer_text,
                encoding="utf-8",
                newline="\n",
            )
            delivery_path = (
                copied
                / "implementation-execution/references/delivery-protocol.md"
            )
            delivery_text = delivery_path.read_text(encoding="utf-8").replace(
                "phantom ref",
                "logical ref",
            )
            delivery_text = delivery_text.replace(
                "terminal/<sequence>-<step>.json",
                "terminal/state.json",
            )
            delivery_path.write_text(
                delivery_text,
                encoding="utf-8",
                newline="\n",
            )

            errors = validator.validate_all(copied)
            self.assertTrue(any("只遮蔽該秘密值" in error for error in errors), errors)
            self.assertTrue(any("已知秘密值集合" in error for error in errors), errors)
            self.assertTrue(any("known_secret_values" in error for error in errors), errors)
            self.assertTrue(any("每個WP開始／完成" in error for error in errors), errors)
            self.assertTrue(any("未被其他transition重用" in error for error in errors), errors)
            self.assertTrue(any("canonical run root" in error for error in errors), errors)
            self.assertTrue(any("commands/full-verification.json" in error for error in errors), errors)
            self.assertTrue(any("terminal/01-review_received.json" in error for error in errors), errors)
            self.assertTrue(any("capability／baseline refs" in error for error in errors), errors)
            self.assertTrue(any("implementation-capability/v1" in error for error in errors), errors)
            self.assertTrue(any("implementation-integrity/v1" in error for error in errors), errors)
            self.assertTrue(any("redacted approval evidence" in error for error in errors), errors)
            self.assertTrue(any("直接擁有同一`source_ref`" in error for error in errors), errors)
            self.assertTrue(any("`output_ref`只是傳輸位置" in error for error in errors), errors)
            self.assertTrue(any("duplicate normalized refs" in error for error in errors), errors)
            self.assertTrue(any("raw_output_refs`自身也不得重複" in error for error in errors), errors)
            self.assertTrue(any("A→B→C無證據輪換" in error for error in errors), errors)
            self.assertTrue(any("phantom ref" in error for error in errors), errors)
            self.assertTrue(any("terminal/<sequence>-<step>.json" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main(verbosity=2)
