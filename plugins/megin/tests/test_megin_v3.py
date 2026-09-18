from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
ENGINE = ROOT / "scripts" / "megin_v3.py"
GHERKIN = ROOT / "scripts" / "gherkin.py"
SESSION_HOOK = ROOT / "hooks" / "session_start.py"


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
        # The test area is ignored and may be cleaned by the repository's test harness.
        pass

    def git(self, *args: str) -> str:
        result = subprocess.run(["git", *args], cwd=self.repo, env=self.env, text=True, encoding="utf-8", capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def cli(self, *args: str, expect: int = 0) -> dict:
        result = subprocess.run([sys.executable, str(ENGINE), *args], cwd=ROOT, env=self.env, text=True, encoding="utf-8", capture_output=True)
        self.assertEqual(result.returncode, expect, result.stderr)
        return json.loads(result.stdout)

    def start(self, work_id: str = "v3-readme") -> dict:
        return self.cli(
            "start", "--repo", str(self.repo), "--work-id", work_id, "--task-class", "small",
            "--request", "update README behavior", "--allowed-path", "README.md",
            "--test-command", "python -c \"print(1)\"",
        )

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

    def test_session_hook_only_returns_routing_context(self) -> None:
        result = subprocess.run([sys.executable, str(SESSION_HOOK)], cwd=ROOT, input=json.dumps({"cwd": str(self.repo)}), env=self.env, text=True, encoding="utf-8", capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertIn("read-only", payload["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(self.git("status", "--porcelain"), "")


if __name__ == "__main__":
    unittest.main()
