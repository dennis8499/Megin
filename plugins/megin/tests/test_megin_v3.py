from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import uuid
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
ENGINE = ROOT / "scripts" / "megin_v3.py"
GHERKIN = ROOT / "scripts" / "gherkin.py"
SESSION_HOOK = ROOT / "hooks" / "session_start.py"


def remove_fixture(path: Path) -> None:
    def remove_readonly(function, target, _exc_info) -> None:
        os.chmod(target, stat.S_IREAD | stat.S_IWRITE)
        function(target)

    if path.exists():
        shutil.rmtree(path, onerror=remove_readonly)


class MeginV3CliTests(unittest.TestCase):
    def setUp(self) -> None:
        # The managed Windows runner can deny temporary-directory ACL changes.
        # Keep disposable fixtures in the repository's writable, ignored test area.
        fixture_root = ROOT.parent.parent / ".test-run-tmp"
        fixture_root.mkdir(parents=True, exist_ok=True)
        self.root = fixture_root / f"v3-test-{os.getpid()}-{uuid.uuid4().hex}"
        self.root.mkdir(parents=True, exist_ok=True)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.state = self.root / "state"
        self.env = os.environ.copy()
        self.env["MEGIN_STATE_ROOT"] = str(self.state)
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "megin@example.invalid")
        self.git("config", "user.name", "Megin v3 test")
        (self.repo / "README.md").write_text("seed\n", encoding="utf-8")
        self.git("add", "README.md")
        self.git("commit", "-qm", "seed")

    def tearDown(self) -> None:
        try:
            remove_fixture(self.root)
        except OSError:
            pass

    def git(self, *args: str) -> str:
        result = subprocess.run(["git", *args], cwd=self.repo, env=self.env, text=True, encoding="utf-8", capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def cli(self, *args: str, expect: int = 0) -> dict:
        result = subprocess.run([sys.executable, str(ENGINE), *args], cwd=ROOT, env=self.env, text=True, encoding="utf-8", capture_output=True)
        self.assertEqual(result.returncode, expect, result.stderr)
        return json.loads(result.stdout)

    def start(
        self,
        work_id: str = "v3-readme",
        task_titles: tuple[str, ...] = (),
        scenario_command: str | None = None,
    ) -> dict:
        scenario_id = f"BDD-{work_id.upper()}-001"
        command = [
            "start", "--repo", str(self.repo), "--work-id", work_id, "--task-class", "small",
            "--request", "update README behavior", "--allowed-path", "README.md",
            "--test-command", "python -c \"print(1)\"",
            "--scenario-command", scenario_command or f"python -c \"import json; print(json.dumps({{'scenarios': [{{'id': '{scenario_id}', 'status': 'passed'}}]}}))\"",
        ]
        for title in task_titles:
            command.extend(["--task", title])
        return self.cli(*command)

    def test_plan_gate_acceptance_and_commit_order(self) -> None:
        candidate = self.start()
        self.assertEqual(candidate["schema"], "delivery-run/v3")
        self.assertEqual(candidate["status"], "awaiting_approval")
        base = self.git("rev-parse", "HEAD").strip()
        rejected = subprocess.run(
            [sys.executable, str(ENGINE), "approve", "--repo", str(self.repo), "--work-id", "v3-readme"],
            cwd=ROOT, env=self.env, text=True, encoding="utf-8", capture_output=True,
        )
        self.assertEqual(rejected.returncode, 2)
        self.assertIn("explicit response", rejected.stderr)
        approved = self.cli("approve", "--repo", str(self.repo), "--work-id", "v3-readme", "--confirm")
        assignment = approved["assignment"]
        self.assertEqual(approved["approval"], "approved")
        self.assertEqual(approved["workspace"]["branch"], "feat/v3-readme")
        (self.repo / "README.md").write_text("implemented\n", encoding="utf-8")
        self.cli(
            "resume", "--repo", str(self.repo), "--work-id", "v3-readme", "--writer-complete",
            "--writer-id", assignment["identity"], "--writer-ticket", assignment["ticket"],
        )
        self.cli("resume", "--repo", str(self.repo), "--work-id", "v3-readme", "--review-verdict", "APPROVED", "--reviewer-id", "fresh", "--reviewer-session", "fresh:1")
        verified = self.cli("verify", "--repo", str(self.repo), "--work-id", "v3-readme")
        self.assertEqual(verified["status"], "awaiting_user_acceptance")
        self.assertIsNone(verified["publication"]["commit_sha"])
        self.assertEqual(self.git("rev-parse", "HEAD").strip(), base)
        accepted = self.cli("accept", "--repo", str(self.repo), "--work-id", "v3-readme", "--confirm")
        self.assertEqual(accepted["human_acceptance"]["status"], "passed")
        finished = self.cli("finish", "--repo", str(self.repo), "--work-id", "v3-readme")
        self.assertEqual(finished["status"], "complete")
        self.assertTrue(finished["commit"])
        self.assertNotEqual(self.git("rev-parse", "HEAD").strip(), base)

    def test_read_only_route_does_not_create_state(self) -> None:
        result = self.cli("classify", "--request", "請檢視目前流程並提供評估")
        self.assertTrue(result["read_only"])
        status = self.cli("status", "--repo", str(self.repo))
        self.assertEqual(status["runs"], [])

    def test_explicit_mutating_class_cannot_override_read_only_intent(self) -> None:
        result = self.cli(
            "classify", "--request", "review this workflow without changing anything",
            "--task-class", "small",
        )
        self.assertTrue(result["read_only"])
        self.assertEqual(result["task_class"], "read_only")

    def test_default_base_does_not_follow_current_feature_branch(self) -> None:
        self.git("switch", "-c", "feature/current")
        result = self.cli("init", "--repo", str(self.repo), "--force")
        self.assertEqual(result["config"]["base_branch"], "main")

    def test_missing_base_fails_closed(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ENGINE), "start", "--repo", str(self.repo), "--work-id", "v3-missing-base",
             "--request", "update README behavior", "--task-class", "small", "--base-branch", "missing"],
            cwd=ROOT, env=self.env, text=True, encoding="utf-8", capture_output=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("base branch does not resolve", result.stderr)

    def test_current_workspace_lock_blocks_another_approval(self) -> None:
        candidate = self.start("v3-lock")
        lock = Path(candidate["state_path"]).parent / "current-workspace.lock"
        lock.write_text(json.dumps({"work_id": "other-work"}), encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(ENGINE), "approve", "--repo", str(self.repo), "--work-id", "v3-lock", "--confirm"],
            cwd=ROOT, env=self.env, text=True, encoding="utf-8", capture_output=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("already owned by Work ID other-work", result.stderr)

    def test_bug_route_requires_read_only_diagnosis(self) -> None:
        diagnosis = self.cli(
            "diagnose", "--repo", str(self.repo), "--request", "bug: README regression",
            "--command", "python -c \"print(1)\"", "--disposition", "confirmed",
            "--hypothesis", "the regression is in the README rendering path",
        )
        candidate = self.cli(
            "start", "--repo", str(self.repo), "--work-id", "v3-bug", "--request", "bug: README regression",
            "--task-class", "bug", "--diagnosis", "confirmed", "--diagnosis-file", diagnosis["assessment_path"],
            "--allowed-path", "README.md",
        )
        self.assertEqual(candidate["task_class"], "bug")
        self.assertEqual(candidate["status"], "awaiting_approval")

    def test_gherkin_contract_requires_steps_and_stable_id(self) -> None:
        feature = self.root / "login.feature"
        feature.write_text(
            "@BDD-LOGIN-001\nFeature: Login\n\nScenario: sign in\n  Given a registered user\n  When the user signs in\n  Then the dashboard is shown\n",
            encoding="utf-8",
        )
        result = self.cli(
            "start", "--repo", str(self.repo), "--work-id", "v3-gherkin", "--request", "add login",
            "--task-class", "small", "--feature-file", str(feature), "--allowed-path", "README.md",
        )
        self.assertEqual(result["behavior_contract"]["scenarios"][0]["id"], "BDD-LOGIN-001")
        bad = self.root / "bad.feature"
        bad.write_text("Feature: Broken\nScenario: empty\n", encoding="utf-8")
        failed = subprocess.run(
            [sys.executable, str(ENGINE), "start", "--repo", str(self.repo), "--work-id", "v3-bad", "--request", "bad feature request", "--task-class", "small", "--feature-file", str(bad)],
            cwd=ROOT, env=self.env, text=True, encoding="utf-8", capture_output=True,
        )
        self.assertEqual(failed.returncode, 2)
        self.assertIn("no Given/When/Then", failed.stderr)

    def test_snapshot_drift_after_review_blocks_verification(self) -> None:
        candidate = self.start("v3-drift")
        base = self.git("rev-parse", "HEAD").strip()
        approved = self.cli("approve", "--repo", str(self.repo), "--work-id", "v3-drift", "--confirm")
        assignment = approved["assignment"]
        (self.repo / "README.md").write_text("reviewed\n", encoding="utf-8")
        self.cli(
            "resume", "--repo", str(self.repo), "--work-id", "v3-drift", "--writer-complete",
            "--writer-id", assignment["identity"], "--writer-ticket", assignment["ticket"],
        )
        self.cli("resume", "--repo", str(self.repo), "--work-id", "v3-drift", "--review-verdict", "APPROVED", "--reviewer-id", "fresh", "--reviewer-session", "fresh:1")
        (self.repo / "README.md").write_text("unreviewed\n", encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(ENGINE), "verify", "--repo", str(self.repo), "--work-id", "v3-drift"],
            cwd=ROOT, env=self.env, text=True, encoding="utf-8", capture_output=True,
        )
        self.assertEqual(result.returncode, 2)
        status = self.cli("status", "--repo", str(self.repo), "--work-id", "v3-drift")
        self.assertEqual(status["status"], "awaiting_review")
        self.assertEqual(status["tasks"][0]["status"], "awaiting_review")
        self.cli("resume", "--repo", str(self.repo), "--work-id", "v3-drift", "--review-verdict", "APPROVED", "--reviewer-id", "fresh-2", "--reviewer-session", "fresh-2:1")
        verified = self.cli("verify", "--repo", str(self.repo), "--work-id", "v3-drift")
        self.assertEqual(verified["status"], "awaiting_user_acceptance")
        self.assertEqual(self.git("rev-parse", "HEAD").strip(), base)

    def test_multi_task_snapshot_drift_requires_each_task_fresh_review(self) -> None:
        self.start("v3-multi-drift", ("first task", "second task"))
        approved = self.cli("approve", "--repo", str(self.repo), "--work-id", "v3-multi-drift", "--confirm")
        assignment = approved["assignment"]
        (self.repo / "README.md").write_text("first task\n", encoding="utf-8")
        self.cli(
            "resume", "--repo", str(self.repo), "--work-id", "v3-multi-drift", "--task-id", "task-01", "--writer-complete",
            "--writer-id", assignment["identity"], "--writer-ticket", assignment["ticket"],
        )
        self.cli(
            "resume", "--repo", str(self.repo), "--work-id", "v3-multi-drift", "--task-id", "task-01",
            "--review-verdict", "APPROVED", "--reviewer-id", "fresh-1", "--reviewer-session", "fresh-1:1",
        )
        active = self.cli("status", "--repo", str(self.repo), "--work-id", "v3-multi-drift")
        self.assertEqual(active["tasks"][1]["status"], "active")
        (self.repo / "README.md").write_text("second task\n", encoding="utf-8")
        self.cli("resume", "--repo", str(self.repo), "--work-id", "v3-multi-drift", "--task-id", "task-02", "--writer-complete")
        self.cli(
            "resume", "--repo", str(self.repo), "--work-id", "v3-multi-drift", "--task-id", "task-02",
            "--review-verdict", "APPROVED", "--reviewer-id", "fresh-2", "--reviewer-session", "fresh-2:1",
        )

        (self.repo / "README.md").write_text("drifted after review\n", encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(ENGINE), "verify", "--repo", str(self.repo), "--work-id", "v3-multi-drift"],
            cwd=ROOT, env=self.env, text=True, encoding="utf-8", capture_output=True,
        )
        self.assertEqual(result.returncode, 2)
        status = self.cli("status", "--repo", str(self.repo), "--work-id", "v3-multi-drift")
        self.assertEqual([task["status"] for task in status["tasks"]], ["awaiting_review", "awaiting_review"])
        self.assertEqual(status["review"]["findings"], [])
        self.assertEqual(status["review"]["no_progress_count"], 0)

        self.cli(
            "resume", "--repo", str(self.repo), "--work-id", "v3-multi-drift", "--task-id", "task-01",
            "--review-verdict", "APPROVED", "--reviewer-id", "fresh-3", "--reviewer-session", "fresh-3:1",
        )
        status = self.cli("status", "--repo", str(self.repo), "--work-id", "v3-multi-drift")
        self.assertEqual([task["status"] for task in status["tasks"]], ["reviewed", "awaiting_review"])
        self.cli(
            "resume", "--repo", str(self.repo), "--work-id", "v3-multi-drift", "--task-id", "task-02",
            "--review-verdict", "APPROVED", "--reviewer-id", "fresh-4", "--reviewer-session", "fresh-4:1",
        )
        verified = self.cli("verify", "--repo", str(self.repo), "--work-id", "v3-multi-drift")
        self.assertEqual(verified["status"], "awaiting_user_acceptance")

    def test_scenario_runner_workspace_mutation_is_recorded_as_failed(self) -> None:
        scenario_command = (
            "python -c \"from pathlib import Path; Path('README.md').write_text('runner mutation\\n', encoding='utf-8'); "
            "import json; print(json.dumps({'scenarios': [{'id': 'BDD-V3-SCENARIO-MUTATION-001', 'status': 'passed'}]}))\""
        )
        self.start("v3-scenario-mutation", scenario_command=scenario_command)
        approved = self.cli("approve", "--repo", str(self.repo), "--work-id", "v3-scenario-mutation", "--confirm")
        assignment = approved["assignment"]
        (self.repo / "README.md").write_text("implemented\n", encoding="utf-8")
        self.cli(
            "resume", "--repo", str(self.repo), "--work-id", "v3-scenario-mutation", "--writer-complete",
            "--writer-id", assignment["identity"], "--writer-ticket", assignment["ticket"],
        )
        self.cli(
            "resume", "--repo", str(self.repo), "--work-id", "v3-scenario-mutation", "--review-verdict", "APPROVED",
            "--reviewer-id", "fresh", "--reviewer-session", "fresh:1",
        )
        result = self.cli("verify", "--repo", str(self.repo), "--work-id", "v3-scenario-mutation", expect=2)
        record = result["verification"]["commands"][-1]
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(record["status"], "failed")
        self.assertIn("changed the approved workspace", record["reason"])

    def test_missing_scenario_evidence_blocks_verification(self) -> None:
        candidate = self.cli(
            "start", "--repo", str(self.repo), "--work-id", "v3-no-scenario", "--task-class", "small",
            "--request", "update README behavior", "--allowed-path", "README.md", "--test-command", "python -c \"print(1)\"",
        )
        approved = self.cli("approve", "--repo", str(self.repo), "--work-id", "v3-no-scenario", "--confirm")
        assignment = approved["assignment"]
        (self.repo / "README.md").write_text("implemented\n", encoding="utf-8")
        self.cli(
            "resume", "--repo", str(self.repo), "--work-id", "v3-no-scenario", "--writer-complete",
            "--writer-id", assignment["identity"], "--writer-ticket", assignment["ticket"],
        )
        self.cli("resume", "--repo", str(self.repo), "--work-id", "v3-no-scenario", "--review-verdict", "APPROVED", "--reviewer-id", "fresh", "--reviewer-session", "fresh:1")
        result = subprocess.run(
            [sys.executable, str(ENGINE), "verify", "--repo", str(self.repo), "--work-id", "v3-no-scenario"],
            cwd=ROOT, env=self.env, text=True, encoding="utf-8", capture_output=True,
        )
        self.assertEqual(result.returncode, 2)
        status = self.cli("status", "--repo", str(self.repo), "--work-id", "v3-no-scenario")
        self.assertEqual(status["verification"]["scenario_results"][0]["status"], "not_run")

    def test_knowledge_candidate_is_promoted_only_after_commit(self) -> None:
        result = self.cli(
            "start", "--repo", str(self.repo), "--work-id", "v3-knowledge", "--task-class", "small",
            "--request", "update knowledge", "--allowed-path", "knowledge.json", "--knowledge-path", "knowledge.json",
            "--test-command", "python -c \"print(1)\"",
            "--scenario-command", "python -c \"import json; print(json.dumps({'scenarios': [{'id': 'BDD-V3-KNOWLEDGE-001', 'status': 'passed'}]}))\"",
        )
        approved = self.cli("approve", "--repo", str(self.repo), "--work-id", "v3-knowledge", "--confirm")
        assignment = approved["assignment"]
        (self.repo / "knowledge.json").write_text('{"claim": "verified"}\n', encoding="utf-8")
        self.cli(
            "resume", "--repo", str(self.repo), "--work-id", "v3-knowledge", "--writer-complete",
            "--writer-id", assignment["identity"], "--writer-ticket", assignment["ticket"],
        )
        self.cli("resume", "--repo", str(self.repo), "--work-id", "v3-knowledge", "--review-verdict", "APPROVED", "--reviewer-id", "fresh", "--reviewer-session", "fresh:1")
        self.cli("verify", "--repo", str(self.repo), "--work-id", "v3-knowledge")
        self.cli("accept", "--repo", str(self.repo), "--work-id", "v3-knowledge", "--confirm")
        finished = self.cli("finish", "--repo", str(self.repo), "--work-id", "v3-knowledge")
        self.assertEqual(finished["knowledge"]["status"], "promoted")
        candidate_path = Path(finished["knowledge"]["candidate_path"])
        candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
        self.assertIn("pre_sha256", candidate["sources"][0])
        self.assertIn("post_sha256", candidate["sources"][0])
        self.assertEqual(candidate["post_snapshot"], finished["knowledge"]["post_snapshot"])

    def test_invalid_knowledge_can_recover_on_same_work_id(self) -> None:
        self.cli(
            "start", "--repo", str(self.repo), "--work-id", "v3-bad-knowledge", "--task-class", "small",
            "--request", "update knowledge", "--allowed-path", "knowledge.json", "--knowledge-path", "knowledge.json",
            "--test-command", "python -c \"print(1)\"",
            "--scenario-command", "python -c \"import json; print(json.dumps({'scenarios': [{'id': 'BDD-V3-BAD-KNOWLEDGE-001', 'status': 'passed'}]}))\"",
        )
        approved = self.cli("approve", "--repo", str(self.repo), "--work-id", "v3-bad-knowledge", "--confirm")
        assignment = approved["assignment"]
        (self.repo / "knowledge.json").write_text('{invalid\n', encoding="utf-8")
        self.cli(
            "resume", "--repo", str(self.repo), "--work-id", "v3-bad-knowledge", "--writer-complete",
            "--writer-id", assignment["identity"], "--writer-ticket", assignment["ticket"],
        )
        self.cli("resume", "--repo", str(self.repo), "--work-id", "v3-bad-knowledge", "--review-verdict", "APPROVED", "--reviewer-id", "fresh", "--reviewer-session", "fresh:1")
        self.cli("verify", "--repo", str(self.repo), "--work-id", "v3-bad-knowledge")
        self.cli("accept", "--repo", str(self.repo), "--work-id", "v3-bad-knowledge", "--confirm")
        result = subprocess.run(
            [sys.executable, str(ENGINE), "finish", "--repo", str(self.repo), "--work-id", "v3-bad-knowledge"],
            cwd=ROOT, env=self.env, text=True, encoding="utf-8", capture_output=True,
        )
        self.assertEqual(result.returncode, 2)
        status = self.cli("status", "--repo", str(self.repo), "--work-id", "v3-bad-knowledge")
        self.assertEqual(status["status"], "blocked")
        self.assertEqual(status["knowledge"]["status"], "blocked")
        self.assertIsNone(status["publication"]["commit_sha"])
        state_record = json.loads(Path(status["state_path"]).read_text(encoding="utf-8"))
        self.assertTrue(any(item["kind"] == "knowledge_promotion_blocked" for item in state_record["events"]))

        (self.repo / "knowledge.json").write_text('{"claim": "repaired"}\n', encoding="utf-8")
        drift = subprocess.run(
            [sys.executable, str(ENGINE), "verify", "--repo", str(self.repo), "--work-id", "v3-bad-knowledge"],
            cwd=ROOT, env=self.env, text=True, encoding="utf-8", capture_output=True,
        )
        self.assertEqual(drift.returncode, 2)
        self.cli(
            "resume", "--repo", str(self.repo), "--work-id", "v3-bad-knowledge", "--review-verdict", "APPROVED",
            "--reviewer-id", "fresh-2", "--reviewer-session", "fresh-2:1",
        )
        self.cli("verify", "--repo", str(self.repo), "--work-id", "v3-bad-knowledge")
        self.cli("accept", "--repo", str(self.repo), "--work-id", "v3-bad-knowledge", "--confirm")
        recovered = self.cli("finish", "--repo", str(self.repo), "--work-id", "v3-bad-knowledge")
        self.assertEqual(recovered["status"], "complete")
        self.assertEqual(recovered["knowledge"]["status"], "promoted")
        self.assertEqual(recovered["knowledge"]["conflicts"], [])
        self.assertIsNotNone(recovered["publication"]["commit_sha"])

    def test_session_hook_only_returns_routing_context(self) -> None:
        result = subprocess.run([sys.executable, str(SESSION_HOOK)], cwd=ROOT, input=json.dumps({"cwd": str(self.repo)}), env=self.env, text=True, encoding="utf-8", capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertIn("read-only", payload["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(self.git("status", "--porcelain"), "")


if __name__ == "__main__":
    unittest.main()
