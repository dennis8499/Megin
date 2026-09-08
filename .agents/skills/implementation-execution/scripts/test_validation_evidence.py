#!/usr/bin/env python3
"""Focused tests for validation planning, evidence, review reuse, and archives."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parent
MODULE_PATH = SCRIPT_DIR / "validation_evidence.py"


def _load_module():
    if not MODULE_PATH.is_file():
        raise AssertionError("validation_evidence.py is absent")
    spec = importlib.util.spec_from_file_location("validation_evidence_under_test", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError("validation_evidence.py cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_full_suite_module():
    path = (
        SCRIPT_DIR.parents[1]
        / "project-knowledge/scripts/run_full_suite.py"
    )
    spec = importlib.util.spec_from_file_location("run_full_suite_under_test", path)
    if spec is None or spec.loader is None:
        raise AssertionError("run_full_suite.py cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_delivery_doctor_module():
    scripts = SCRIPT_DIR.parents[1] / "delivery-orchestrator/scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    path = scripts / "_delivery_doctor.py"
    spec = importlib.util.spec_from_file_location("delivery_doctor_under_test", path)
    if spec is None or spec.loader is None:
        raise AssertionError("_delivery_doctor.py cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _validation_plan() -> dict[str, object]:
    return {
        "schema": "validation-plan/v1",
        "profile": "local",
        "target_environment": {
            "os": "windows",
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
                "CMD-GOVERNANCE-001",
            )
        ],
        "coverage_edges": [
            {
                "producer_command_ref": "CMD-TEST-FULL-001",
                "covered_command_ref": value,
                "required_child_ids": children,
                "inventory": "complete",
            }
            for value, children in (
                ("CMD-BDD-FULL-001", ["BDD-FULL"]),
                ("CMD-BUILD-FULL-001", ["BUILD-FULL"]),
                ("CMD-GOVERNANCE-001", ["GOVERNANCE"]),
            )
        ],
        "release_requirements": {
            "profile": "release",
            "platforms": ["windows", "linux"],
            "hosted": True,
        },
        "reuse_policy": {
            "terminal_only_paths": [
                "docs/work/{work_id}/implementation/outcome*.json",
                "docs/work/{work_id}/implementation/outcome*.md",
                "knowledge/candidate-seal.json",
            ],
            "executable_input_globs": [
                ".agents/skills/**",
                "**/*.py",
                "**/*.json",
                "**/*.md",
            ],
        },
    }


def _commands() -> list[dict[str, str]]:
    command = "python -X utf8 -B runner.py --scope all --profile local"
    return [
        {"command_id": value, "command": command, "cwd": "."}
        for value in (
            "CMD-BDD-FULL-001",
            "CMD-BUILD-FULL-001",
            "CMD-TEST-FULL-001",
            "CMD-GOVERNANCE-001",
        )
    ]


def _precheck_inputs(*, block_coverage: bool = False) -> list[dict[str, object]]:
    values = []
    for check_id in (
        "source_requirement_coverage",
        "diff_manifest",
        "test_oracles",
        "ready_evidence",
        "snapshot",
        "environment",
    ):
        blocked = block_coverage and check_id == "source_requirement_coverage"
        values.append(
            {
                "check_id": check_id,
                "outcome": "blocked" if blocked else "passed",
                "evidence_refs": [f"precheck/{check_id}.json"],
                "findings": (
                    [
                        {
                            "finding_id": "F-coverage-1",
                            "message": "REQ-002 has no BDD or code evidence.",
                        },
                        {
                            "finding_id": "F-oracle-1",
                            "message": "TEST-002 has no discriminating oracle.",
                        },
                    ]
                    if blocked
                    else []
                ),
            }
        )
    return values


class CoverageAndBundleTests(unittest.TestCase):
    def test_profile_runner_rejects_exit_zero_with_skipped_inventory(self) -> None:
        runner = _load_full_suite_module()
        with tempfile.TemporaryDirectory() as temporary:
            fixture_root = Path(temporary) / "fixtures"
            fixture_root.mkdir()
            result = runner.execute_profile_item(
                {
                    "command_id": "TEST-SKIPPED",
                    "logical_command_id": "TEST-SKIPPED",
                    "execution_class": "parallel_safe",
                    "arguments": [
                        sys.executable,
                        "-c",
                        "print('{\"failed\":0,\"skipped\":1,\"run\":1}')",
                    ],
                    "timeout": 30,
                },
                workspace=Path.cwd(),
                fixture_root=fixture_root,
                fixture_argument=Path(".knowledge-test-tmp/fixtures"),
                worker_index=1,
            )
            self.assertEqual("failed", result["status"])
            self.assertEqual(0, result["exit_code"])
            self.assertEqual(1, result["skipped_count"])
            self.assertEqual("passed", result["worker_cleanup"])

    def test_full_suite_coverage_executes_each_child_once(self) -> None:
        module = _load_module()
        calls: list[str] = []

        def execute(command: dict[str, str]) -> dict[str, object]:
            calls.append(command["command_id"])
            return {
                "status": "passed",
                "exit_code": 0,
                "inventory_complete": True,
                "children": [
                    {"command_id": value, "status": "passed"}
                    for value in ("BDD-FULL", "BUILD-FULL", "GOVERNANCE")
                ],
            }

        report = module.execute_plan(_validation_plan(), _commands(), execute)
        self.assertEqual(["CMD-TEST-FULL-001"], calls)
        self.assertEqual(1, report["physical_execution_count"])
        self.assertEqual(
            {
                "CMD-BDD-FULL-001": "satisfied",
                "CMD-BUILD-FULL-001": "satisfied",
                "CMD-TEST-FULL-001": "satisfied",
                "CMD-GOVERNANCE-001": "satisfied",
            },
            {
                item["obligation_id"]: item["status"]
                for item in report["obligations"]
            },
        )

    def test_partial_coverage_runs_only_the_missing_obligation(self) -> None:
        module = _load_module()
        calls: list[str] = []

        def execute(command: dict[str, str]) -> dict[str, object]:
            calls.append(command["command_id"])
            children = (
                ["BUILD-FULL", "GOVERNANCE"]
                if command["command_id"] == "CMD-TEST-FULL-001"
                else []
            )
            return {
                "status": "passed",
                "exit_code": 0,
                "inventory_complete": True,
                "children": [
                    {"command_id": value, "status": "passed"}
                    for value in children
                ],
            }

        report = module.execute_plan(_validation_plan(), _commands(), execute)
        self.assertEqual(
            ["CMD-TEST-FULL-001", "CMD-BDD-FULL-001"],
            calls,
        )
        self.assertEqual(2, report["physical_execution_count"])
        self.assertTrue(
            all(item["status"] == "satisfied" for item in report["obligations"])
        )

    def test_atomic_bundle_and_reference_fail_closed(self) -> None:
        module = _load_module()
        self.assertTrue(
            hasattr(module, "write_bundle"),
            "atomic validation evidence writer is absent",
        )
        with tempfile.TemporaryDirectory() as temporary:
            evidence_root = Path(temporary) / "evidence"
            evidence_root.mkdir()
            executions = [
                {
                    "command_id": "CMD-PASS",
                    "status": "passed",
                    "exit_code": 0,
                    "duration_seconds": 1.25,
                    "failure_count": 0,
                    "skipped_count": 0,
                    "inventory_complete": True,
                    "children": [{"command_id": "CHILD", "status": "passed"}],
                    "stdout": b"passed output\n",
                    "stderr": b"",
                },
                {
                    "command_id": "CMD-FAIL",
                    "status": "failed",
                    "exit_code": 1,
                    "duration_seconds": 0.5,
                    "failure_count": 1,
                    "skipped_count": 0,
                    "inventory_complete": True,
                    "children": [],
                    "stdout": b"",
                    "stderr": b"assertion failed\n",
                },
                {
                    "command_id": "CMD-TIMEOUT",
                    "status": "timeout",
                    "exit_code": None,
                    "duration_seconds": 30.0,
                    "failure_count": None,
                    "skipped_count": None,
                    "inventory_complete": False,
                    "children": [],
                    "stdout": b"partial\n",
                    "stderr": b"",
                },
            ]
            bundle = module.write_bundle(
                evidence_root,
                "sample",
                profile="local",
                execution_input={
                    "head": "a" * 40,
                    "files": [],
                    "ready_payload_sha256": "b" * 64,
                },
                environment={"os": "windows", "python": "3.14.6"},
                ready_payload_sha256="b" * 64,
                executions=executions,
            )
            index_path = bundle / "index.json"
            verified = module.verify_bundle(index_path)
            self.assertEqual("validation-evidence/v1", verified["schema"])
            self.assertEqual(
                {"passed": 1, "failed": 1, "timeout": 1, "not_run": 0},
                verified["summary"]["counts"],
            )
            with self.assertRaises(FileExistsError):
                module.write_bundle(
                    evidence_root,
                    "sample",
                    profile="local",
                    execution_input={},
                    environment={},
                    ready_payload_sha256="b" * 64,
                    executions=[],
                )

            reference = module.make_reference(index_path, "CMD-PASS")
            self.assertEqual("validation-reference/v1", reference["schema"])
            self.assertEqual("verified", module.verify_reference(reference)["outcome"])
            with self.assertRaises(module.EvidenceError):
                module.make_reference(index_path, "CMD-TIMEOUT")

            original_index = index_path.read_bytes()
            ready_drift = json.loads(original_index)
            ready_drift["ready_payload_sha256"] = "d" * 64
            index_path.write_text(
                json.dumps(ready_drift, ensure_ascii=False, sort_keys=True, indent=2)
                + "\n",
                encoding="utf-8",
                newline="\n",
            )
            with self.assertRaises(module.EvidenceError):
                module.verify_bundle(index_path)
            index_path.write_bytes(original_index)

            stdout_path = bundle / verified["commands"][0]["stdout"]["path"]
            stdout_path.write_bytes(b"tampered\n")
            with self.assertRaises(module.EvidenceError):
                module.verify_bundle(index_path)

            missing_bundle = module.write_bundle(
                evidence_root,
                "missing",
                profile="local",
                execution_input={},
                environment={},
                ready_payload_sha256="c" * 64,
                executions=[executions[0]],
            )
            missing_index = json.loads(
                (missing_bundle / "index.json").read_text(encoding="utf-8")
            )
            (missing_bundle / missing_index["commands"][0]["stderr"]["path"]).unlink()
            with self.assertRaises(module.EvidenceError):
                module.verify_bundle(missing_bundle / "index.json")

            with mock.patch.object(module, "_is_redirect", return_value=True):
                with self.assertRaises(module.EvidenceError):
                    module.verify_bundle(index_path)

    def test_runner_profile_preserves_functional_output_and_writes_evidence(self) -> None:
        module = _load_module()
        runner = _load_full_suite_module()
        temporary_root = Path.cwd() / ".knowledge-test-tmp"
        shutil.rmtree(temporary_root, ignore_errors=True)
        fixture_root = temporary_root / "fixtures"
        evidence_root = temporary_root / "evidence"
        command = {
            "command_id": "TEST-CHILD",
            "arguments": [sys.executable, "-c", "pass"],
            "timeout": 30,
            "parallel_safe": True,
        }
        completed = subprocess.CompletedProcess(
            command["arguments"],
            0,
            b'{"failed":0,"skipped":0,"run":1}\n',
            b"",
        )
        stdout = io.StringIO()
        try:
            with (
                mock.patch.object(runner, "_commands", return_value=[command]),
                mock.patch.object(
                    runner.subprocess,
                    "run",
                    return_value=completed,
                ) as invoked,
                contextlib.redirect_stdout(stdout),
            ):
                exit_code = runner.main(
                    [
                        "--scope",
                        "all",
                        "--profile",
                        "local",
                        "--fixture-root",
                        ".knowledge-test-tmp/fixtures",
                        "--jobs",
                        "2",
                        "--evidence-root",
                        ".knowledge-test-tmp/evidence",
                        "--run-label",
                        "test-run",
                    ]
                )
            self.assertEqual(0, exit_code)
            functional = json.loads(stdout.getvalue())
            self.assertEqual("passed", functional["outcome"])
            self.assertEqual(1, len(functional["commands"]))
            child_invocations = [
                call
                for call in invoked.call_args_list
                if call.args and call.args[0] == command["arguments"]
            ]
            self.assertEqual(1, len(child_invocations))
            index = module.verify_bundle(evidence_root / "test-run/index.json")
            self.assertEqual("local", index["profile"])
            self.assertEqual("passed", index["commands"][0]["status"])
            self.assertEqual(
                completed.stdout.decode("utf-8"),
                (
                    evidence_root
                    / "test-run"
                    / index["commands"][0]["stdout"]["path"]
                ).read_text(encoding="utf-8"),
            )
        finally:
            shutil.rmtree(temporary_root, ignore_errors=True)


class ReviewPipelineTests(unittest.TestCase):
    def test_blocking_precheck_aggregates_findings_without_running_commands(self) -> None:
        module = _load_module()
        calls: list[str] = []

        def execute(command: dict[str, object]) -> dict[str, object]:
            calls.append(str(command["command_id"]))
            raise AssertionError("expensive validation must not start")

        report = module.run_review_precheck(
            _precheck_inputs(block_coverage=True),
            [
                {"command_id": "CMD-TEST-FULL-001"},
                {"command_id": "CMD-BDD-FULL-001"},
            ],
            execute,
            execution_input_identity="a" * 64,
            environment_identity="b" * 64,
            ready_payload_sha256="c" * 64,
        )
        self.assertEqual([], calls)
        self.assertEqual("blocked", report["precheck"]["outcome"])
        self.assertEqual(2, len(report["precheck"]["blocking_findings"]))
        self.assertEqual(
            ["not_run", "not_run"],
            [item["outcome"] for item in report["command_outcomes"]],
        )
        self.assertEqual(
            ["precheck_blocked", "precheck_blocked"],
            [item["not_run_reason"] for item in report["command_outcomes"]],
        )
        for outcome in report["command_outcomes"]:
            provenance = outcome["provenance"]
            self.assertEqual("executed", provenance["mode"])
            self.assertEqual("a" * 64, provenance["execution_input_identity"])
            self.assertEqual("b" * 64, provenance["environment_identity"])
            self.assertEqual("c" * 64, provenance["ready_payload_sha256"])
            for field in ("command_contract_sha256", "test_inventory_sha256"):
                self.assertRegex(provenance[field], r"^[a-f0-9]{64}$")

    def test_preliminary_executes_and_final_references_terminal_only_additions(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as temporary:
            evidence_root = Path(temporary) / "evidence"
            evidence_root.mkdir()
            bundle = module.write_bundle(
                evidence_root,
                "preliminary",
                profile="local",
                execution_input={"snapshot": "a" * 64, "commands": ["CMD-TEST-FULL-001"]},
                environment={"os": "windows", "python": "3.14.6"},
                ready_payload_sha256="b" * 64,
                executions=[
                    {
                        "command_id": "CMD-TEST-FULL-001",
                        "status": "passed",
                        "exit_code": 0,
                        "duration_seconds": 12.0,
                        "failure_count": 0,
                        "skipped_count": 0,
                        "inventory_complete": True,
                        "children": [{"command_id": "BDD-FULL", "status": "passed"}],
                        "stdout": b"passed\n",
                        "stderr": b"",
                    }
                ],
            )
            index_path = bundle / "index.json"
            index = module.verify_bundle(index_path)
            reference = module.make_reference(index_path, "CMD-TEST-FULL-001")
            changes = [
                {
                    "path": "docs/work/work-speed/implementation/outcome.json",
                    "change": "added",
                },
                {
                    "path": "docs/work/work-speed/implementation/outcome.md",
                    "change": "added",
                },
                {
                    "path": "knowledge/candidate-seal.json",
                    "change": "added",
                },
                {
                    "path": "snapshots/final-product.json",
                    "change": "added",
                },
                {
                    "path": "reviews/final/verifier.json",
                    "change": "added",
                },
            ]
            terminal_paths = [
                "docs/work/work-speed/implementation/outcome*.json",
                "docs/work/work-speed/implementation/outcome*.md",
                "knowledge/candidate-seal.json",
                "snapshots/*.json",
                "reviews/final/verifier*.json",
            ]
            preliminary = module.decide_review_execution(
                stage="preliminary",
                reference=reference,
                current_execution_input_identity=index["execution_input_identity"],
                current_environment_identity=index["environment_identity"],
                current_ready_payload_sha256=index["ready_payload_sha256"],
                changes=[],
                terminal_only_paths=terminal_paths,
            )
            self.assertEqual("executed", preliminary["mode"])
            final = module.decide_review_execution(
                stage="final",
                reference=reference,
                current_execution_input_identity=index["execution_input_identity"],
                current_environment_identity=index["environment_identity"],
                current_ready_payload_sha256=index["ready_payload_sha256"],
                changes=changes,
                terminal_only_paths=terminal_paths,
            )
            self.assertEqual("referenced", final["mode"])
            self.assertEqual("verified", final["verifier"]["outcome"])

    def test_reuse_requires_fresh_execution_for_every_nonterminal_drift_class(self) -> None:
        module = _load_module()
        base = {
            "schema": "validation-reference/v1",
            "execution_input_identity": "a" * 64,
            "environment_identity": "b" * 64,
            "ready_payload_sha256": "c" * 64,
        }
        terminal_paths = ["docs/work/work-speed/implementation/outcome*.json"]
        path_cases = (
            "src/product.py",
            "tests/test_product.py",
            ".agents/skills/example/SKILL.md",
            ".agents/skills/example/references/example.schema.json",
            "docs/behavior.md",
            "unclassified/new-input.bin",
        )
        for path in path_cases:
            with self.subTest(path=path):
                decision = module.decide_review_execution(
                    stage="final",
                    reference=base,
                    current_execution_input_identity="a" * 64,
                    current_environment_identity="b" * 64,
                    current_ready_payload_sha256="c" * 64,
                    changes=[{"path": path, "change": "modified"}],
                    terminal_only_paths=terminal_paths,
                    verify=False,
                )
                self.assertEqual("fresh_required", decision["mode"])
                self.assertIn("nonterminal_input", decision["reasons"])

        for field, current in (
            ("current_execution_input_identity", "d" * 64),
            ("current_environment_identity", "e" * 64),
            ("current_ready_payload_sha256", "f" * 64),
        ):
            arguments = {
                "stage": "final",
                "reference": base,
                "current_execution_input_identity": "a" * 64,
                "current_environment_identity": "b" * 64,
                "current_ready_payload_sha256": "c" * 64,
                "changes": [],
                "terminal_only_paths": terminal_paths,
                "verify": False,
            }
            arguments[field] = current
            decision = module.decide_review_execution(**arguments)
            self.assertEqual("fresh_required", decision["mode"])

        modified_terminal = module.decide_review_execution(
            stage="final",
            reference=base,
            current_execution_input_identity="a" * 64,
            current_environment_identity="b" * 64,
            current_ready_payload_sha256="c" * 64,
            changes=[
                {
                    "path": "docs/work/work-speed/implementation/outcome.json",
                    "change": "modified",
                }
            ],
            terminal_only_paths=terminal_paths,
            verify=False,
        )
        self.assertEqual("fresh_required", modified_terminal["mode"])

        cross_work = module.decide_review_execution(
            stage="final",
            reference=base,
            current_execution_input_identity="a" * 64,
            current_environment_identity="b" * 64,
            current_ready_payload_sha256="c" * 64,
            changes=[
                {
                    "path": "docs/work/work-other/implementation/outcome.json",
                    "change": "added",
                }
            ],
            terminal_only_paths=["docs/work/*/implementation/outcome*.json"],
            work_id="work-speed",
            existing_terminal_paths=[],
            verify=False,
        )
        self.assertEqual("fresh_required", cross_work["mode"])
        self.assertIn("nonterminal_input", cross_work["reasons"])

        skipped_revision = module.decide_review_execution(
            stage="final",
            reference=base,
            current_execution_input_identity="a" * 64,
            current_environment_identity="b" * 64,
            current_ready_payload_sha256="c" * 64,
            changes=[
                {
                    "path": "docs/work/work-speed/implementation/outcome-3.json",
                    "change": "added",
                }
            ],
            terminal_only_paths=["docs/work/*/implementation/outcome*.json"],
            work_id="work-speed",
            existing_terminal_paths=[
                "docs/work/work-speed/implementation/outcome.json"
            ],
            verify=False,
        )
        self.assertEqual("fresh_required", skipped_revision["mode"])
        self.assertIn("terminal_sequence", skipped_revision["reasons"])


class EvidenceOperationsTests(unittest.TestCase):
    def test_render_and_archive_are_deterministic_and_fail_closed(self) -> None:
        module = _load_module()
        handoff = {
            "schema": "ready-plan/v1",
            "commands": [
                {
                    "command_id": "CMD-TEST-FULL-001",
                    "purpose": "test-full",
                    "command": "python runner.py --scope all",
                }
            ],
            "sources": [
                {"source_id": "SRC-001", "location": "requirements.md"}
            ],
            "contract_index": [
                {
                    "contract_id": "BDD-301",
                    "kind": "bdd-scenario",
                    "source_refs": ["SRC-001"],
                    "wp_refs": ["WP-003"],
                },
                {
                    "contract_id": "TEST-301",
                    "kind": "inner-test",
                    "source_refs": ["SRC-001"],
                    "wp_refs": ["WP-003"],
                },
            ],
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_root = root / "run"
            run_root.mkdir()
            identity = {
                "run_id": "a" * 64,
                "repo_id": "b" * 64,
                "worktree_key": "c" * 64,
            }
            (run_root / "run.json").write_text(
                json.dumps({"schema": "implementation-ledger/v1", **identity}),
                encoding="utf-8",
            )
            evidence_root = run_root / "validation"
            evidence_root.mkdir()
            bundle = module.write_bundle(
                evidence_root,
                "complete",
                profile="local",
                execution_input={"scope": "all", "commands": ["CMD-TEST-FULL-001"]},
                environment={"os": "windows", "python": "3.14.6"},
                ready_payload_sha256="d" * 64,
                executions=[
                    {
                        "command_id": "CMD-TEST-FULL-001",
                        "status": "passed",
                        "exit_code": 0,
                        "duration_seconds": 2.0,
                        "failure_count": 0,
                        "skipped_count": 0,
                        "inventory_complete": True,
                        "children": [{"command_id": "BDD-FULL", "status": "passed"}],
                        "stdout": b"passed\n",
                        "stderr": b"",
                    }
                ],
            )
            index_path = bundle / "index.json"
            first = module.render_review(handoff, index_path)
            reordered = {key: handoff[key] for key in reversed(tuple(handoff))}
            second = module.render_review(reordered, index_path)
            self.assertEqual(first, second)
            self.assertIn("## Command summary", first)
            self.assertIn("## Traceability", first)
            self.assertIn("## Evidence overview", first)
            self.assertIn("BDD-301", first)
            self.assertNotIn("generated_at", first)

            archive_one = root / "one.zip"
            archive_two = root / "two.zip"
            module.export_archive(run_root, archive_one, identity=identity)
            module.export_archive(run_root, archive_two, identity=identity)
            self.assertEqual(archive_one.read_bytes(), archive_two.read_bytes())
            manifest = module.verify_archive(archive_one, expected_identity=identity)
            self.assertEqual("evidence-archive/v1", manifest["schema"])

            imports_root = root / "imports"
            imports_root.mkdir()
            imported = module.import_archive(
                archive_one,
                imports_root,
                expected_identity=identity,
            )
            self.assertFalse(imported["approval_inherited"])
            self.assertTrue(Path(imported["quarantine_root"]).joinpath("run.json").is_file())

            before = sorted(path.relative_to(imports_root).as_posix() for path in imports_root.rglob("*"))
            corrupt = root / "corrupt.zip"
            raw = bytearray(archive_one.read_bytes())
            raw[len(raw) // 2] ^= 0x01
            corrupt.write_bytes(raw)
            with self.assertRaises(module.EvidenceError):
                module.import_archive(corrupt, imports_root, expected_identity=identity)
            after = sorted(path.relative_to(imports_root).as_posix() for path in imports_root.rglob("*"))
            self.assertEqual(before, after)

            traversal = root / "traversal.zip"
            with zipfile.ZipFile(traversal, "w") as archive:
                archive.writestr("../escape.txt", b"escape")
            with self.assertRaises(module.EvidenceError):
                module.verify_archive(traversal)

    def test_activity_categories_and_benchmark_threshold(self) -> None:
        module = _load_module()
        doctor = _load_delivery_doctor_module()
        events = [
            {"at": "2026-09-07T00:00:00Z", "to_status": "active"},
            {"at": "2026-09-07T00:00:10Z", "to_status": "awaiting_user"},
            {"at": "2026-09-07T00:00:20Z", "to_status": "active"},
            {"at": "2026-09-07T00:00:40Z", "to_status": "blocked"},
            {"at": "2026-09-07T00:00:50Z", "to_status": "active"},
            {"at": "2026-09-07T00:01:10Z", "to_status": "complete"},
        ]
        activity = doctor.summarize_activity_durations(
            events,
            command_intervals=[
                {
                    "started_at": "2026-09-07T00:00:02Z",
                    "ended_at": "2026-09-07T00:00:07Z",
                }
            ],
            review_intervals=[
                {
                    "started_at": "2026-09-07T00:00:22Z",
                    "ended_at": "2026-09-07T00:00:27Z",
                }
            ],
        )
        self.assertEqual(
            {
                "commands": 5.0,
                "review": 5.0,
                "human_wait": 10.0,
                "interruption": 10.0,
                "active_work": 40.0,
            },
            activity["activity_durations_seconds"],
        )
        self.assertEqual([], activity["unavailable_fields"])

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            input_value = {"scope": "all", "commands": ["CMD-TEST-FULL-001"]}
            environment = {"os": "windows", "python": "3.14.6"}
            baseline_paths = []
            optimized_paths = []
            for index, duration in enumerate((100.0, 110.0, 120.0), 1):
                path = root / f"baseline-{index}.json"
                path.write_text(
                    json.dumps(
                        {
                            "schema": "knowledge-suite-metrics/v1",
                            "scope": "all",
                            "outcome": "passed",
                            "commands": [
                                {
                                    "command_id": "CMD-TEST-FULL-001",
                                    "status": "passed",
                                    "duration_seconds": duration,
                                    "exit_code": 0,
                                    "timeout_seconds": 900,
                                }
                            ],
                            "summary": {
                                "counts": {
                                    "passed": 1,
                                    "failed": 0,
                                    "timeout": 0,
                                    "not_run": 0,
                                },
                                "total_duration_seconds": duration,
                            },
                            "execution_input_class": module.canonical_sha256(input_value),
                            "environment_identity": module.canonical_sha256(environment),
                        },
                        sort_keys=True,
                    ),
                    encoding="utf-8",
                )
                baseline_paths.append(path)
            for index, duration in enumerate((60.0, 70.0, 80.0), 1):
                evidence_root = root / f"optimized-{index}"
                evidence_root.mkdir()
                bundle = module.write_bundle(
                    evidence_root,
                    "run",
                    profile="local",
                    execution_input=input_value,
                    environment=environment,
                    ready_payload_sha256="e" * 64,
                    executions=[
                        {
                            "command_id": "CMD-TEST-FULL-001",
                            "status": "passed",
                            "exit_code": 0,
                            "duration_seconds": duration,
                            "failure_count": 0,
                            "skipped_count": 0,
                            "inventory_complete": True,
                            "children": [],
                            "stdout": b"ok\n",
                            "stderr": b"",
                        }
                    ],
                )
                optimized_paths.append(bundle / "index.json")
            comparison = module.compare_benchmarks(
                baseline_paths,
                optimized_paths,
                minimum_improvement=30.0,
            )
            self.assertEqual("passed", comparison["outcome"])
            self.assertEqual(110.0, comparison["baseline_median_seconds"])
            self.assertEqual(70.0, comparison["optimized_median_seconds"])
            self.assertGreaterEqual(comparison["improvement_percent"], 30.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
