from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path
import importlib.util


SCRIPT = Path(__file__).parents[1] / "scripts" / "megin.py"
# Explicit legacy-token allowlist: these values belong only to migration
# fixtures and must not leak into the normal Megin lifecycle tests.
MIGRATION_LEGACY_ALLOWLIST = {
    "config_schema": "sdlc-project/v1",
    "plugin": "sdlc",
    "config_dir": ".sdlc",
    "capability_schema": "sdlc-capability/v1",
    "writer_report_schema": "sdlc-writer-report/v1",
    "review_report_schema": "sdlc-review-report/v1",
}
_SPEC = importlib.util.spec_from_file_location("megin_engine", SCRIPT)
assert _SPEC and _SPEC.loader
ENGINE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ENGINE)


class PortableCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.repo = self.root / "project with 中文"
        self.repo.mkdir()
        self.env = os.environ.copy()
        self.env["MEGIN_STATE_ROOT"] = str(self.root / "state")
        self.previous_state_root = os.environ.get("MEGIN_STATE_ROOT")
        os.environ["MEGIN_STATE_ROOT"] = self.env["MEGIN_STATE_ROOT"]
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "megin@example.invalid")
        self.git("config", "user.name", "Megin Test")
        (self.repo / "README.md").write_text("seed\n", encoding="utf-8")
        self.git("add", "README.md")
        self.git("commit", "-qm", "seed")

    def tearDown(self) -> None:
        # Windows keeps a worktree directory registered in the source repo until
        # it is explicitly removed; remove those registrations before deleting
        # the temporary repository so later cases can create paths reliably.
        try:
            entries = self.git("worktree", "list", "--porcelain").splitlines()
            for line in entries:
                if line.startswith("worktree "):
                    candidate = Path(line[len("worktree "):].strip())
                    if candidate.resolve() != self.repo.resolve() and candidate.exists():
                        subprocess.run(["git", "worktree", "remove", "--force", str(candidate)], cwd=str(self.repo), env=self.env, capture_output=True, text=True)
        except (AssertionError, OSError):
            pass
        if self.previous_state_root is None:
            os.environ.pop("MEGIN_STATE_ROOT", None)
        else:
            os.environ["MEGIN_STATE_ROOT"] = self.previous_state_root
        self.temp.cleanup()

    def git(self, *args: str, cwd: Path | None = None) -> str:
        result = subprocess.run(["git", *args], cwd=str(cwd or self.repo), env=self.env, text=True, encoding="utf-8", capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def cli(self, *args: str, expect: int = 0) -> dict:
        result = subprocess.run([sys.executable, str(SCRIPT), *args], env=self.env, text=True, encoding="utf-8", capture_output=True)
        self.assertEqual(result.returncode, expect, result.stderr)
        return json.loads(result.stdout)

    def cli_raw(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, str(SCRIPT), *args], env=self.env, text=True, encoding="utf-8", capture_output=True)

    def set_state_root(self, path: Path) -> None:
        self.env["MEGIN_STATE_ROOT"] = str(path)
        os.environ["MEGIN_STATE_ROOT"] = str(path)

    def legacyize_config(self) -> None:
        config_dir = self.repo / ".megin"
        config_path = config_dir / "config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        config["schema"] = MIGRATION_LEGACY_ALLOWLIST["config_schema"]
        config["plugin"] = MIGRATION_LEGACY_ALLOWLIST["plugin"]
        config["plugin_version"] = "0.1.0"
        legacy_dir = self.repo / MIGRATION_LEGACY_ALLOWLIST["config_dir"]
        config_dir.rename(legacy_dir)
        (legacy_dir / "config.json").write_text(json.dumps(config, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    def prepare_legacy_run(self) -> tuple[Path, Path, Path]:
        source_root = self.root / "legacy-state"
        target_root = self.root / "megin-state"
        self.set_state_root(source_root)
        self.cli("init", "--repo", str(self.repo))
        pending = self.cli(
            "start", "--repo", str(self.repo), "--request", "修正 README 文字",
            "--work-id", "work-migrate", "--task-class", "small", "--allowed-path", "README.md",
        )
        state_path = Path(pending["state_path"])
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["plugin"] = MIGRATION_LEGACY_ALLOWLIST["plugin"]
        state["plugin_version"] = "0.1.0"
        state_path.write_text(json.dumps(state, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        self.legacyize_config()
        return source_root, target_root, state_path

    def writer_complete(self, work_id: str) -> dict:
        status = self.cli("status", "--repo", str(self.repo), "--work-id", work_id)
        assignment = status["current"]
        worktree = Path(status["worktree"])
        paths, snapshot = ENGINE.status_paths(worktree)
        report_path = self.root / f"{work_id}-writer-report.json"
        report_path.write_text(json.dumps({
            "schema": "megin-writer-report/v1",
            "work_id": work_id,
            "assignment_id": assignment["assignment_id"],
            "assignment_sha256": assignment["assignment_sha256"],
            "writer_id": assignment["writer_id"],
            "session_id": assignment["session_id"],
            "ticket_sha256": assignment["ticket_sha256"],
            "status": "completed",
            "changed_paths": paths,
            "snapshot": snapshot,
            "tests": [{"command": (assignment.get("focused_commands") or assignment.get("test_commands") or ["focused"])[0], "status": "passed"}],
        }, ensure_ascii=False), encoding="utf-8")
        return self.cli(
            "resume", "--repo", str(self.repo), "--work-id", work_id,
            "--writer-id", assignment["writer_id"], "--writer-ticket", assignment["ticket_sha256"],
            "--writer-report", str(report_path), "--writer-complete",
        )

    def reviewer_report(self, work_id: str, verdict: str = "APPROVED", reviewer: str = "fresh-reviewer", session: str | None = None, findings: list[dict[str, str]] | None = None) -> Path:
        status = self.cli("status", "--repo", str(self.repo), "--work-id", work_id)
        assignment = status["current"]
        worktree = Path(status["worktree"])
        paths, snapshot = ENGINE.status_paths(worktree)
        state, _ = ENGINE.load_state(self.repo, work_id)
        product_snapshot = ENGINE.working_tree_snapshot(worktree, exclude=state["knowledge"].get("scope", []))
        session = session or f"reviewer:{reviewer}"
        report_path = self.root / f"{work_id}-{assignment['assignment_id']}-{session.replace(':', '-')}-review.json"
        commands = list(dict.fromkeys(
            list(assignment.get("focused_commands", []))
            + list(assignment.get("related_commands", []))
            + list(assignment.get("full_commands", []))
        )) or ["review"]
        test_evidence = []
        for index, command in enumerate(commands, 1):
            evidence_path = self.root / f"{work_id}-{assignment['assignment_id']}-review-evidence-{index}.log"
            evidence = f"review evidence for {command}\n".encode("utf-8")
            evidence_path.write_bytes(evidence)
            test_evidence.append({
                "command": command,
                "status": "passed",
                "evidence_path": str(evidence_path),
                "output_sha256": ENGINE.digest_bytes(evidence),
                "output_bytes": len(evidence),
                "input_snapshot": snapshot,
                "output_snapshot": snapshot,
            })
        report_path.write_text(json.dumps({
            "schema": "megin-review-report/v1",
            "work_id": work_id,
            "assignment_id": assignment["assignment_id"],
            "assignment_sha256": assignment["assignment_sha256"],
            "reviewer_id": reviewer,
            "reviewer_session": session,
            "verdict": verdict,
            "snapshot": snapshot,
            "product_snapshot": product_snapshot,
            "paths": paths,
            "requirements_verdict": verdict,
            "quality_verdict": verdict,
            "findings": findings or [],
            "test_evidence": test_evidence,
        }, ensure_ascii=False), encoding="utf-8")
        return report_path

    def review(self, work_id: str, verdict: str = "APPROVED", reviewer: str = "fresh-reviewer", session: str | None = None, findings: list[dict[str, str]] | None = None) -> dict:
        status = self.cli("status", "--repo", str(self.repo), "--work-id", work_id)
        assignment = status["current"]
        report = self.reviewer_report(work_id, verdict, reviewer, session, findings)
        return self.cli(
            "resume", "--repo", str(self.repo), "--work-id", work_id,
            "--review-verdict", verdict, "--reviewer-id", reviewer,
            "--reviewer-session", session or f"reviewer:{reviewer}", "--review-report", str(report),
        )

    def knowledge_report(self, work_id: str, reviewer: str = "knowledge-reviewer", session: str = "knowledge:1") -> Path:
        state_result = self.cli("status", "--repo", str(self.repo), "--work-id", work_id)
        state, state_path = ENGINE.load_state(self.repo, work_id)
        worktree = Path(state_result["worktree"])
        candidate = ENGINE.create_knowledge_candidate(state, worktree)
        ENGINE.save_state(state, state_path)
        state, _ = ENGINE.load_state(self.repo, work_id)
        snapshot = ENGINE.knowledge_snapshot(worktree, state["knowledge"]["scope"])
        report_path = self.root / f"{work_id}-knowledge-review.json"
        report_path.write_text(json.dumps({
            "schema": "megin-knowledge-review/v1",
            "work_id": work_id,
            "reviewer_id": reviewer,
            "reviewer_session": session,
            "candidate_sha256": state["knowledge"]["candidate_sha256"],
            "scope": state["knowledge"]["scope"],
            "snapshot_before": ENGINE.knowledge_snapshot(worktree, state["knowledge"]["scope"]),
            "snapshot_after": snapshot,
            "status": "reviewed",
            "test_evidence": [{"command": (state["approval"]["scope"].get("test_commands") or ["knowledge-lint"])[0], "status": "passed"}],
            "claim_evidence": [{"path": claim.get("path"), "command": f"claim:{claim.get('path')}", "status": "passed"} for claim in candidate.get("claims", [])],
        }, ensure_ascii=False), encoding="utf-8")
        return report_path

    def test_classification_and_read_only_do_not_create_run(self) -> None:
        output = self.cli("classify", "--request", "請檢視目前流程並提供評估")
        self.assertEqual(output["task_class"], "read_only")
        self.cli("init", "--repo", str(self.repo))
        output = self.cli("start", "--repo", str(self.repo), "--request", "請檢視目前流程")
        self.assertFalse(output["run_created"])
        self.assertEqual(list((self.root / "state").rglob("*.json")), [])

    def test_small_task_requires_one_approval_then_creates_worktree(self) -> None:
        self.cli("init", "--repo", str(self.repo), "--test-command", "python -c 'print(1)'")
        pending = self.cli("start", "--repo", str(self.repo), "--request", "修正 README 文字", "--work-id", "work-small", "--task-class", "small", "--allowed-path", "README.md")
        self.assertEqual(pending["status"], "awaiting_approval")
        active = self.cli("resume", "--repo", str(self.repo), "--work-id", "work-small", "--approve", "--approval-ref", "user:small", "--allowed-path", "README.md")
        self.assertEqual(active["status"], "active")
        self.assertEqual(active["phase"], "implementation")
        self.assertTrue(Path(active["worktree"]).exists())
        self.assertEqual(active["current"]["writer"], "implementation-writer")

    def test_finish_only_commits_approved_paths_and_is_resumable(self) -> None:
        self.cli("init", "--repo", str(self.repo), "--test-command", "python -c 'print(1)'")
        self.cli("start", "--repo", str(self.repo), "--request", "修正 README 文字", "--work-id", "work-finish", "--task-class", "small", "--approve", "--allowed-path", "README.md")
        status = self.cli("status", "--repo", str(self.repo), "--work-id", "work-finish")
        worktree = Path(status["worktree"])
        (worktree / "README.md").write_text("changed\n", encoding="utf-8")
        self.writer_complete("work-finish")
        self.review("work-finish", reviewer="fresh-1")
        result = self.cli("finish", "--repo", str(self.repo), "--work-id", "work-finish")
        self.assertEqual(result["publication"], "publication_pending")
        self.assertEqual(result["status"], "active")
        validation = subprocess.run([sys.executable, str(SCRIPT.parent / "validate.py"), "--state", result["state_path"]], env=self.env, text=True, encoding="utf-8", capture_output=True)
        self.assertEqual(validation.returncode, 0, validation.stdout + validation.stderr)
        commit_count = self.git("rev-list", "--count", "HEAD", cwd=worktree).strip()
        self.assertEqual(commit_count, "2")
        again = self.cli("finish", "--repo", str(self.repo), "--work-id", "work-finish")
        self.assertEqual(again["commit"], result["commit"])
        self.assertEqual(self.git("rev-list", "--count", "HEAD", cwd=worktree).strip(), "2")

    def test_large_requires_requirements_and_plan(self) -> None:
        self.cli("init", "--repo", str(self.repo))
        pending = self.cli("start", "--repo", str(self.repo), "--request", "新增 API 契約與資料庫 schema", "--work-id", "work-large", "--task-class", "large", "--allowed-path", "README.md")
        self.assertEqual(pending["phase"], "requirements")
        planning = self.cli("resume", "--repo", str(self.repo), "--work-id", "work-large", "--approve", "requirements", "--requirements-approval-ref", "user:req")
        self.assertEqual(planning["phase"], "planning")
        active = self.cli("resume", "--repo", str(self.repo), "--work-id", "work-large", "--approve", "plan", "--plan-approval-ref", "user:plan")
        self.assertEqual(active["phase"], "implementation")

    def test_small_scope_can_be_escalated_without_reusing_approval(self) -> None:
        self.cli("init", "--repo", str(self.repo))
        self.cli("start", "--repo", str(self.repo), "--request", "修正 README 文字", "--work-id", "work-escalate", "--task-class", "small", "--allowed-path", "README.md", "--approve")
        pending = self.cli("resume", "--repo", str(self.repo), "--work-id", "work-escalate", "--escalate", "--allowed-path", "src/new.py")
        self.assertEqual(pending["task_class"], "large")
        self.assertEqual(pending["phase"], "requirements")
        self.assertEqual(pending["approval"], "pending")
        self.assertEqual(pending["status"], "awaiting_approval")

    def test_scope_digest_drift_is_fail_closed(self) -> None:
        self.cli("init", "--repo", str(self.repo))
        pending = self.cli("start", "--repo", str(self.repo), "--request", "修正 README 文字", "--work-id", "work-drift", "--task-class", "small", "--allowed-path", "README.md")
        state_path = Path(pending["state_path"])
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["approval"]["scope"]["allowed_paths"] = ["other.txt"]
        state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        result = self.cli_raw("status", "--repo", str(self.repo), "--work-id", "work-drift")
        self.assertEqual(result.returncode, 2)
        self.assertIn("digest", result.stderr)

    def test_review_finding_returns_to_a_new_writer_assignment(self) -> None:
        self.cli("init", "--repo", str(self.repo))
        self.cli("start", "--repo", str(self.repo), "--request", "修正 README 文字", "--work-id", "work-review-loop", "--task-class", "small", "--allowed-path", "README.md", "--approve")
        status = self.cli("status", "--repo", str(self.repo), "--work-id", "work-review-loop")
        worktree = Path(status["worktree"])
        (worktree / "README.md").write_text("changed\n", encoding="utf-8")
        self.writer_complete("work-review-loop")
        changed = self.review("work-review-loop", verdict="CHANGES_REQUIRED", reviewer="fresh-1", findings=[{"key": "coverage", "text": "add coverage"}])
        self.assertEqual(changed["phase"], "implementation")
        self.assertEqual(changed["tasks"][0]["status"], "needs_revision")
        self.assertEqual(changed["current"]["status"], "active")
        self.writer_complete("work-review-loop")
        current = self.cli("status", "--repo", str(self.repo), "--work-id", "work-review-loop")
        self.assertEqual(current["current"]["assignment_id"], "assignment-2")

    def test_repeated_unchanged_review_finding_trips_no_progress_breaker(self) -> None:
        self.cli("init", "--repo", str(self.repo))
        active = self.cli(
            "start", "--repo", str(self.repo), "--request", "修正 README 文字",
            "--work-id", "work-breaker", "--task-class", "small", "--allowed-path", "README.md", "--approve",
        )
        worktree = Path(active["worktree"])
        (worktree / "README.md").write_text("changed\n", encoding="utf-8")
        self.writer_complete("work-breaker")
        for round_number in (1, 2):
            self.review(
                "work-breaker", verdict="CHANGES_REQUIRED", reviewer="fresh-reviewer",
                session=f"review:{round_number}", findings=[{"key": "same-finding", "text": "same finding" if round_number == 1 else "same finding with revised wording"}],
            )
            self.writer_complete("work-breaker")
        blocked = self.review(
            "work-breaker", verdict="CHANGES_REQUIRED", reviewer="fresh-reviewer",
            session="review:3", findings=[{"key": "same-finding", "text": "same finding"}],
        )
        self.assertEqual(blocked["status"], "blocked")
        self.assertEqual(blocked["review_no_progress_count"], 2)
        self.assertEqual(blocked["current"]["assignment_id"], "assignment-3")

    def test_approval_gate_mutation_and_candidate_tamper_fail_closed(self) -> None:
        self.cli("init", "--repo", str(self.repo))
        pending = self.cli("start", "--repo", str(self.repo), "--request", "新增 API 契約與資料庫 schema", "--work-id", "work-binding", "--task-class", "large", "--allowed-path", "README.md")
        state_path = Path(pending["state_path"])
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["approval"]["status"] = "approved"
        state["approval"]["approved_stages"] = ["requirements", "plan"]
        state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        result = self.cli_raw("status", "--repo", str(self.repo), "--work-id", "work-binding")
        self.assertEqual(result.returncode, 2)
        self.assertIn("digest", result.stderr)

    def test_writer_ticket_and_reviewer_independence_are_enforced(self) -> None:
        self.cli("init", "--repo", str(self.repo))
        active = self.cli("start", "--repo", str(self.repo), "--request", "修正 README 文字", "--work-id", "work-ticket", "--task-class", "small", "--allowed-path", "README.md", "--approve")
        ticket = active["current"]["ticket_sha256"]
        worktree = Path(active["worktree"])
        (worktree / "README.md").write_text("changed\n", encoding="utf-8")
        wrong = self.cli_raw("resume", "--repo", str(self.repo), "--work-id", "work-ticket", "--writer-id", "another-writer", "--writer-ticket", ticket, "--writer-complete")
        self.assertEqual(wrong.returncode, 2)
        self.writer_complete("work-ticket")
        report = self.reviewer_report("work-ticket", reviewer="implementation-writer")
        same = self.cli_raw("resume", "--repo", str(self.repo), "--work-id", "work-ticket", "--review-approved", "--reviewer-id", "implementation-writer", "--review-report", str(report))
        self.assertEqual(same.returncode, 2)

    def test_knowledge_candidate_is_reviewed_and_promoted_with_evidence(self) -> None:
        self.cli("init", "--repo", str(self.repo), "--test-command", "python -c 'print(1)'")
        active = self.cli("start", "--repo", str(self.repo), "--request", "修正 README 文字", "--work-id", "work-knowledge", "--task-class", "small", "--allowed-path", "README.md", "--knowledge-path", "README.md", "--approve")
        worktree = Path(active["worktree"])
        (worktree / "README.md").write_text("changed\n", encoding="utf-8")
        self.writer_complete("work-knowledge")
        self.review("work-knowledge", reviewer="fresh-reviewer")
        report = self.knowledge_report("work-knowledge")
        reviewed = self.cli("resume", "--repo", str(self.repo), "--work-id", "work-knowledge", "--verified", "--knowledge-reviewed", "--reviewer-id", "knowledge-reviewer", "--reviewer-session", "knowledge:1", "--knowledge-report", str(report))
        self.assertEqual(reviewed["knowledge"], "reviewed")
        state = json.loads(Path(reviewed["state_path"]).read_text(encoding="utf-8"))
        self.assertTrue(state["knowledge"]["candidate_path"])
        self.assertEqual(state["knowledge"]["lint"]["status"], "passed")
        finished = self.cli("finish", "--repo", str(self.repo), "--work-id", "work-knowledge")
        self.assertEqual(finished["knowledge"], "promoted")

    def test_small_approval_binds_a_versioned_design_candidate(self) -> None:
        self.cli("init", "--repo", str(self.repo))
        active = self.cli(
            "start", "--repo", str(self.repo), "--request", "修正 README 文字",
            "--work-id", "work-design", "--task-class", "small", "--allowed-path", "README.md", "--approve",
        )
        state = json.loads(Path(active["state_path"]).read_text(encoding="utf-8"))
        candidate = state["candidates"]["design"]
        self.assertEqual(candidate["status"], "approved")
        self.assertTrue(Path(candidate["path"]).exists())
        self.assertEqual(candidate["revision"], "candidate-1")

    def test_large_approval_gates_are_separate_state_transitions(self) -> None:
        self.cli("init", "--repo", str(self.repo))
        result = self.cli_raw(
            "start", "--repo", str(self.repo), "--request", "新增 API 契約與資料庫 schema",
            "--work-id", "work-two-gates", "--task-class", "large", "--allowed-path", "README.md",
            "--approve", "requirements", "--approve", "plan",
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("separate", result.stderr)
        self.assertEqual(list((self.root / "state").rglob("work-two-gates.json")), [])

    def test_approval_stage_must_match_task_policy(self) -> None:
        self.cli("init", "--repo", str(self.repo))
        small = self.cli_raw(
            "start", "--repo", str(self.repo), "--request", "修正 README 文字",
            "--work-id", "work-small-stage", "--task-class", "small", "--allowed-path", "README.md",
            "--approve", "plan",
        )
        self.assertEqual(small.returncode, 2)
        self.assertIn("do not apply", small.stderr)
        large = self.cli_raw(
            "start", "--repo", str(self.repo), "--request", "新增 API 契約與資料庫 schema",
            "--work-id", "work-large-stage", "--task-class", "large", "--allowed-path", "README.md",
            "--approve", "integrated",
        )
        self.assertEqual(large.returncode, 2)
        self.assertIn("do not apply", large.stderr)

    def test_verified_flag_runs_commands_and_records_integrity_digest(self) -> None:
        self.cli("init", "--repo", str(self.repo), "--test-command", "python -c 'print(1)'")
        active = self.cli(
            "start", "--repo", str(self.repo), "--request", "修正 README 文字",
            "--work-id", "work-verified", "--task-class", "small", "--allowed-path", "README.md", "--approve",
        )
        worktree = Path(active["worktree"])
        (worktree / "README.md").write_text("verified\n", encoding="utf-8")
        self.writer_complete("work-verified")
        self.review("work-verified", reviewer="fresh-verified")
        verified = self.cli("resume", "--repo", str(self.repo), "--work-id", "work-verified", "--verified")
        state = json.loads(Path(verified["state_path"]).read_text(encoding="utf-8"))
        self.assertEqual(state["verification"]["status"], "passed")
        self.assertTrue(state["verification"]["commands"])
        self.assertRegex(state["verification"]["record_sha256"], r"^[a-f0-9]{64}$")
        evidence = Path(state["verification"]["commands"][0]["evidence_path"])
        evidence.write_bytes(b"tampered\n")
        invalid = self.cli_raw("status", "--repo", str(self.repo), "--work-id", "work-verified")
        self.assertEqual(invalid.returncode, 2)
        self.assertIn("raw output", invalid.stderr)

    def test_multiple_work_packages_are_dispatched_in_dependency_order(self) -> None:
        self.cli("init", "--repo", str(self.repo), "--test-command", "python -c 'print(1)'")
        active = self.cli(
            "start", "--repo", str(self.repo), "--request", "修正 README 文字並拆成兩個工作包",
            "--work-id", "work-packages", "--task-class", "small", "--allowed-path", "README.md",
            "--work-package", "WP-001", "--work-package", "WP-002", "--approve",
        )
        worktree = Path(active["worktree"])
        (worktree / "README.md").write_text("one\n", encoding="utf-8")
        self.writer_complete("work-packages")
        next_run = self.review("work-packages", reviewer="reviewer-one")
        self.assertEqual(next_run["completed"], ["WP-001"])
        self.assertEqual(next_run["current"]["task_id"], "WP-002")
        self.assertEqual(next_run["tasks"][1]["depends_on"], ["WP-001"])

    def test_sequential_packages_keep_prior_changes_and_enforce_new_scope(self) -> None:
        self.cli("init", "--repo", str(self.repo), "--test-command", "python -c 'print(1)'")
        package_file = self.root / "distinct-dispatch.json"
        package_file.write_text(json.dumps({"work_packages": [
            {"id": "WP-001", "allowed_paths": ["README.md"]},
            {"id": "WP-002", "allowed_paths": ["product.txt"]},
        ]}, ensure_ascii=False), encoding="utf-8")
        active = self.cli(
            "start", "--repo", str(self.repo), "--request", "修正文件並拆成兩個工作包",
            "--work-id", "work-distinct-packages", "--task-class", "small",
            "--allowed-path", "README.md", "--allowed-path", "product.txt",
            "--work-package", "WP-001", "--work-package", "WP-002",
            "--work-package-file", str(package_file), "--approve",
        )
        worktree = Path(active["worktree"])
        (worktree / "README.md").write_text("first package\n", encoding="utf-8")
        self.writer_complete("work-distinct-packages")
        self.review("work-distinct-packages", reviewer="distinct-review-1")
        (worktree / "product.txt").write_text("second package\n", encoding="utf-8")
        second = self.writer_complete("work-distinct-packages")
        self.assertEqual(second["current"]["task_id"], "WP-002")
        reviewed = self.review("work-distinct-packages", reviewer="distinct-review-2")
        self.assertEqual(reviewed["completed"], ["WP-001", "WP-002"])

    def test_saved_commit_sha_drift_blocks_resume_even_when_content_is_unchanged(self) -> None:
        self.cli("init", "--repo", str(self.repo), "--test-command", "python -c 'print(1)'")
        active = self.cli(
            "start", "--repo", str(self.repo), "--request", "修正 README 文字",
            "--work-id", "work-commit-drift", "--task-class", "small", "--allowed-path", "README.md", "--approve",
        )
        worktree = Path(active["worktree"])
        (worktree / "README.md").write_text("commit\n", encoding="utf-8")
        self.writer_complete("work-commit-drift")
        self.review("work-commit-drift", reviewer="reviewer")
        finished = self.cli("finish", "--repo", str(self.repo), "--work-id", "work-commit-drift")
        original = finished["commit"]
        self.git("commit", "--amend", "-m", "amended without changing files", cwd=worktree)
        drifted = self.cli_raw("status", "--repo", str(self.repo), "--work-id", "work-commit-drift")
        self.assertEqual(drifted.returncode, 2)
        self.assertIn("commit SHA", drifted.stderr)
        self.assertNotEqual(self.git("rev-parse", "HEAD", cwd=worktree).strip(), original)

    def test_windows_style_test_command_is_accepted_without_losing_backslashes(self) -> None:
        self.cli("init", "--repo", str(self.repo), "--test-command", r"python .\tests\run.py")
        config = json.loads((self.repo / ".megin" / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(config["test_commands"], [r"python .\tests\run.py"])

    def test_read_only_request_cannot_be_forced_into_a_mutating_run(self) -> None:
        self.cli("init", "--repo", str(self.repo))
        result = self.cli_raw(
            "start", "--repo", str(self.repo), "--request", "請解釋目前架構並提供評估",
            "--task-class", "small", "--allowed-path", "README.md",
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("read-only", result.stderr)
        self.assertEqual(list((self.root / "state").rglob("*.json")), [])

    def test_classification_explores_repo_and_bug_cannot_be_downgraded(self) -> None:
        explored = self.cli("classify", "--repo", str(self.repo), "--request", "修正 README 文字")
        self.assertIn("exploration", explored)
        self.assertEqual(explored["exploration"]["repo_id"], ENGINE.repo_identity(self.repo))
        self.cli("init", "--repo", str(self.repo))
        result = self.cli_raw(
            "start", "--repo", str(self.repo), "--request", "修正 README 的 bug",
            "--task-class", "small", "--allowed-path", "README.md",
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("diagnosis", result.stderr)
        self.assertEqual(list((self.root / "state").rglob("*.json")), [])

    def test_review_cannot_accept_a_snapshot_changed_after_writer_completion(self) -> None:
        self.cli("init", "--repo", str(self.repo))
        active = self.cli(
            "start", "--repo", str(self.repo), "--request", "修正 README 文字",
            "--work-id", "work-review-boundary", "--task-class", "small", "--allowed-path", "README.md", "--approve",
        )
        worktree = Path(active["worktree"])
        worktree.joinpath("README.md").write_text("writer bytes\n", encoding="utf-8")
        self.writer_complete("work-review-boundary")
        worktree.joinpath("README.md").write_text("drifted bytes\n", encoding="utf-8")
        report = self.reviewer_report("work-review-boundary", reviewer="boundary-reviewer")
        result = self.cli_raw(
            "resume", "--repo", str(self.repo), "--work-id", "work-review-boundary",
            "--review-approved", "--reviewer-id", "boundary-reviewer", "--review-report", str(report),
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("writer completion", result.stderr)

    def test_approved_review_rejects_blocking_finding(self) -> None:
        self.cli("init", "--repo", str(self.repo))
        active = self.cli(
            "start", "--repo", str(self.repo), "--request", "修正 README 文字",
            "--work-id", "work-major-finding", "--task-class", "small", "--allowed-path", "README.md", "--approve",
        )
        worktree = Path(active["worktree"])
        worktree.joinpath("README.md").write_text("changed\n", encoding="utf-8")
        self.writer_complete("work-major-finding")
        report = self.reviewer_report(
            "work-major-finding", reviewer="finding-reviewer",
            findings=[{"key": "major", "text": "blocking requirement remains", "severity": "major"}],
        )
        result = self.cli_raw(
            "resume", "--repo", str(self.repo), "--work-id", "work-major-finding",
            "--review-approved", "--reviewer-id", "finding-reviewer", "--review-report", str(report),
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("blocking or major", result.stderr)

    def test_review_report_requires_content_bound_test_evidence(self) -> None:
        self.cli("init", "--repo", str(self.repo))
        active = self.cli(
            "start", "--repo", str(self.repo), "--request", "修正 README 文字",
            "--work-id", "work-review-evidence", "--task-class", "small",
            "--allowed-path", "README.md", "--approve",
        )
        Path(active["worktree"], "README.md").write_text("reviewed bytes\n", encoding="utf-8")
        self.writer_complete("work-review-evidence")
        report = self.reviewer_report("work-review-evidence", reviewer="evidence-reviewer")
        payload = json.loads(report.read_text(encoding="utf-8"))
        payload["test_evidence"][0].pop("output_sha256")
        report.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        result = self.cli_raw(
            "resume", "--repo", str(self.repo), "--work-id", "work-review-evidence",
            "--review-approved", "--reviewer-id", "evidence-reviewer", "--review-report", str(report),
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("schema validation", result.stderr)

    def test_redact_masks_prefixed_environment_secrets(self) -> None:
        redacted = ENGINE.redact("AWS_SECRET_ACCESS_KEY=secret MY_API_KEY='api value' PRIVATE_KEY=private")
        self.assertNotIn("secret", redacted)
        self.assertNotIn("api value", redacted)
        self.assertNotIn("private", redacted)
        self.assertIn("AWS_SECRET_ACCESS_KEY=<redacted>", redacted)

    def test_commit_recovery_refuses_a_dirty_worktree(self) -> None:
        self.cli("init", "--repo", str(self.repo))
        active = self.cli(
            "start", "--repo", str(self.repo), "--request", "修正 README 文字",
            "--work-id", "work-recovery-dirty", "--task-class", "small",
            "--allowed-path", "README.md", "--approve",
        )
        worktree = Path(active["worktree"])
        worktree.joinpath("README.md").write_text("committed bytes\n", encoding="utf-8")
        self.git("add", "README.md", cwd=worktree)
        self.git("commit", "-qm", "megin(work-recovery-dirty): committed bytes", cwd=worktree)
        worktree.joinpath("uncommitted.txt").write_text("ambiguous\n", encoding="utf-8")
        state, _ = ENGINE.load_state(self.repo, "work-recovery-dirty")
        self.assertFalse(ENGINE.recover_commit(state, worktree))
        self.assertIsNone(state["publication"].get("commit_sha"))

    def test_bug_repair_requires_a_read_only_diagnosis_assessment(self) -> None:
        self.cli("init", "--repo", str(self.repo))
        request = "修正 README 的 bug"
        missing = self.cli("start", "--repo", str(self.repo), "--request", request, "--task-class", "bug", "--repair-class", "small")
        self.assertFalse(missing["run_created"])
        diagnosis = self.cli(
            "diagnose", "--repo", str(self.repo), "--request", request,
            "--command", "python -c \"print(1)\"", "--disposition", "confirmed",
            "--hypothesis", "the parser accepts the malformed input and returns the wrong text",
        )
        active = self.cli(
            "start", "--repo", str(self.repo), "--request", request, "--work-id", "work-bug",
            "--task-class", "bug", "--repair-class", "small", "--diagnosis-file", diagnosis["assessment_path"],
            "--allowed-path", "README.md", "--approve",
        )
        state = json.loads(Path(active["state_path"]).read_text(encoding="utf-8"))
        self.assertEqual(state["task"]["diagnosis"], "confirmed")
        diagnosis_record = json.loads(Path(diagnosis["assessment_path"]).read_text(encoding="utf-8"))
        self.assertEqual(state["task"]["diagnosis_assessment"]["output_sha256"], diagnosis_record["output_sha256"])

    def test_task_specific_dispatch_packages_are_bound_to_approval(self) -> None:
        self.cli("init", "--repo", str(self.repo))
        package_file = self.root / "dispatch.json"
        package_file.write_text(json.dumps({"work_packages": [
            {"id": "WP-001", "acceptance": ["README has the requested wording"], "allowed_paths": ["README.md"], "forbidden_paths": ["secret.txt"], "interfaces": ["README contract"], "focused_commands": ["python -c 'print(1)'"], "related_commands": ["python -c 'print(1)'"], "full_commands": ["python -c 'print(1)'"]},
            {"id": "WP-002", "acceptance": ["second file is updated"], "allowed_paths": ["README.md"], "interfaces": ["follow-up contract"]},
        ]}, ensure_ascii=False), encoding="utf-8")
        active = self.cli(
            "start", "--repo", str(self.repo), "--request", "修正 README 文字並拆成兩個工作包",
            "--work-id", "work-dispatch", "--task-class", "small", "--work-package", "WP-001",
            "--work-package", "WP-002", "--work-package-file", str(package_file), "--allowed-path", "README.md", "--approve",
        )
        self.assertEqual(active["tasks"][0]["acceptance"], ["README has the requested wording"])
        self.assertEqual(active["current"]["focused_commands"], ["python -c 'print(1)'"])
        state_path = Path(active["state_path"])
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["tasks"][0]["allowed_paths"] = ["other.txt"]
        state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        invalid = self.cli_raw("status", "--repo", str(self.repo), "--work-id", "work-dispatch")
        self.assertEqual(invalid.returncode, 2)
        self.assertIn("digest", invalid.stderr)

    def test_configured_base_branch_is_used_for_new_worktree(self) -> None:
        self.git("branch", "release")
        self.cli("init", "--repo", str(self.repo), "--base-branch", "release")
        active = self.cli(
            "start", "--repo", str(self.repo), "--request", "修正 README 文字",
            "--work-id", "work-base", "--task-class", "small", "--allowed-path", "README.md", "--approve",
        )
        state = json.loads(Path(active["state_path"]).read_text(encoding="utf-8"))
        self.assertEqual(state["repo"]["base_branch"], "release")
        self.assertEqual(state["workspace"]["base_sha"], self.git("rev-parse", "release").strip())

    def test_writer_and_review_cannot_complete_without_external_reports(self) -> None:
        self.cli("init", "--repo", str(self.repo))
        active = self.cli(
            "start", "--repo", str(self.repo), "--request", "修正 README 文字",
            "--work-id", "work-reports", "--task-class", "small", "--allowed-path", "README.md", "--approve",
        )
        worktree = Path(active["worktree"])
        (worktree / "README.md").write_text("changed\n", encoding="utf-8")
        assignment = active["current"]
        missing_writer = self.cli_raw(
            "resume", "--repo", str(self.repo), "--work-id", "work-reports",
            "--writer-id", assignment["writer_id"], "--writer-ticket", assignment["ticket_sha256"], "--writer-complete",
        )
        self.assertEqual(missing_writer.returncode, 2)
        self.assertIn("external report", missing_writer.stderr)
        self.writer_complete("work-reports")
        missing_review = self.cli_raw(
            "resume", "--repo", str(self.repo), "--work-id", "work-reports",
            "--review-approved", "--reviewer-id", "reviewer",
        )
        self.assertEqual(missing_review.returncode, 2)
        self.assertIn("external report", missing_review.stderr)

    def test_writer_blocker_is_persisted_and_requires_a_new_ticket(self) -> None:
        self.cli("init", "--repo", str(self.repo))
        active = self.cli(
            "start", "--repo", str(self.repo), "--request", "修正 README 文字",
            "--work-id", "work-writer-blocked", "--task-class", "small",
            "--allowed-path", "README.md", "--approve",
        )
        assignment = active["current"]
        worktree = Path(active["worktree"])
        paths, snapshot = ENGINE.status_paths(worktree)
        report_path = self.root / "writer-blocked.json"
        report_path.write_text(json.dumps({
            "schema": "megin-writer-report/v1", "work_id": "work-writer-blocked",
            "assignment_id": assignment["assignment_id"], "assignment_sha256": assignment["assignment_sha256"],
            "writer_id": assignment["writer_id"], "session_id": assignment["session_id"],
            "ticket_sha256": assignment["ticket_sha256"], "status": "blocked",
            "changed_paths": paths, "snapshot": snapshot,
        }, ensure_ascii=False), encoding="utf-8")
        blocked = self.cli(
            "resume", "--repo", str(self.repo), "--work-id", "work-writer-blocked",
            "--writer-id", assignment["writer_id"], "--writer-ticket", assignment["ticket_sha256"],
            "--writer-report", str(report_path), "--writer-complete",
        )
        self.assertEqual(blocked["status"], "blocked")
        self.assertEqual(blocked["current"]["status"], "blocked")
        resumed = self.cli("status", "--repo", str(self.repo), "--work-id", "work-writer-blocked")
        self.assertEqual(resumed["status"], "blocked")
        self.assertEqual(resumed["current"]["status"], "blocked")

    def test_knowledge_conflict_can_leave_product_delivery_active(self) -> None:
        self.cli("init", "--repo", str(self.repo), "--test-command", "python -c 'print(1)'")
        active = self.cli(
            "start", "--repo", str(self.repo), "--request", "修正 README 並更新 product",
            "--work-id", "work-knowledge-conflict", "--task-class", "small", "--allowed-path", "README.md",
            "--allowed-path", "product.txt", "--knowledge-path", "README.md", "--approve",
        )
        worktree = Path(active["worktree"])
        (worktree / "README.md").write_text("reviewed knowledge\n", encoding="utf-8")
        (worktree / "product.txt").write_text("product change\n", encoding="utf-8")
        self.writer_complete("work-knowledge-conflict")
        self.review("work-knowledge-conflict", reviewer="code-reviewer")
        self.cli("resume", "--repo", str(self.repo), "--work-id", "work-knowledge-conflict", "--verified")
        knowledge_report = self.knowledge_report("work-knowledge-conflict")
        self.cli("resume", "--repo", str(self.repo), "--work-id", "work-knowledge-conflict", "--knowledge-reviewed", "--reviewer-id", "knowledge-reviewer", "--reviewer-session", "knowledge:1", "--knowledge-report", str(knowledge_report))
        (worktree / "README.md").write_text("concurrent canonical edit\n", encoding="utf-8")
        finished = self.cli("finish", "--repo", str(self.repo), "--work-id", "work-knowledge-conflict")
        self.assertEqual(finished["status"], "active")
        self.assertEqual(finished["knowledge"], "blocked")
        self.assertTrue(finished["commit"])
        self.assertIn("README.md", json.loads(Path(finished["state_path"]).read_text(encoding="utf-8"))["knowledge"]["conflicts"][0])
        resumed = self.cli("status", "--repo", str(self.repo), "--work-id", "work-knowledge-conflict")
        self.assertEqual(resumed["status"], "active")
        self.assertEqual(resumed["publication"], "publication_pending")

    def test_migrate_dry_run_is_non_mutating_and_reports_manifest(self) -> None:
        self.cli("init", "--repo", str(self.repo))
        self.legacyize_config()
        source_root = self.root / "legacy-state"
        target_root = self.root / "megin-state"
        result = self.cli(
            "migrate", "--repo", str(self.repo),
            "--from-state-root", str(source_root), "--to-state-root", str(target_root), "--dry-run",
        )
        self.assertEqual(result["schema"], "megin-migration/v1")
        self.assertEqual(result["status"], "dry_run")
        self.assertRegex(result["migration_id"], r"^[0-9a-f]{64}$")
        self.assertEqual(result["file_count"], 1)
        self.assertEqual(result["source"]["state_root"], str(source_root.resolve()))
        self.assertEqual(result["target"]["state_root"], str(target_root.resolve()))
        self.assertTrue((self.repo / MIGRATION_LEGACY_ALLOWLIST["config_dir"] / "config.json").exists())
        self.assertFalse((self.repo / ".megin").exists())
        self.assertFalse(target_root.exists())
        self.assertIsNone(result["backup"]["state"])

    def test_migrate_converts_state_paths_preserves_digests_and_is_idempotent(self) -> None:
        source_root, target_root, legacy_state_path = self.prepare_legacy_run()
        old_state = json.loads(legacy_state_path.read_text(encoding="utf-8"))
        old_candidate = Path(old_state["candidates"]["design"]["path"])
        old_candidate_bytes = old_candidate.read_bytes()
        result = self.cli(
            "migrate", "--repo", str(self.repo),
            "--from-state-root", str(source_root), "--to-state-root", str(target_root),
        )
        self.assertEqual(result["status"], "migrated")
        self.assertEqual(result["work_ids"], ["work-migrate"])
        self.assertGreaterEqual(result["file_count"], 3)
        self.assertTrue(Path(result["backup"]["config"]).is_dir())
        self.assertTrue(Path(result["backup"]["state"]).is_dir())
        self.assertFalse((self.repo / MIGRATION_LEGACY_ALLOWLIST["config_dir"]).exists())
        self.assertTrue((self.repo / ".megin" / "config.json").exists())
        self.assertFalse(legacy_state_path.exists())

        self.set_state_root(target_root)
        migrated = self.cli("status", "--repo", str(self.repo), "--work-id", "work-migrate")
        migrated_path = Path(migrated["state_path"])
        state = json.loads(migrated_path.read_text(encoding="utf-8"))
        self.assertEqual(state["plugin"], "megin")
        self.assertEqual(state["plugin_version"], "0.2.0")
        candidate = state["candidates"]["design"]
        candidate_path = Path(candidate["path"])
        self.assertTrue(str(candidate_path).startswith(str(target_root.resolve())))
        self.assertEqual(candidate_path.read_bytes(), old_candidate_bytes)
        self.assertEqual(candidate["sha256"], ENGINE.digest_bytes(old_candidate_bytes))
        self.assertEqual(state["task"]["request"], old_state["task"]["request"])
        self.assertEqual(ENGINE.load_state(self.repo, "work-migrate")[0]["plugin"], "megin")

        again = self.cli(
            "migrate", "--repo", str(self.repo),
            "--from-state-root", str(source_root), "--to-state-root", str(target_root),
        )
        self.assertEqual(again["status"], "already_migrated")
        self.assertEqual(again["work_ids"], ["work-migrate"])

    def test_migrate_converts_persisted_report_and_capability_schemas(self) -> None:
        source_root = self.root / "legacy-state"
        target_root = self.root / "megin-state"
        self.set_state_root(source_root)
        self.cli("init", "--repo", str(self.repo))
        active = self.cli(
            "start", "--repo", str(self.repo), "--request", "修正 README 文字",
            "--work-id", "work-migrate-reports", "--task-class", "small",
            "--allowed-path", "README.md", "--approve",
        )
        worktree = Path(active["worktree"])
        (worktree / "README.md").write_text("migrated reports\n", encoding="utf-8")
        self.writer_complete("work-migrate-reports")
        self.review("work-migrate-reports")
        state_path = Path(self.cli("status", "--repo", str(self.repo), "--work-id", "work-migrate-reports")["state_path"])
        state = json.loads(state_path.read_text(encoding="utf-8"))

        capability_paths: list[Path] = []
        for assignment in state["assignments"]:
            capability_paths.append(Path(assignment["capability_path"]))
        capability_paths.append(Path(state["review"]["reviewer_capability_path"]))
        for capability_path in capability_paths:
            payload = json.loads(capability_path.read_text(encoding="utf-8"))
            payload["schema"] = MIGRATION_LEGACY_ALLOWLIST["capability_schema"]
            payload.pop("capability_sha256", None)
            digest = ENGINE.digest_json(payload)
            payload["capability_sha256"] = digest
            capability_path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
            for assignment in state["assignments"]:
                if Path(assignment["capability_path"]).resolve() == capability_path.resolve():
                    assignment["capability_sha256"] = digest
            if Path(state["review"]["reviewer_capability_path"]).resolve() == capability_path.resolve():
                state["review"]["reviewer_capability_sha256"] = digest

        writer_result = state["assignments"][0]["writer_result"]
        writer_report_path = Path(writer_result["report_path"])
        writer_report = json.loads(writer_report_path.read_text(encoding="utf-8"))
        writer_report["schema"] = MIGRATION_LEGACY_ALLOWLIST["writer_report_schema"]
        writer_report_path.write_text(json.dumps(writer_report, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        review_report_path = Path(state["review"]["report_path"])
        review_report = json.loads(review_report_path.read_text(encoding="utf-8"))
        review_report["schema"] = MIGRATION_LEGACY_ALLOWLIST["review_report_schema"]
        review_report_path.write_text(json.dumps(review_report, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        state["plugin"] = MIGRATION_LEGACY_ALLOWLIST["plugin"]
        state["plugin_version"] = "0.1.0"
        state_path.write_text(json.dumps(state, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        self.legacyize_config()

        result = self.cli(
            "migrate", "--repo", str(self.repo),
            "--from-state-root", str(source_root), "--to-state-root", str(target_root),
        )
        self.assertEqual(result["status"], "migrated")
        self.set_state_root(target_root)
        migrated = ENGINE.load_state(self.repo, "work-migrate-reports")[0]
        for assignment in migrated["assignments"]:
            capability = json.loads(Path(assignment["capability_path"]).read_text(encoding="utf-8"))
            self.assertEqual(capability["schema"], "megin-capability/v1")
            ENGINE.validate_capability(
                assignment["capability_path"], assignment["capability_sha256"], migrated,
                kind="writer", assignment_id=assignment["assignment_id"],
                identity=assignment["writer_id"], session_id=assignment["session_id"],
            )
        ENGINE.validate_capability(
            migrated["review"]["reviewer_capability_path"], migrated["review"]["reviewer_capability_sha256"], migrated,
            kind="reviewer", assignment_id=migrated["review"]["assignment_id"],
            identity=migrated["review"]["reviewer_id"], session_id=migrated["review"]["reviewer_session"],
        )
        self.assertEqual(json.loads(Path(migrated["assignments"][0]["writer_result"]["report_path"]).read_text(encoding="utf-8"))["schema"], "megin-writer-report/v1")
        self.assertEqual(json.loads(Path(migrated["review"]["report_path"]).read_text(encoding="utf-8"))["schema"], "megin-review-report/v1")

    def test_normal_commands_reject_legacy_config_with_migration_hint(self) -> None:
        self.cli("init", "--repo", str(self.repo))
        self.legacyize_config()
        result = self.cli_raw("status", "--repo", str(self.repo))
        self.assertEqual(result.returncode, 2)
        self.assertIn("megin migrate --repo", result.stderr)
        self.assertNotIn('"runs"', result.stdout)

    def test_migrate_fails_closed_on_destination_conflict(self) -> None:
        source_root, target_root, _ = self.prepare_legacy_run()
        target_state = target_root / ENGINE.repo_identity(self.repo)
        target_state.mkdir(parents=True)
        marker = target_state / "keep.txt"
        marker.write_text("destination belongs to another run\n", encoding="utf-8")
        result = self.cli_raw(
            "migrate", "--repo", str(self.repo),
            "--from-state-root", str(source_root), "--to-state-root", str(target_root),
        )
        self.assertEqual(result.returncode, 3)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["schema"], "megin-migration/v1")
        self.assertEqual(payload["status"], "blocked")
        self.assertTrue(payload["conflicts"])
        self.assertTrue((self.repo / MIGRATION_LEGACY_ALLOWLIST["config_dir"] / "config.json").exists())
        self.assertFalse((self.repo / ".megin").exists())
        self.assertEqual(marker.read_text(encoding="utf-8"), "destination belongs to another run\n")

    def test_migrate_fails_closed_on_lock_and_malformed_state(self) -> None:
        source_root, target_root, state_path = self.prepare_legacy_run()
        lock = state_path.parent / "work-migrate.json.lock"
        lock.write_text("active\n", encoding="utf-8")
        locked = self.cli_raw(
            "migrate", "--repo", str(self.repo),
            "--from-state-root", str(source_root), "--to-state-root", str(target_root),
        )
        self.assertEqual(locked.returncode, 3)
        self.assertIn("lock", json.loads(locked.stdout)["conflicts"][0])
        self.assertTrue((self.repo / MIGRATION_LEGACY_ALLOWLIST["config_dir"]).exists())
        self.assertFalse((self.repo / ".megin").exists())
        lock.unlink()

        state_path.write_text("{ malformed", encoding="utf-8")
        malformed = self.cli_raw(
            "migrate", "--repo", str(self.repo),
            "--from-state-root", str(source_root), "--to-state-root", str(target_root),
        )
        self.assertEqual(malformed.returncode, 3)
        self.assertIn("malformed", json.loads(malformed.stdout)["conflicts"][0])
        self.assertTrue((self.repo / MIGRATION_LEGACY_ALLOWLIST["config_dir"]).exists())
        self.assertFalse((self.repo / ".megin").exists())

    def test_migrate_rejects_redirected_state_inputs(self) -> None:
        source_root, target_root, state_path = self.prepare_legacy_run()
        redirected = state_path.parent / "redirected.json"
        outside = self.root / "outside.json"
        outside.write_text("{}\n", encoding="utf-8")
        try:
            redirected.symlink_to(outside)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"symlinks are unavailable in this Windows test environment: {exc}")
        result = self.cli_raw(
            "migrate", "--repo", str(self.repo),
            "--from-state-root", str(source_root), "--to-state-root", str(target_root),
        )
        self.assertEqual(result.returncode, 3)
        self.assertIn("symlink", json.loads(result.stdout)["conflicts"][0])
        self.assertTrue((self.repo / MIGRATION_LEGACY_ALLOWLIST["config_dir"]).exists())
        self.assertFalse((self.repo / ".megin").exists())

    def test_migrate_rechecks_source_before_publish(self) -> None:
        source_root, target_root, state_path = self.prepare_legacy_run()
        original_transform = ENGINE._migration_transform_tree
        changed = False

        def mutate_source_before_transform(root: Path, source: Path, target: Path) -> list[str]:
            nonlocal changed
            if not changed and source == source_root:
                changed = True
                state_path.write_text(state_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            return original_transform(root, source, target)

        args = argparse.Namespace(
            from_state_root=str(source_root), to_state_root=str(target_root), dry_run=False,
        )
        with mock.patch.object(ENGINE, "_migration_transform_tree", side_effect=mutate_source_before_transform):
            with self.assertRaises(ENGINE.MeginError) as context:
                ENGINE._run_migration(args, self.repo)
        self.assertIn("changed during migration", str(context.exception))
        self.assertTrue((self.repo / MIGRATION_LEGACY_ALLOWLIST["config_dir"] / "config.json").exists())
        self.assertFalse((self.repo / ".megin").exists())
        self.assertTrue(state_path.exists())

    def test_migrate_recovers_after_publish_validation_failure(self) -> None:
        source_root, target_root, _ = self.prepare_legacy_run()
        args = argparse.Namespace(
            from_state_root=str(source_root), to_state_root=str(target_root), dry_run=False,
        )
        with mock.patch.object(ENGINE, "load_config", side_effect=ENGINE.MeginError("injected target validation failure")):
            with self.assertRaises(ENGINE.MeginError) as context:
                ENGINE._run_migration(args, self.repo)
        self.assertIn("injected target validation failure", str(context.exception))
        self.assertTrue((self.repo / MIGRATION_LEGACY_ALLOWLIST["config_dir"] / "config.json").exists())
        self.assertFalse((self.repo / ".megin").exists())
        self.assertTrue((source_root / ENGINE.repo_identity(self.repo) / "work-migrate.json").exists())
        self.assertTrue(list(target_root.glob("*.megin-failed-*")))
        self.assertTrue(list(self.repo.glob(".megin.failed-*")))


if __name__ == "__main__":
    unittest.main()
