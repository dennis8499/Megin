#!/usr/bin/env python3
"""Compatibility runner for the split delivery-orchestrator test suites."""

from __future__ import annotations

import contextlib
import importlib.util
import inspect
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import _delivery_git as delivery_git
import _delivery_record as delivery_record
import _delivery_test_support as support
from test_delivery_safety import DeliverySafetyTests
from test_delivery_transitions import (
    DeliveryBugOverlayTests,
    DeliveryTerminalContractTests,
    DeliveryTransitionTests,
)
from test_delivery_worktree import DeliveryWorktreeTests, UnifiedEntryAuthorizationTests


class DeliveryPerformanceTests(support.DeliveryFixture):
    def test_50k_repository_probe_transition_and_authorize_stay_under_two_seconds(self) -> None:
        primary = self.make_repo("performance-50k-project")
        blob = support.run(
            ["git", "-C", str(primary), "hash-object", "-w", "--stdin"],
            input_bytes=b"fixture\n",
        ).stdout.decode("ascii").strip()
        fixture_paths = [
            f"fixture/{index // 100:03d}/path-{index:05d}.txt"
            for index in range(49_999)
        ]
        index_entries = b"".join(
            f"100644 {blob}\t{path}\n".encode("ascii") for path in fixture_paths
        )
        support.run(
            ["git", "-C", str(primary), "update-index", "--add", "--index-info"],
            input_bytes=index_entries,
        )
        support.git(primary, "commit", "-m", "50k performance fixture")
        local_profile = os.environ.get("MEGIN_RUNNER_VALIDATION_PROFILE") == "local"
        if local_profile:
            support.run(
                [
                    "git",
                    "-C",
                    str(primary),
                    "update-index",
                    "--skip-worktree",
                    "-z",
                    "--stdin",
                ],
                input_bytes=("\0".join(fixture_paths) + "\0").encode("ascii"),
            )
        else:
            support.git(primary, "checkout-index", "--all", "--force")
            support.git(primary, "update-index", "--refresh")
        tracked = [
            item
            for item in support.git(primary, "ls-files", "-z").stdout.split(b"\0")
            if item
        ]
        self.assertEqual(50_000, len(tracked))
        self.assertEqual(not local_profile, (primary / fixture_paths[0]).exists())

        probe_started = time.perf_counter()
        probe = support.workspace.probe_repository(primary)
        probe_elapsed = time.perf_counter() - probe_started
        self.assertTrue(probe["strict_clean"])

        work_id = "performance-50k-transition"
        delivery = Path(self.start(primary, work_id)["worktree"])
        delivery_tracked = [
            item
            for item in support.git(delivery, "ls-files", "-z").stdout.split(b"\0")
            if item
        ]
        self.assertEqual(50_000, len(delivery_tracked))
        self.assertTrue((delivery / fixture_paths[0]).is_file())
        transition_started = time.perf_counter()
        transitioned = self.transition(
            delivery,
            work_id,
            "requirements",
            "active",
            "requirements_started",
        )
        transition_elapsed = time.perf_counter() - transition_started
        authorization_started = time.perf_counter()
        authorization = support.workspace.authorize_stage(
            delivery,
            "requirements",
            root=self.registry,
            work_id=work_id,
        )
        authorization_elapsed = time.perf_counter() - authorization_started

        self.assertEqual("requirements", transitioned["phase"])
        self.assertEqual("active", transitioned["status"])
        self.assertEqual("authorized", authorization["outcome"])
        required_measurements = {
            "probe_seconds": probe_elapsed,
            "transition_seconds": transition_elapsed,
        }
        print(
            json.dumps(
                {
                    "authorization_observation_seconds": round(
                        authorization_elapsed, 6
                    ),
                    "file_count": len(tracked),
                    **{
                        name: round(duration, 6)
                        for name, duration in required_measurements.items()
                    },
                },
                sort_keys=True,
            )
        )
        self.assertEqual(
            {},
            {
                name: round(duration, 6)
                for name, duration in required_measurements.items()
                if duration >= 2.0
            },
            json.dumps(
                {
                    **required_measurements,
                    "authorization_observation_seconds": authorization_elapsed,
                },
                sort_keys=True,
            ),
        )

    def test_full_probe_and_ready_transition_stay_within_git_budgets(self) -> None:
        primary = self.make_repo("performance-project")
        commands: list[dict[str, object]] = []
        real_git = delivery_git._git
        lock_active = False

        def recording_git(
            repo: str | Path,
            arguments: list[str],
            *,
            check: bool = True,
            input_bytes: bytes | None = None,
        ) -> object:
            commands.append(
                {
                    "lock": "post" if lock_active else "pre",
                    "arguments": list(arguments),
                }
            )
            return real_git(
                repo,
                arguments,
                check=check,
                input_bytes=input_bytes,
            )

        git_patches = (
            mock.patch.object(delivery_git, "_git", side_effect=recording_git),
            mock.patch.object(delivery_record, "_git", side_effect=recording_git),
            mock.patch.object(support.workspace, "_git", side_effect=recording_git),
        )
        with git_patches[0], git_patches[1], git_patches[2]:
            probe = support.workspace.probe_repository(primary)

        self.assertTrue(probe["strict_clean"])
        full_probe_commands = list(commands)
        self.assertEqual(
            [
                "rev-parse",
                "--is-bare-repository",
                "--show-toplevel",
                "--path-format=absolute",
                "--git-common-dir",
                "HEAD",
            ],
            full_probe_commands[0]["arguments"],
        )
        self.assertEqual(
            1,
            sum(
                item["arguments"][-3:] == ["ls-files", "--stage", "-z"]
                for item in full_probe_commands
            ),
        )
        self.assertFalse(
            any(
                item["arguments"][-2:] == ["ls-files", "-z"]
                for item in full_probe_commands
            )
        )

        delivery = Path(
            self.start(primary, "performance-transition-work")["worktree"]
        )
        commands.clear()
        real_lock = support.workspace._exclusive_lock

        @contextlib.contextmanager
        def recording_lock(path: Path) -> object:
            nonlocal lock_active
            with real_lock(path):
                lock_active = True
                try:
                    yield
                finally:
                    lock_active = False

        with (
            mock.patch.object(delivery_git, "_git", side_effect=recording_git),
            mock.patch.object(delivery_record, "_git", side_effect=recording_git),
            mock.patch.object(support.workspace, "_git", side_effect=recording_git),
            mock.patch.object(
                support.workspace,
                "_exclusive_lock",
                side_effect=recording_lock,
            ),
        ):
            transitioned = self.transition(
                delivery,
                "performance-transition-work",
                "requirements",
                "active",
                "requirements_started",
            )

        self.assertEqual("requirements", transitioned["phase"])
        self.assertEqual("active", transitioned["status"])
        failures: dict[str, object] = {}
        if len(full_probe_commands) > 6:
            failures["full_probe_git_calls"] = len(full_probe_commands)
        if len(commands) > 8:
            failures["ready_transition_git_calls"] = len(commands)
        pre_lock_calls = sum(item["lock"] == "pre" for item in commands)
        if pre_lock_calls != 1:
            failures["pre_lock_git_calls"] = pre_lock_calls
        if not any(
            item["lock"] == "post" and "status" in item["arguments"]
            for item in commands
        ):
            failures["post_lock_status_probe"] = "missing"
        self.assertEqual(
            {},
            failures,
            json.dumps(
                {
                    "failures": failures,
                    "full_probe_commands": full_probe_commands,
                    "ready_transition_commands": commands,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        )


class DeliveryTransitionArchitectureTests(support.DeliveryFixture):
    BDD_BINDINGS = {"BDD-028": "test_phase_handlers_and_validator_adapter_are_explicit"}

    def test_phase_handlers_and_validator_adapter_are_explicit(self) -> None:
        script_dir = Path(__file__).resolve().parent
        handlers_path = script_dir / "_delivery_transition_handlers.py"
        adapter_path = script_dir / "_delivery_validator_adapter.py"
        self.assertTrue(handlers_path.is_file(), "phase transition handlers are absent")
        self.assertTrue(adapter_path.is_file(), "owner validator adapter is absent")

        handlers_spec = importlib.util.spec_from_file_location(
            "delivery_transition_handlers_contract", handlers_path
        )
        self.assertIsNotNone(handlers_spec)
        self.assertIsNotNone(handlers_spec.loader)
        handlers = importlib.util.module_from_spec(handlers_spec)
        sys.modules[handlers_spec.name] = handlers
        handlers_spec.loader.exec_module(handlers)
        self.assertEqual(
            {"requirements", "planning", "implementation", "knowledge"},
            set(handlers.PHASE_HANDLERS),
        )
        self.assertTrue(
            all(
                isinstance(handler, handlers.TransitionPhaseHandler)
                for handler in handlers.PHASE_HANDLERS.values()
            )
        )
        self.assertTrue(hasattr(handlers, "TransitionContext"))
        self.assertTrue(handlers.TransitionContext.__dataclass_params__.frozen)
        request = handlers.TransitionRequest(
            current_phase="requirements",
            current_status="active",
            phase="planning",
            status="active",
            requirements=handlers.OptionalBinding(("path", "hash", ("approval",))),
            plan=handlers.OptionalBinding((None, None, None, ())),
            implementation=handlers.OptionalBinding((None, None, None)),
            knowledge_review=handlers.OptionalBinding((None, None, None, None, None)),
            promotion=handlers.OptionalBinding((None, None, None, None)),
        )
        self.assertEqual(("planning", "active"), handlers.validate_transition_route(request))

        adapter_spec = importlib.util.spec_from_file_location(
            "delivery_validator_adapter_contract", adapter_path
        )
        self.assertIsNotNone(adapter_spec)
        self.assertIsNotNone(adapter_spec.loader)
        adapter = importlib.util.module_from_spec(adapter_spec)
        sys.modules[adapter_spec.name] = adapter
        adapter_spec.loader.exec_module(adapter)
        owner = adapter.OwnerValidatorAdapter()
        self.assertIs(owner.validator("planning"), owner.validator("planning"))

        record_source = (script_dir / "_delivery_record.py").read_text(encoding="utf-8")
        self.assertNotIn("importlib.util", record_source)
        coordinator = inspect.getsource(support.workspace._transition_record_unlocked)
        self.assertIn("apply_transition_handlers", coordinator)
        for phase_owned_block in (
            'PHASE_HANDLERS["requirements"]',
            'PHASE_HANDLERS["planning"]',
            'PHASE_HANDLERS["implementation"]',
            'PHASE_HANDLERS["knowledge"]',
            "if transition_request.requirements.supplied",
            "if transition_request.plan.supplied",
            "if transition_request.implementation.supplied",
            "if review_supplied",
        ):
            self.assertNotIn(phase_owned_block, coordinator)

    def test_windows_git_capture_uses_regular_files_and_preserves_bytes(self) -> None:
        observed: dict[str, object] = {}

        def fake_run(command, **kwargs):
            observed.update(kwargs)
            self.assertIsNot(kwargs.get("stdin"), subprocess.PIPE)
            self.assertIsNot(kwargs.get("stdout"), subprocess.PIPE)
            self.assertIsNot(kwargs.get("stderr"), subprocess.PIPE)
            self.assertEqual(b"request-bytes", kwargs["stdin"].read())
            kwargs["stdout"].write(b"response-bytes")
            kwargs["stderr"].write(b"diagnostic-bytes")
            kwargs["stdout"].flush()
            kwargs["stderr"].flush()
            return subprocess.CompletedProcess(command, 17)

        with mock.patch.object(delivery_git.subprocess, "run", side_effect=fake_run):
            completed = delivery_git._run_captured_process(
                ["git", "version"],
                environment={"LC_ALL": "C"},
                input_bytes=b"request-bytes",
                use_regular_files=True,
            )

        self.assertEqual(17, completed.returncode)
        self.assertEqual(b"response-bytes", completed.stdout)
        self.assertEqual(b"diagnostic-bytes", completed.stderr)
        self.assertFalse(observed.get("shell", False))

        fixture_result = subprocess.CompletedProcess(["git", "version"], 0, b"fixture", b"")
        with mock.patch.object(
            support,
            "_run_captured_process",
            return_value=fixture_result,
        ) as fixture_capture:
            self.assertIs(fixture_result, support.run(["git", "version"]))
        fixture_capture.assert_called_once()


class DeliveryDoctorTests(support.DeliveryFixture):
    BDD_BINDINGS = {"BDD-030": "test_doctor_passes_with_seven_checks_and_zero_writes"}

    @staticmethod
    def _path_snapshot(path: Path) -> tuple[bool, dict[str, str]]:
        return path.exists(), support.file_bytes(path) if path.exists() else {}

    def _observed_snapshot(
        self,
        primary: Path,
        delivery: Path,
        sentinel: Path,
        registry: Path | None = None,
    ) -> dict[str, object]:
        observed_registry = registry or self.registry
        return {
            "primary": support.primary_snapshot(primary),
            "delivery": support.primary_snapshot(delivery),
            "registry": self._path_snapshot(observed_registry),
            "sentinel": sentinel.read_bytes(),
        }

    def test_doctor_passes_with_seven_checks_and_zero_writes(self) -> None:
        primary = self.make_repo("doctor-valid")
        work_id = "doctor-valid-work"
        delivery = Path(self.start(primary, work_id)["worktree"])
        sentinel = self.root / "outside-sentinel.bin"
        sentinel.write_bytes(b"outside remains unchanged\n")
        before = self._observed_snapshot(primary, delivery, sentinel)

        report = support.workspace.doctor_workspace(
            delivery,
            root=self.registry,
            work_id=work_id,
        )

        self.assertEqual("delivery-doctor/v1", report["schema"])
        self.assertEqual("passed", report["outcome"])
        self.assertEqual(0, support.workspace.doctor_exit_code(report))
        self.assertEqual(
            [
                "repository_identity",
                "registry",
                "record",
                "generation",
                "artifacts",
                "evidence",
                "recovery",
            ],
            [check["check_id"] for check in report["checks"]],
        )
        self.assertTrue(all(check["outcome"] == "passed" for check in report["checks"]))
        self.assertEqual(work_id, report["work"]["work_id"])
        self.assertTrue(
            any(action["code"] == "RESUME_CURRENT_RUN" for action in report["next_actions"])
        )
        self.assertEqual(before, self._observed_snapshot(primary, delivery, sentinel))

    def test_discovery_failures_are_closed_and_do_not_select_a_run(self) -> None:
        no_run_repo = self.make_repo("doctor-no-run")
        absent_registry = self.root / "absent-registry"
        report = support.workspace.doctor_workspace(no_run_repo, root=absent_registry)
        self.assertEqual("blocked", report["outcome"])
        self.assertIn("NO_ACTIVE_RUN", {item["code"] for item in report["diagnostics"]})
        self.assertIsNone(report["work"])
        self.assertFalse(absent_registry.exists())

        missing_repo = self.make_repo("doctor-missing-record")
        missing_probe = support.workspace.probe_repository(missing_repo)
        missing_root = self.root / "missing-registry"
        missing_dir = (
            missing_root
            / "repos"
            / missing_probe["repo_id"]
            / "works"
            / "doctor-missing-work"
        )
        missing_dir.mkdir(parents=True)
        before_missing = self._path_snapshot(missing_root)
        missing = support.workspace.doctor_workspace(
            missing_repo,
            root=missing_root,
            work_id="doctor-missing-work",
        )
        self.assertIn("RECORD_MISSING", {item["code"] for item in missing["diagnostics"]})
        self.assertEqual(before_missing, self._path_snapshot(missing_root))

        corrupt_repo = self.make_repo("doctor-corrupt-record")
        corrupt_probe = support.workspace.probe_repository(corrupt_repo)
        corrupt_root = self.root / "corrupt-registry"
        corrupt_path = (
            corrupt_root
            / "repos"
            / corrupt_probe["repo_id"]
            / "works"
            / "doctor-corrupt-work"
            / "run.json"
        )
        corrupt_path.parent.mkdir(parents=True)
        corrupt_path.write_bytes(b'{"schema":"delivery-run/v1",')
        before_corrupt = self._path_snapshot(corrupt_root)
        corrupt = support.workspace.doctor_workspace(
            corrupt_repo,
            root=corrupt_root,
            work_id="doctor-corrupt-work",
        )
        self.assertIn("INVALID_RECORD", {item["code"] for item in corrupt["diagnostics"]})
        self.assertEqual(before_corrupt, self._path_snapshot(corrupt_root))

        ambiguous_repo = self.make_repo("doctor-ambiguous")
        first = Path(self.start(ambiguous_repo, "doctor-first-work")["worktree"])
        second = Path(self.start(ambiguous_repo, "doctor-second-work")["worktree"])
        sentinel = self.root / "ambiguous-sentinel.bin"
        sentinel.write_bytes(b"keep")
        before = {
            "primary": support.primary_snapshot(ambiguous_repo),
            "first": support.primary_snapshot(first),
            "second": support.primary_snapshot(second),
            "registry": self._path_snapshot(self.registry),
            "sentinel": sentinel.read_bytes(),
        }
        ambiguous = support.workspace.doctor_workspace(ambiguous_repo, root=self.registry)
        self.assertIn("AMBIGUOUS_RUNS", {item["code"] for item in ambiguous["diagnostics"]})
        self.assertEqual(["doctor-first-work", "doctor-second-work"], ambiguous["available_work_ids"])
        self.assertIsNone(ambiguous["work"])
        self.assertEqual(
            before,
            {
                "primary": support.primary_snapshot(ambiguous_repo),
                "first": support.primary_snapshot(first),
                "second": support.primary_snapshot(second),
                "registry": self._path_snapshot(self.registry),
                "sentinel": sentinel.read_bytes(),
            },
        )

    def test_identity_artifact_evidence_and_recovery_are_distinct(self) -> None:
        identity_repo = self.make_repo("doctor-identity")
        identity_work = "doctor-identity-work"
        identity_delivery = Path(self.start(identity_repo, identity_work)["worktree"])
        identity = support.workspace.doctor_workspace(
            identity_repo,
            root=self.registry,
            work_id=identity_work,
        )
        self.assertIn("IDENTITY_MISMATCH", {item["code"] for item in identity["diagnostics"]})
        self.assertEqual(3, support.workspace.doctor_exit_code(identity))

        drift_repo = self.make_repo("doctor-artifact")
        drift_work = "doctor-artifact-work"
        drift_delivery = Path(self.start(drift_repo, drift_work)["worktree"])
        self.enter_requirements(drift_delivery, drift_work)
        requirements_path, requirements_sha = self.approve_requirements(
            drift_delivery, drift_work
        )
        self.approve_plan(
            drift_delivery,
            drift_work,
            requirements_path,
            requirements_sha,
        )
        requirements_file = drift_delivery / Path(*requirements_path.split("/"))
        requirements_file.write_text("# drifted bytes\n", encoding="utf-8", newline="\n")
        before_drift = requirements_file.read_bytes()
        drift = support.workspace.doctor_workspace(
            drift_delivery,
            root=self.registry,
            work_id=drift_work,
        )
        self.assertIn("ARTIFACT_DRIFT", {item["code"] for item in drift["diagnostics"]})
        self.assertEqual(before_drift, requirements_file.read_bytes())

        evidence_repo = self.make_repo("doctor-evidence")
        evidence_work = "doctor-evidence-work"
        evidence_delivery = Path(self.start(evidence_repo, evidence_work)["worktree"])
        self.enter_requirements(evidence_delivery, evidence_work)
        self.approve_requirements(evidence_delivery, evidence_work)
        evidence_probe = support.workspace.probe_repository(evidence_delivery)
        record_path = (
            self.registry
            / "repos"
            / evidence_probe["repo_id"]
            / "works"
            / evidence_work
            / "run.json"
        )
        record = json.loads(record_path.read_text(encoding="utf-8"))
        record["requirements"]["revisions"][-1]["approval_evidence_refs"] = []
        record_path.write_text(
            json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        before_evidence = record_path.read_bytes()
        evidence = support.workspace.doctor_workspace(
            evidence_delivery,
            root=self.registry,
            work_id=evidence_work,
        )
        self.assertIn("EVIDENCE_MISSING", {item["code"] for item in evidence["diagnostics"]})
        self.assertEqual(before_evidence, record_path.read_bytes())

        recovery_repo = self.make_repo("doctor-recovery")
        recovery_work = "doctor-recovery-work"
        recovery_delivery = Path(self.start(recovery_repo, recovery_work)["worktree"])
        recovery_probe = support.workspace.probe_repository(recovery_delivery)
        knowledge_repo_root = (
            Path(tempfile.gettempdir()).resolve()
            / "project-knowledge"
            / "repos"
            / recovery_probe["repo_id"]
        )
        journal = knowledge_repo_root / "journals" / "doctor-fixture" / "journal.json"
        journal.parent.mkdir(parents=True, exist_ok=True)
        journal.write_text(
            json.dumps({"schema": "knowledge-journal/v1", "status": "in_progress"}),
            encoding="utf-8",
            newline="\n",
        )
        before_journal = journal.read_bytes()
        try:
            recovery = support.workspace.doctor_workspace(
                recovery_delivery,
                root=self.registry,
                work_id=recovery_work,
            )
            self.assertIn(
                "RECOVERY_REQUIRED",
                {item["code"] for item in recovery["diagnostics"]},
            )
            self.assertEqual(before_journal, journal.read_bytes())
        finally:
            shutil.rmtree(knowledge_repo_root, ignore_errors=True)

    def test_invalid_input_environment_failure_and_cli_exit_codes(self) -> None:
        import _delivery_doctor as delivery_doctor

        repo = self.make_repo("doctor-exits")
        invalid = support.workspace.doctor_workspace(
            repo,
            root=self.registry,
            work_id="INVALID WORK ID",
        )
        self.assertEqual("invalid", invalid["outcome"])
        self.assertEqual(2, support.workspace.doctor_exit_code(invalid))

        with mock.patch.object(
            delivery_doctor,
            "probe_repository",
            side_effect=support.workspace.DeliveryError(
                "git unavailable",
                code="GIT_COMMAND_FAILED",
            ),
        ):
            unavailable = support.workspace.doctor_workspace(repo, root=self.registry)
        self.assertEqual("unavailable", unavailable["outcome"])
        self.assertIn(
            "ENVIRONMENT_UNAVAILABLE",
            {item["code"] for item in unavailable["diagnostics"]},
        )
        self.assertEqual(4, support.workspace.doctor_exit_code(unavailable))

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = support.workspace.main(
                [
                    "doctor",
                    "--repo",
                    str(repo),
                    "--registry-root",
                    str(self.registry),
                ]
            )
        cli_report = json.loads(stdout.getvalue())
        self.assertEqual(3, exit_code)
        self.assertEqual("delivery-doctor/v1", cli_report["schema"])
        self.assertIn("NO_ACTIVE_RUN", {item["code"] for item in cli_report["diagnostics"]})

    def test_process_metrics_count_returns_and_leave_open_phases_unavailable(self) -> None:
        import _delivery_doctor as delivery_doctor

        events = [
            {
                "at": "2026-09-06T00:00:00Z",
                "from_phase": None,
                "to_phase": "workspace",
            },
            {
                "at": "2026-09-06T00:00:10Z",
                "from_phase": "workspace",
                "to_phase": "requirements",
            },
            {
                "at": "2026-09-06T00:00:20Z",
                "from_phase": "requirements",
                "to_phase": "planning",
            },
            {
                "at": "2026-09-06T00:00:30Z",
                "from_phase": "planning",
                "to_phase": "requirements",
            },
        ]
        report = delivery_doctor.summarize_process_metrics(events)
        self.assertEqual("delivery-process-metrics/v1", report["schema"])
        self.assertEqual(1, report["phase_return_count"])
        self.assertEqual(10.0, report["phase_durations_seconds"]["workspace"])
        self.assertEqual(10.0, report["phase_durations_seconds"]["planning"])
        self.assertIsNone(report["phase_durations_seconds"]["requirements"])
        self.assertIn(
            "phase_durations_seconds.requirements",
            report["unavailable_fields"],
        )
        self.assertIsNone(report["phase_durations_seconds"]["implementation"])
        self.assertIn(
            "phase_durations_seconds.implementation",
            report["unavailable_fields"],
        )


class WorkflowSpeedFixtureTests(unittest.TestCase):
    def _runner(self):
        path = (
            Path(__file__).resolve().parents[2]
            / "project-knowledge/scripts/run_full_suite.py"
        )
        spec = importlib.util.spec_from_file_location(
            "workflow_speed_full_suite_under_test", path
        )
        if spec is None or spec.loader is None:
            raise AssertionError("run_full_suite.py cannot be loaded")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module

    def test_parallel_workers_are_isolated_and_performance_is_last(self) -> None:
        runner = self._runner()
        behavior_path = (
            Path(__file__).resolve().parents[2]
            / "project-knowledge/scripts/test_behavior.py"
        )
        behavior_spec = importlib.util.spec_from_file_location(
            "workflow_speed_behavior_shards_under_test", behavior_path
        )
        if behavior_spec is None or behavior_spec.loader is None:
            raise AssertionError("test_behavior.py cannot be loaded")
        behavior = importlib.util.module_from_spec(behavior_spec)
        sys.modules[behavior_spec.name] = behavior
        behavior_spec.loader.exec_module(behavior)
        scenario_shards = [
            set(behavior.functional_shard_scenarios(index, 4))
            for index in range(1, 5)
        ]
        self.assertEqual(
            set(behavior.SCENARIOS) - set(behavior.SEQUENTIAL_PERFORMANCE_SCENARIOS),
            set().union(*scenario_shards),
        )
        self.assertEqual(
            sum(len(values) for values in scenario_shards),
            len(set().union(*scenario_shards)),
        )
        performance_scenarios = list(behavior.SEQUENTIAL_PERFORMANCE_SCENARIOS)
        self.assertEqual(
            set(behavior.SEQUENTIAL_PERFORMANCE_SCENARIOS)
            - set(behavior.RELEASE_ONLY_SCENARIOS),
            set(behavior.validation_profile_scenarios(performance_scenarios, "local")),
        )
        self.assertEqual(
            set(behavior.SEQUENTIAL_PERFORMANCE_SCENARIOS),
            set(behavior.validation_profile_scenarios(performance_scenarios, "release")),
        )
        self.assertEqual(
            set(behavior.SEQUENTIAL_PERFORMANCE_SCENARIOS),
            set(behavior.validation_profile_scenarios(performance_scenarios, None)),
        )

        bdd_command = {
            "command_id": "BDD-FULL",
            "arguments": [sys.executable, str(behavior_path)],
            "timeout": 900,
        }
        profiled_bdd = runner._profile_commands([bdd_command])
        self.assertEqual(4, sum(
            item["execution_class"] == "parallel_safe"
            for item in profiled_bdd
        ))
        self.assertEqual(1, sum(
            item["execution_class"] == "sequential_performance"
            for item in profiled_bdd
        ))
        self.assertTrue(
            all(item["logical_command_id"] == "BDD-FULL" for item in profiled_bdd)
        )
        local_bdd = runner._profile_commands([bdd_command], profile="local")
        release_bdd = runner._profile_commands([bdd_command], profile="release")
        local_performance = next(
            item for item in local_bdd if item["command_id"] == "BDD-PERFORMANCE"
        )
        release_performance = next(
            item for item in release_bdd if item["command_id"] == "BDD-PERFORMANCE"
        )
        self.assertEqual(
            ["--performance-only", "--validation-profile", "local"],
            local_performance["arguments"][-3:],
        )
        self.assertEqual(
            ["--performance-only", "--validation-profile", "release"],
            release_performance["arguments"][-3:],
        )
        delivery_command = {
            "command_id": "TEST-OWNER-DELIVERY-WORKSPACE",
            "arguments": [sys.executable, str(Path(__file__).resolve())],
            "timeout": 900,
        }
        profiled_delivery = runner._profile_commands([delivery_command])
        functional_shards = [
            item
            for item in profiled_delivery
            if item["execution_class"] == "parallel_safe"
        ]
        performance_shards = [
            item
            for item in profiled_delivery
            if item["execution_class"] == "sequential_performance"
        ]
        self.assertGreater(len(functional_shards), 1)
        self.assertEqual(1, len(performance_shards))
        self.assertEqual(
            set(runner.DELIVERY_FUNCTIONAL_CASES),
            {
                selector
                for item in functional_shards
                for selector in item["arguments"][2:]
            },
        )
        self.assertTrue(
            all(
                item["logical_command_id"]
                == "TEST-OWNER-DELIVERY-WORKSPACE"
                for item in profiled_delivery
            )
        )
        commands = [
            {
                "command_id": f"PARALLEL-{index}",
                "execution_class": "parallel_safe",
            }
            for index in range(3)
        ]
        commands.append(
            {
                "command_id": "PERFORMANCE",
                "execution_class": "sequential_performance",
            }
        )
        lock = threading.Lock()
        active = 0
        maximum_active = 0
        finished_parallel: set[str] = set()
        performance_observation: tuple[int, set[str]] | None = None

        def execute(command: dict[str, object]) -> dict[str, object]:
            nonlocal active, maximum_active, performance_observation
            if command["execution_class"] == "sequential_performance":
                with lock:
                    performance_observation = (active, set(finished_parallel))
                return {"status": "passed", "command_id": command["command_id"]}
            with lock:
                active += 1
                maximum_active = max(maximum_active, active)
            time.sleep(0.04)
            with lock:
                active -= 1
                finished_parallel.add(str(command["command_id"]))
            return {"status": "passed", "command_id": command["command_id"]}

        results = runner.execute_profile_schedule(commands, jobs=3, executor=execute)
        self.assertGreaterEqual(maximum_active, 2)
        self.assertEqual(
            (0, {"PARALLEL-0", "PARALLEL-1", "PARALLEL-2"}),
            performance_observation,
        )
        self.assertTrue(all(item["status"] == "passed" for item in results.values()))

        priority_commands = [
            {
                "command_id": "SHORT-A",
                "execution_class": "parallel_safe",
                "worker_index": 1,
                "schedule_priority": 0,
            },
            {
                "command_id": "LONG",
                "execution_class": "parallel_safe",
                "worker_index": 2,
                "schedule_priority": 100,
            },
            {
                "command_id": "SHORT-B",
                "execution_class": "parallel_safe",
                "worker_index": 3,
                "schedule_priority": 0,
            },
        ]
        starts: list[str] = []

        def record_start(command: dict[str, object]) -> dict[str, object]:
            with lock:
                starts.append(str(command["command_id"]))
            return {"status": "passed", "command_id": command["command_id"]}

        serial = runner.execute_profile_schedule(
            priority_commands,
            jobs=1,
            executor=record_start,
        )
        self.assertEqual(["LONG", "SHORT-A", "SHORT-B"], starts)
        starts.clear()
        parallel_results = runner.execute_profile_schedule(
            priority_commands,
            jobs=3,
            executor=record_start,
        )
        self.assertEqual(set(serial), set(parallel_results))
        self.assertEqual(
            {key: value["status"] for key, value in serial.items()},
            {key: value["status"] for key, value in parallel_results.items()},
        )

        fail_fast_commands = [
            {
                "command_id": f"FAILFAST-{index}",
                "execution_class": "parallel_safe",
                "worker_index": index,
            }
            for index in range(4)
        ]
        fail_fast_commands.append(
            {
                "command_id": "FAILFAST-PERFORMANCE",
                "execution_class": "sequential_performance",
                "worker_index": 5,
            }
        )
        started: list[str] = []

        def fail_first(command: dict[str, object]) -> dict[str, object]:
            started.append(str(command["command_id"]))
            if command["command_id"] == "FAILFAST-0":
                return {"status": "failed", "command_id": command["command_id"]}
            time.sleep(0.06)
            return {"status": "passed", "command_id": command["command_id"]}

        fail_fast = runner.execute_profile_schedule(
            fail_fast_commands,
            jobs=2,
            executor=fail_first,
        )
        self.assertEqual(["FAILFAST-0", "FAILFAST-1"], sorted(started))
        self.assertEqual("not_run", fail_fast["FAILFAST-2"]["status"])
        self.assertEqual("not_run", fail_fast["FAILFAST-3"]["status"])
        self.assertEqual("not_run", fail_fast["FAILFAST-PERFORMANCE"]["status"])

        with tempfile.TemporaryDirectory(prefix="workflow-worker-test-") as temporary:
            fixture_root = Path(temporary) / "fixtures"
            fixture_root.mkdir()
            environment_command = {
                "command_id": "ENV-A",
                "arguments": [
                    sys.executable,
                    "-c",
                    (
                        "import json,os; "
                        "print(json.dumps({'environment':{k:os.environ.get(k) "
                        "for k in ['TMP','TEMP','TMPDIR',"
                        "'KNOWLEDGE_TEST_WORKER_ROOT',"
                        "'KNOWLEDGE_TEST_REGISTRY_ROOT',"
                        "'MEGIN_RUNNER_VALIDATION_PROFILE']},"
                        "'arguments':__import__('sys').argv[1:]}))"
                    ),
                    "--fixture-root",
                    str(Path(".knowledge-test-tmp/fixtures")),
                ],
                "timeout": 30,
                "execution_class": "parallel_safe",
            }
            first = runner.execute_profile_item(
                environment_command,
                workspace=Path.cwd(),
                fixture_root=fixture_root,
                fixture_argument=Path(".knowledge-test-tmp/fixtures"),
                worker_index=1,
                validation_profile="local",
            )
            environment_command["command_id"] = "ENV-B"
            second = runner.execute_profile_item(
                environment_command,
                workspace=Path.cwd(),
                fixture_root=fixture_root,
                fixture_argument=Path(".knowledge-test-tmp/fixtures"),
                worker_index=2,
                validation_profile="release",
            )
            first_payload = json.loads(first["stdout"].decode("utf-8"))
            second_payload = json.loads(second["stdout"].decode("utf-8"))
            first_environment = first_payload["environment"]
            second_environment = second_payload["environment"]
            self.assertNotEqual(
                first_environment["KNOWLEDGE_TEST_WORKER_ROOT"],
                second_environment["KNOWLEDGE_TEST_WORKER_ROOT"],
            )
            self.assertEqual(
                "001", Path(first_environment["KNOWLEDGE_TEST_WORKER_ROOT"]).name
            )
            self.assertEqual(
                "002", Path(second_environment["KNOWLEDGE_TEST_WORKER_ROOT"]).name
            )
            self.assertEqual("t", Path(first_environment["TMP"]).name)
            self.assertEqual(
                "local", first_environment["MEGIN_RUNNER_VALIDATION_PROFILE"]
            )
            self.assertEqual(
                "release", second_environment["MEGIN_RUNNER_VALIDATION_PROFILE"]
            )
            self.assertEqual(
                "r", Path(first_environment["KNOWLEDGE_TEST_REGISTRY_ROOT"]).name
            )
            self.assertEqual(
                Path(first_environment["KNOWLEDGE_TEST_WORKER_ROOT"]) / "fixture",
                Path(first_payload["arguments"][1]),
            )
            self.assertEqual("passed", first["worker_cleanup"])
            self.assertEqual("passed", second["worker_cleanup"])
            self.assertEqual([], list(fixture_root.iterdir()))

    def test_delivery_fixture_profile_has_setup_body_and_cleanup(self) -> None:
        profile_parent = Path(tempfile.mkdtemp(prefix="delivery-profile-test-"))
        profile_path = profile_parent / "profile.json"

        class ProfiledFixture(support.DeliveryFixture):
            def runTest(self) -> None:
                self.make_repo("profiled-project")

        try:
            with mock.patch.dict(
                os.environ,
                {"DELIVERY_FIXTURE_PROFILE": str(profile_path)},
            ):
                result = unittest.TestResult()
                ProfiledFixture().run(result)
            self.assertTrue(result.wasSuccessful(), result.errors)
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            self.assertEqual("delivery-fixture-profile/v1", profile["schema"])
            self.assertEqual(1, len(profile["tests"]))
            sample = profile["tests"][0]
            for field in (
                "setup_seconds",
                "repository_setup_seconds",
                "body_seconds",
                "cleanup_seconds",
            ):
                self.assertIsInstance(sample[field], float)
                self.assertGreaterEqual(sample[field], 0.0)
            self.assertGreater(sample["repository_setup_seconds"], 0.0)
        finally:
            shutil.rmtree(profile_parent, ignore_errors=True)

    def test_profile_worker_uses_a_short_nested_git_fixture_prefix(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"KNOWLEDGE_TEST_WORKER_ROOT": str(Path.cwd() / "worker")},
        ):
            self.assertEqual("d-", support._fixture_prefix())
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual("delivery-orchestrator-test-", support._fixture_prefix())

    def test_nested_test_entrypoints_keep_their_parent_workers_isolated(self) -> None:
        runner = self._runner()
        workspace = Path.cwd()
        outer_value = os.environ.get("KNOWLEDGE_TEST_WORKER_ROOT")
        if outer_value:
            fixture_root = Path(outer_value) / "nested-workers"
        else:
            fixture_root = (
                workspace
                / ".knowledge-test-tmp"
                / f"nested-workers-{os.getpid()}-{time.time_ns()}"
            )
        fixture_root.mkdir(parents=True)
        query_script = (
            Path(__file__).resolve().parents[2]
            / "project-knowledge/scripts/test_query.py"
        )
        commands = [
            {
                "command_id": f"NESTED-QUERY-{index}",
                "logical_command_id": f"NESTED-QUERY-{index}",
                "arguments": [
                    sys.executable,
                    "-X",
                    "utf8",
                    "-B",
                    str(query_script),
                    "ChineseWorkflowQueryTests",
                ],
                "timeout": 60,
                "execution_class": "parallel_safe",
                "worker_index": index,
            }
            for index in (1, 2)
        ]
        try:
            results = runner.execute_profile_schedule(
                commands,
                jobs=2,
                executor=lambda command: runner.execute_profile_item(
                    command,
                    workspace=workspace,
                    fixture_root=fixture_root,
                    fixture_argument=Path(".knowledge-test-tmp/fixtures"),
                    worker_index=int(command["worker_index"]),
                ),
            )
            self.assertTrue(
                all(item["status"] == "passed" for item in results.values()),
                {
                    key: value.get("stderr", b"").decode(
                        "utf-8", errors="replace"
                    )
                    for key, value in results.items()
                },
            )
            self.assertEqual([], list(fixture_root.iterdir()))
        finally:
            shutil.rmtree(fixture_root, ignore_errors=True)


TEST_CASES = (
    DeliverySafetyTests,
    DeliveryTransitionTests,
    DeliveryBugOverlayTests,
    DeliveryTerminalContractTests,
    DeliveryWorktreeTests,
    UnifiedEntryAuthorizationTests,
    DeliveryPerformanceTests,
    DeliveryTransitionArchitectureTests,
    DeliveryDoctorTests,
    WorkflowSpeedFixtureTests,
)


def _test_ids(suite: unittest.TestSuite) -> list[str]:
    result: list[str] = []
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            result.extend(_test_ids(item))
        else:
            result.append(item.id().removeprefix("__main__."))
    return result


def _inventory() -> dict[str, object]:
    loader = unittest.defaultTestLoader
    tests = sorted(
        {
            test_id
            for case in TEST_CASES
            for test_id in _test_ids(loader.loadTestsFromTestCase(case))
        }
    )
    bindings = [
        {"bdd_id": bdd_id, "test": f"{case.__name__}.{method}"}
        for case in TEST_CASES
        for bdd_id, method in getattr(case, "BDD_BINDINGS", {}).items()
    ]
    return {
        "schema": "delivery-test-inventory/v1",
        "discovered": len(tests),
        "tests": tests,
        "bdd_bindings": sorted(bindings, key=lambda item: item["bdd_id"]),
    }


if __name__ == "__main__":
    if sys.argv[1:] == ["--list-tests"]:
        print(json.dumps(_inventory(), ensure_ascii=False, sort_keys=True))
    else:
        unittest.main(verbosity=2)
