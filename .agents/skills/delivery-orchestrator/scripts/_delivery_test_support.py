#!/usr/bin/env python3
"""Shared isolated fixtures for delivery-orchestrator tests."""

from __future__ import annotations

import concurrent.futures
import copy
import hashlib
import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from typing import Any, Sequence


SCRIPT = Path(__file__).with_name("delivery_workspace.py")
SPEC = importlib.util.spec_from_file_location("delivery_workspace", SCRIPT)
if SPEC is None or SPEC.loader is None:  # pragma: no cover - import infrastructure
    raise RuntimeError(f"cannot import {SCRIPT}")
workspace = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = workspace
SPEC.loader.exec_module(workspace)

PLANNING_TEST = SCRIPT.resolve().parents[2] / "technical-planning" / "scripts" / "_ready_fixture.py"
PLANNING_SPEC = importlib.util.spec_from_file_location("delivery_planning_fixture", PLANNING_TEST)
if PLANNING_SPEC is None or PLANNING_SPEC.loader is None:  # pragma: no cover - import infrastructure
    raise RuntimeError(f"cannot import {PLANNING_TEST}")
planning_fixture = importlib.util.module_from_spec(PLANNING_SPEC)
PLANNING_SPEC.loader.exec_module(planning_fixture)

REQUEST_SHA = hashlib.sha256(b"original delivery request").hexdigest()


def run(command: Sequence[str], *, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    environment = os.environ.copy()
    environment.update(
        {
            "GIT_AUTHOR_NAME": "Delivery Test",
            "GIT_AUTHOR_EMAIL": "delivery@example.invalid",
            "GIT_COMMITTER_NAME": "Delivery Test",
            "GIT_COMMITTER_EMAIL": "delivery@example.invalid",
            "GIT_CONFIG_NOSYSTEM": "1",
        }
    )
    completed = subprocess.run(
        list(command),
        cwd=cwd,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and completed.returncode != 0:
        raise AssertionError(
            f"command failed ({completed.returncode}): {command!r}\n"
            f"stdout={completed.stdout.decode('utf-8', 'replace')}\n"
            f"stderr={completed.stderr.decode('utf-8', 'replace')}"
        )
    return completed


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    return run(["git", "-C", str(repo), *args], check=check)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def file_bytes(root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if not relative.parts or relative.parts[0] == ".git" or not path.is_file():
            continue
        result[relative.as_posix()] = digest(path)
    return result


def git_path(repo: Path, name: str) -> Path:
    raw = git(repo, "rev-parse", "--path-format=absolute", "--git-path", name).stdout.decode().strip()
    return Path(raw)


def primary_snapshot(repo: Path) -> dict[str, Any]:
    status = git(
        repo,
        "--no-optional-locks",
        "status",
        "--porcelain=v2",
        "-z",
        "--untracked-files=all",
        "--ignore-submodules=none",
    ).stdout
    return {
        "head": git(repo, "rev-parse", "HEAD").stdout,
        "symbolic_head": git(repo, "symbolic-ref", "HEAD", check=False).stdout,
        "index": digest(git_path(repo, "index")),
        "status": status,
        "files": file_bytes(repo),
    }

class DeliveryFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="delivery-orchestrator-test-")
        self.root = Path(self.temporary.name)
        self.registry = self.root / "registry"
        self.implementation_run_dirs: list[Path] = []

    def tearDown(self) -> None:
        runs_root = (
            Path(tempfile.gettempdir()).resolve()
            / "implementation-execution"
            / "runs"
        )
        for run_dir in self.implementation_run_dirs:
            if run_dir.parent == runs_root and re.fullmatch(r"[0-9a-f]{64}", run_dir.name):
                shutil.rmtree(run_dir, ignore_errors=True)
        self.temporary.cleanup()

    def make_repo(self, name: str = "project") -> Path:
        repo = self.root / name
        run(["git", "init", "-b", "main", str(repo)])
        git(repo, "config", "core.autocrlf", "false")
        git(repo, "config", "user.name", "Delivery Test")
        git(repo, "config", "user.email", "delivery@example.invalid")
        (repo / "app.txt").write_text("baseline\n", encoding="utf-8", newline="\n")
        git(repo, "add", "app.txt")
        git(repo, "commit", "-m", "baseline")
        return repo

    def start(self, repo: Path, work_id: str = "work-test-001", generation: int = 1) -> dict[str, Any]:
        return workspace.start_workspace(
            repo,
            work_id,
            REQUEST_SHA,
            root=self.registry,
            generation=generation,
            knowledge_policy="legacy",
        )

    def start_required(
        self,
        repo: Path,
        work_id: str = "work-knowledge-required",
    ) -> dict[str, Any]:
        return workspace.start_workspace(
            repo,
            work_id,
            REQUEST_SHA,
            root=self.registry,
        )

    def assert_error(self, code: str, callback: Any) -> workspace.DeliveryError:
        with self.assertRaises(workspace.DeliveryError) as captured:
            callback()
        self.assertEqual(code, captured.exception.code, str(captured.exception))
        return captured.exception

    def record(self, repo: Path, work_id: str) -> dict[str, Any]:
        probe = workspace.probe_repository(repo)
        path = workspace.run_directory(self.registry, probe["repo_id"], work_id) / "run.json"
        return workspace.load_record(path)

    def transition(
        self,
        repo: Path,
        work_id: str,
        phase: str,
        status: str,
        event: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        evidence_refs = kwargs.pop("evidence_refs", [f"evidence/{event}.json"])
        return workspace.transition_record(
            repo,
            work_id,
            phase,
            status,
            event,
            evidence_refs,
            root=self.registry,
            **kwargs,
        )

    def persist_complete_implementation(
        self,
        delivery: Path,
        work_id: str,
        run_id: str,
        *,
        bug_verification_result: str | None = None,
        allow_preexisting_review_evidence: bool = False,
    ) -> tuple[str, str, str]:
        record = self.record(delivery, work_id)
        handoff_relative = record["plans"]["current_handoff_path"]
        handoff = json.loads(
            (delivery / Path(*handoff_relative.split("/"))).read_text(encoding="utf-8")
        )
        runs_root = (
            Path(tempfile.gettempdir()).resolve()
            / "implementation-execution"
            / "runs"
        )
        run_dir = runs_root / run_id
        if allow_preexisting_review_evidence:
            self.assertTrue(run_dir.is_dir(), f"preliminary implementation run is absent: {run_id}")
            existing = {
                path.relative_to(run_dir).as_posix()
                for path in run_dir.rglob("*")
                if path.is_file()
            }
            self.assertTrue(existing)
            self.assertTrue(
                all(
                    path == "run.json"
                    or path.startswith("reviews/preliminary-")
                    for path in existing
                ),
                existing,
            )
        else:
            self.assertFalse(run_dir.exists(), f"isolated implementation run already exists: {run_id}")
        review_round = 2 if allow_preexisting_review_evidence else 1
        review_root = f"reviews/round-{review_round}"
        review_relative = f"{review_root}/report.json"
        review_path = run_dir / Path(*review_relative.split("/"))
        review_path.parent.mkdir(parents=True)
        self.implementation_run_dirs.append(run_dir)
        outcomes = []
        raw_refs = []
        for command in handoff["commands"]:
            if command["purpose"] not in {"build-full", "test-full", "bdd-full", "governance", "ci"}:
                continue
            output_ref = f"{review_root}/outputs/{command['command_id']}.txt"
            outcomes.append(
                {
                    "command_id": command["command_id"],
                    "outcome": "passed",
                    "exit_code": 0,
                    "failure_count": 0,
                    "skipped_count": 0,
                    "output_ref": output_ref,
                    "not_run_reason": None,
                }
            )
            raw_refs.append(output_ref)
            output_path = run_dir / Path(*output_ref.split("/"))
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text("command passed\n", encoding="utf-8", newline="\n")
        coverage = [
            {
                "source_ref": source["source_id"],
                "obligation_ref": obligation,
                "bdd_refs": ["BDD-001"],
                "test_refs": ["TEST-001"],
                "wp_refs": source["wp_refs"],
                "code_evidence": ["diff://reviewed"],
                "result": "covered",
            }
            for source in handoff["sources"]
            for obligation in source["plan_refs"]
        ]
        bug_verification_relative: str | None = None
        bug_evidence_refs: list[str] = []
        bug_context = handoff.get("bug_context")
        if isinstance(bug_context, dict):
            result = bug_verification_result or bug_context["verification_target"]
            partial = result == "partial"
            failed = result == "failed"
            bug_verification_relative = (
                f"docs/bugs/{bug_context['bug_id']}/verifications/{work_id}.json"
            )
            bug_verification = {
                "schema": "bug-verification/v1",
                "bug_id": bug_context["bug_id"],
                "work_id": work_id,
                "result": result,
                "plan": {
                    "handoff_path": handoff_relative,
                    "candidate_revision": handoff["candidate"]["revision"],
                    "verification_target": bug_context["verification_target"],
                },
                "assessment": copy.deepcopy(bug_context["assessment"]),
                "original_reproduction": {
                    "pre_fix": {
                        "command_ref": None if partial else "CMD-BUG-REPRO-001",
                        "status": "inconclusive" if partial else "present",
                        "evidence_refs": ["commands/bug-pre.txt"],
                    },
                    "post_fix": {
                        "command_ref": None if partial else "CMD-BUG-REPRO-001",
                        "status": "inconclusive" if partial else ("present" if failed else "absent"),
                        "evidence_refs": ["commands/bug-post.txt"],
                    },
                },
                "regression": {
                    "bdd_refs": bug_context["regression_bdd_refs"],
                    "test_refs": bug_context["regression_test_refs"],
                    "red_evidence_refs": ["tests/regression-red.txt"],
                    "green_evidence_refs": ["tests/regression-green.txt"],
                },
                "proxy": {
                    "bdd_refs": bug_context["partial_safeguards"]["proxy_bdd_refs"] if partial else [],
                    "test_refs": bug_context["partial_safeguards"]["proxy_test_refs"] if partial else [],
                    "red_evidence_refs": ["tests/proxy-red.txt"] if partial else [],
                    "green_evidence_refs": ["tests/proxy-green.txt"] if partial else [],
                },
                "full_verification": copy.deepcopy(outcomes),
                "residual_risks": bug_context["partial_safeguards"]["residual_risks"] if partial else [],
                "follow_up": bug_context["partial_safeguards"]["follow_up"] if partial else [],
                "implementation_review_ref": review_relative,
                "summary": (
                    "Original symptom remains present after the attempted fix."
                    if failed
                    else "Proxy evidence passed; original symptom remains inconclusive."
                    if partial
                    else "Original symptom is absent after the root-cause fix."
                ),
                "created_at": "2026-08-30T00:00:00Z",
            }
            if failed:
                bug_verification["full_verification"][0].update(
                    {"outcome": "failed", "exit_code": 1, "failure_count": 1}
                )
            bug_evidence_refs = [
                *bug_verification["original_reproduction"]["pre_fix"]["evidence_refs"],
                *bug_verification["original_reproduction"]["post_fix"]["evidence_refs"],
                *bug_verification["regression"]["red_evidence_refs"],
                *bug_verification["regression"]["green_evidence_refs"],
                *bug_verification["proxy"]["red_evidence_refs"],
                *bug_verification["proxy"]["green_evidence_refs"],
            ]
            verification_path = delivery / Path(*bug_verification_relative.split("/"))
            verification_path.parent.mkdir(parents=True, exist_ok=True)
            verification_path.write_text(
                json.dumps(bug_verification, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
                newline="\n",
            )
        snapshot_relative = "diffs/reviewed-snapshot.json"
        snapshot = workspace._current_implementation_snapshot(record, handoff)
        snapshot_path = run_dir / Path(*snapshot_relative.split("/"))
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_text(
            json.dumps(snapshot, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        report = {
            "schema": "implementation-review/v1",
            "round": review_round,
            "verdict": "APPROVED",
            "snapshot_before": snapshot["snapshot_id"],
            "snapshot_after": snapshot["snapshot_id"],
            "attestation": {
                "agent_id": "fresh-reviewer",
                "fresh_session": True,
                "read_only": True,
                "implementation_conversation_received": False,
                "delegation_used": False,
                "write_actions": False,
            },
            "command_outcomes": outcomes,
            "raw_output_refs": raw_refs,
            "requirement_coverage": coverage,
            "findings": [],
            "summary": (
                "Implementation approved; BUG verification is partial and the original symptom remains inconclusive."
                if bug_verification_relative is not None
                and (bug_verification_result or bug_context["verification_target"]) == "partial"
                else "Independent verification approved the reviewed snapshot."
            ),
        }
        if bug_verification_relative is not None:
            report["bug_verification_ref"] = bug_verification_relative
            report["bug_verification_result"] = bug_verification_result or bug_context["verification_target"]
        review_path.write_text(
            json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        raw_response_relative = f"{review_root}/raw-response.txt"
        raw_response_path = run_dir / Path(*raw_response_relative.split("/"))
        raw_response_path.write_text("fresh reviewer response\n", encoding="utf-8", newline="\n")
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
            for outcome in outcomes
        ]
        main_output_refs = [
            entry[field]
            for entry in main_commands
            for field in ("stdout_ref", "stderr_ref")
        ]
        terminal_witness_steps = [
            "review_received",
            "snapshot_recomputed_before_persist",
            "snapshot_matched_before_persist",
            "report_persisted",
            "snapshot_recomputed_after_persist",
            "snapshot_matched_after_persist",
        ]
        terminal_witness_refs = [
            f"terminal/{sequence:02d}-{step}.json"
            for sequence, step in enumerate(terminal_witness_steps, 1)
        ]
        terminal_refs = [
            "source-manifest.json",
            "wp-ledger.json",
            "breaker.json",
            "commands/full-verification.json",
            *main_output_refs,
            *bug_evidence_refs,
            snapshot_relative,
            raw_response_relative,
            *raw_refs,
            review_relative,
            *terminal_witness_refs,
            "integrity/global-5-ready-source.json",
            *[
                f"integrity/{wp['wp_id']}/{boundary}-ready-source.json"
                for wp in handoff["work_packages"]
                for boundary in ("start", "complete")
            ],
        ]
        placeholder_payloads = {
            "source-manifest.json": handoff["sources"],
            "wp-ledger.json": {wp["wp_id"]: "Verified" for wp in handoff["work_packages"]},
            "breaker.json": {"schema": "implementation-breaker/v1", "findings": [], "global_no_progress_rounds": 0},
            "commands/full-verification.json": {"commands": main_commands},
            "evidence/capability.json": {
                "schema": "implementation-capability/v1",
                "run_id": run_id,
                "checks": {
                    "fresh_reviewer": "passed",
                    "git_workspace": "passed",
                    "toolchain": "passed",
                },
                "evidence_refs": ["evidence/capability-output.txt"],
            },
            "evidence/capability-output.txt": {"outcome": "passed"},
            "evidence/baseline.json": {
                "schema": "implementation-baseline/v1",
                "run_id": run_id,
                "outcome": "passed",
                "evidence_refs": ["evidence/baseline-output.txt"],
            },
            "evidence/baseline-output.txt": {"outcome": "passed"},
        }
        placeholder_payloads.update(
            {
                relative: {"stream": relative.rsplit(".", 2)[-2]}
                for relative in main_output_refs
            }
        )
        placeholder_payloads.update(
            {
                relative: {"evidence": relative}
                for relative in bug_evidence_refs
            }
        )
        witness_evidence = {
            "review_received": [raw_response_relative],
            "snapshot_recomputed_before_persist": [snapshot_relative],
            "snapshot_matched_before_persist": [snapshot_relative],
            "report_persisted": [raw_response_relative, *sorted(raw_refs), review_relative],
            "snapshot_recomputed_after_persist": [snapshot_relative],
            "snapshot_matched_after_persist": [snapshot_relative],
        }
        placeholder_payloads.update(
            {
                relative: {
                    "sequence": sequence,
                    "step": step,
                    "evidence_refs": witness_evidence[step],
                }
                for sequence, (step, relative) in enumerate(
                    zip(terminal_witness_steps, terminal_witness_refs),
                    1,
                )
            }
        )
        for relative, payload in placeholder_payloads.items():
            path = run_dir / Path(*relative.split("/"))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
                newline="\n",
            )
        integrity_refs = [
            *(f"integrity/global-{sequence}-ready-source.json" for sequence in range(1, 6)),
            *(
                f"integrity/{wp['wp_id']}/{boundary}-ready-source.json"
                for wp in handoff["work_packages"]
                for boundary in ("start", "complete")
            ),
        ]
        source_hashes = sorted(
            (
                {"ref": source["source_id"], "sha256": source["sha256"]}
                for source in handoff["sources"]
            ),
            key=lambda item: item["ref"],
        )
        for relative in integrity_refs:
            path = run_dir / Path(*relative.split("/"))
            path.parent.mkdir(parents=True, exist_ok=True)
            match = re.fullmatch(r"integrity/global-(\d+)-ready-source\.json", relative)
            transition_sequence = int(match.group(1)) if match else 5
            path.write_text(
                json.dumps(
                    {
                        "schema": "implementation-integrity/v1",
                        "scope": relative,
                        "attempt_id": "attempt-1",
                        "transition_sequence": transition_sequence,
                        "ready_sha256": workspace.sha256_bytes(workspace.canonical_json(handoff)),
                        "source_hashes": source_hashes,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
                newline="\n",
            )
        generation = record["generations"][-1]
        ledger = {
            "schema": "implementation-ledger/v1",
            "run_id": run_id,
            "binding": {
                "repo_id": record["repo_id"],
                "canonical_worktree": generation["canonical_worktree"],
                "worktree_key": generation["worktree_key"],
                "branch": generation["branch"],
                "initial_base_sha": generation["base_sha"],
                "run_id": run_id,
            },
            "handoff_path": handoff_relative,
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
                    "candidate_revision": handoff["candidate"]["revision"],
                    "state": "Complete",
                    "wp_states": {wp["wp_id"]: "Verified" for wp in handoff["work_packages"]},
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
        (run_dir / "run.json").write_text(
            json.dumps(ledger, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        return (
            f"implementation:runs/{run_id}/run.json",
            f"implementation:{review_relative}",
            f"implementation:{snapshot_relative}",
        )

    def enter_requirements(self, delivery: Path, work_id: str) -> None:
        self.transition(delivery, work_id, "requirements", "active", "requirements_started")
        self.transition(delivery, work_id, "requirements", "awaiting_user", "requirements_candidate")

    def approve_requirements(self, delivery: Path, work_id: str, revision: int = 1) -> tuple[str, str]:
        name = "requirements.md" if revision == 1 else f"requirements-{revision}.md"
        relative = f"docs/work/{work_id}/{name}"
        path = delivery / Path(*relative.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# Requirements {revision}\n\nStatus: Ready\n", encoding="utf-8", newline="\n")
        value = digest(path)
        self.transition(
            delivery,
            work_id,
            "planning",
            "active",
            f"requirements_{revision}_approved",
            requirements_path=relative,
            requirements_sha256=value,
            requirements_approval_refs=[f"conversation:req-{revision}"],
        )
        return relative, value

    def ready_handoff(
        self,
        delivery: Path,
        work_id: str,
        requirements_path: str,
        requirements_sha256: str,
        revision: int = 1,
        bug_verification_target: str = "verified",
    ) -> tuple[str, str, str]:
        directory = "plan" if revision == 1 else f"plan-{revision}"
        root = delivery / "docs" / "work" / work_id / directory
        root.mkdir(parents=True, exist_ok=True)
        plan = root / "plan.md"
        plan.write_text(f"# Ready plan {revision}\n", encoding="utf-8", newline="\n")
        relative_handoff = f"docs/work/{work_id}/{directory}/handoff.json"
        evidence = f"conversation:plan-{revision}"
        record = self.record(delivery, work_id)
        handoff: dict[str, Any] = copy.deepcopy(planning_fixture.ready_example())
        handoff["candidate"]["revision"] = f"candidate-{revision}"
        handoff["approval"] = {
            "status": "Ready",
            "actor": "user",
            "confirmed_at": "2026-08-30T00:00:00Z",
            "evidence": evidence,
        }
        handoff["planning_baseline"] = {
            "repo_id": record["repo_id"],
            "head_sha": record["generations"][-1]["base_sha"],
            "status_sha256": "0" * 64,
        }
        plan_relative = f"docs/work/{work_id}/{directory}/plan.md"
        handoff["primary_plan"] = {"path": plan_relative, "sha256": digest(plan)}
        handoff["artifacts"] = [
            {
                "path": plan_relative,
                "role": "primary",
                "approval_status": "Ready",
                "sha256": digest(plan),
            },
            {
                "path": relative_handoff,
                "role": "handoff",
                "approval_status": "Ready",
                "sha256": None,
            },
        ]
        handoff["sources"][0].update(
            {
                "kind": "spec",
                "location": requirements_path,
                "revision": str(revision),
                "sha256": requirements_sha256,
            }
        )
        if record.get("work_kind") == "bug":
            assessment = record["bugs"]["assessments"][-1]
            handoff["sources"].append(
                {
                    "source_id": "SRC-BUG-001",
                    "kind": "bug",
                    "location": assessment["path"],
                    "revision": "1",
                    "sha256": assessment["sha256"],
                    "plan_refs": ["REQ-001"],
                    "wp_refs": ["WP-001"],
                }
            )
            handoff["work_packages"][0]["source_refs"].append("SRC-BUG-001")
            for contract in handoff["contract_index"]:
                if contract["contract_id"] in {"REQ-001", "BDD-001", "TEST-001", "WP-001"}:
                    contract["source_refs"].append("SRC-BUG-001")
            handoff["commands"].append(
                {
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
                    "success_criteria": ["distinguishes symptom present from absent"],
                    "completeness_criteria": ["original symptom oracle executed"],
                    "absence_evidence": [],
                }
            )
            handoff["contract_index"].append(
                {
                    "contract_id": "CMD-BUG-REPRO-001",
                    "kind": "command",
                    "source_refs": ["SRC-001", "SRC-BUG-001"],
                    "wp_refs": ["WP-001"],
                }
            )
            handoff["work_packages"][0]["contract_refs"].append("CMD-BUG-REPRO-001")
            handoff["work_packages"][0]["command_refs"].append("CMD-BUG-REPRO-001")
            handoff["bug_context"] = {
                "bug_id": assessment["bug_id"],
                "assessment": {
                    "path": assessment["path"],
                    "sha256": assessment["sha256"],
                    "markdown_path": assessment["markdown_path"],
                    "markdown_sha256": assessment["markdown_sha256"],
                },
                "reproduction_status": "reproduced" if bug_verification_target == "verified" else "not-reproduced",
                "root_cause_status": "confirmed" if bug_verification_target == "verified" else "hypothesized",
                "root_cause_confidence": "high" if bug_verification_target == "verified" else "low",
                "verification_target": bug_verification_target,
                "original_reproduction_command_ref": "CMD-BUG-REPRO-001" if bug_verification_target == "verified" else None,
                "regression_bdd_refs": ["BDD-001"],
                "regression_test_refs": ["TEST-001"],
                "partial_safeguards": {
                    "reason": None if bug_verification_target == "verified" else "Original symptom is not reproducible.",
                    "proxy_bdd_refs": [] if bug_verification_target == "verified" else ["BDD-001"],
                    "proxy_test_refs": [] if bug_verification_target == "verified" else ["TEST-001"],
                    "residual_risks": [] if bug_verification_target == "verified" else ["Original symptom may persist outside the proxy seam."],
                    "follow_up": [] if bug_verification_target == "verified" else ["Verify the original journey manually in staging."],
                },
            }
        handoff["revision_impact"]["revision"] = f"candidate-{revision}"
        payload = workspace._ready_payload_sha256(handoff)
        handoff["candidate"]["payload_sha256"] = payload
        (root / "handoff.json").write_text(
            json.dumps(handoff, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        return relative_handoff, payload, evidence

    def approve_plan(
        self,
        delivery: Path,
        work_id: str,
        requirements_path: str,
        requirements_sha256: str,
        revision: int = 1,
        bug_verification_target: str = "verified",
    ) -> tuple[str, str]:
        self.transition(delivery, work_id, "planning", "awaiting_user", f"plan_{revision}_candidate")
        handoff, payload, evidence = self.ready_handoff(
            delivery,
            work_id,
            requirements_path,
            requirements_sha256,
            revision,
            bug_verification_target,
        )
        self.transition(
            delivery,
            work_id,
            "implementation",
            "active",
            f"plan_{revision}_approved",
            handoff_path=handoff,
            candidate_revision=f"candidate-{revision}",
            payload_sha256=payload,
            plan_approval_refs=[evidence],
        )
        return handoff, payload
