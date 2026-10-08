"""Exercise the public single-Repo workflow through local delivery and remote drift."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SKILL_ROOT = ROOT / ".agents" / "skills"
SCRIPTS = SKILL_ROOT / "megin" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import repo_workspace  # noqa: E402

QUALITY_GATE = SCRIPTS / "quality_gate.py"
REPO_WORK_ID = "work-20261006-standalone-delivery"


class RepoWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.temp = Path(self.temporary.name)
        self.repo = self.temp / "repo"
        self.repo.mkdir()
        shutil.copytree(SKILL_ROOT, self.repo / ".agents" / "skills",
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Repo Workflow Test")
        self.git("config", "user.email", "repo-workflow@example.invalid")
        (self.repo / "README.md").write_text("base\n", encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-m", "base")
        self.base = self.git("rev-parse", "HEAD").stdout.strip()
        self.remote: Path | None = None

    def git(self, *arguments: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            ["git", "-C", str(cwd or self.repo), *arguments], text=True,
            encoding="utf-8", errors="replace", capture_output=True, check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        return result

    def run_gate(self, action: str, gate: str | None = None) -> subprocess.CompletedProcess[str]:
        arguments = [sys.executable, "-X", "utf8", "-B", str(QUALITY_GATE), action,
                     "--repo", str(self.repo), "--work-id", REPO_WORK_ID]
        if gate:
            arguments.extend(["--gate", gate])
        return subprocess.run(arguments, text=True, encoding="utf-8", errors="replace",
                              capture_output=True, check=False)

    def prepare_work(self, with_remote: bool = False) -> None:
        if with_remote:
            self.remote = self.temp / "origin.git"
            result = subprocess.run(
                ["git", "-C", str(self.temp), "init", "--bare", "-b", "main", str(self.remote)],
                text=True, encoding="utf-8", errors="replace", capture_output=True, check=False,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            self.git("remote", "add", "origin", str(self.remote))
            self.git("push", "-u", "origin", "main")
        feature = f"feature/{REPO_WORK_ID}"
        self.git("switch", "-c", feature)
        (self.repo / "app.py").write_text('value = "accepted"\n', encoding="utf-8")
        work = self.repo / "docs" / "work" / REPO_WORK_ID
        (work / "plan-1").mkdir(parents=True)
        evidence = work / "evidence"
        evidence.mkdir()
        process_records = [
            f"docs/work/{REPO_WORK_ID}/evidence/quality.json",
            f"docs/work/{REPO_WORK_ID}/evidence/writer.md",
            f"docs/work/{REPO_WORK_ID}/evidence/check.log",
            f"docs/work/{REPO_WORK_ID}/evidence/review.md",
            f"docs/work/{REPO_WORK_ID}/evidence/acceptance.md",
            f"docs/work/{REPO_WORK_ID}/evidence/delivery.json",
        ]
        skills_sha = repo_workspace.fingerprint(self.repo)["sha256"]
        contract = {
            "schema": "megin-repo-quality-contract/v1",
            "work_id": REPO_WORK_ID,
            "plan_version": "plan-1",
            "base_branch": "main",
            "base_commit": self.base,
            "feature_branch": feature,
            "remote_name": "origin" if with_remote else None,
            "remote_url": str(self.remote) if with_remote else None,
            "allowed_paths": ["app.py", f"docs/work/{REPO_WORK_ID}/"],
            "checks": [{"id": "unit", "kind": "test", "command": "python -m unittest", "cwd": "."}],
            "process_records": process_records,
            "quality_ref": process_records[0],
            "delivery_ref": process_records[-1],
            "skills_sha256": skills_sha,
        }
        (work / "plan-1" / "quality-contract.json").write_text(
            json.dumps(contract, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8",
        )
        (work / "plan-1" / "plan.md").write_text("approved single-Repo plan\n", encoding="utf-8")
        (work / "requirements.md").write_text("approved behavior\n", encoding="utf-8")
        (work / "workflow.md").write_text(
            f"# Workflow\n\n- schema: megin-repo-workflow/v1\n- work_id: {REPO_WORK_ID}\n"
            f"- repository: .\n- base_branch: main\n- base_commit: {self.base}\n"
            f"- feature_branch: {feature}\n- remote_name: {'origin' if with_remote else 'none'}\n"
            f"- remote_url: {str(self.remote) if with_remote else 'none'}\n"
            "- phase: implementation\n- status: active\n- plan_version: plan-1\n"
            f"- quality_ref: {process_records[0]}\n- delivery_ref: {process_records[-1]}\n",
            encoding="utf-8",
        )
        (evidence / "delivery.json").write_text("{}\n", encoding="utf-8")
        claim = repo_workspace.claim(self.repo, REPO_WORK_ID, "writer-1")
        self.assertEqual(REPO_WORK_ID, claim["work_id"])
        self.assertEqual("writer-1", repo_workspace.check_owner(self.repo, REPO_WORK_ID, "writer-1")["writer"])
        self.write_accepted_evidence()

    def write_accepted_evidence(self) -> None:
        work = self.repo / "docs" / "work" / REPO_WORK_ID
        evidence_dir = work / "evidence"
        snapshot_result = self.run_gate("snapshot")
        self.assertEqual(0, snapshot_result.returncode, snapshot_result.stderr)
        snapshot = json.loads(snapshot_result.stdout)["product_sha256"]
        lines = {
            "writer.md": f"- context: writer-1\n- snapshot: {snapshot}\n",
            "review.md": f"- context: reviewer-2\n- verdict: APPROVED\n- snapshot: {snapshot}\n",
            "acceptance.md": (f"- work_id: {REPO_WORK_ID}\n- version: acceptance-1\n"
                              f"- snapshot: {snapshot}\n- verdict: ACCEPTED\n"),
            "check.log": "Working directory: .\nCommand: python -m unittest\nExit code: 0\n1 test passed\n",
        }
        for name, contents in lines.items():
            (evidence_dir / name).write_text(contents, encoding="utf-8")

        def reference(name: str, claims: dict[str, int]) -> dict:
            path = evidence_dir / name
            content = path.read_text(encoding="utf-8").splitlines()
            return {
                "path": f"docs/work/{REPO_WORK_ID}/evidence/{name}",
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "claims": {key: {"line": index, "text": content[index - 1]}
                           for key, index in claims.items()},
            }

        writer_ref = reference("writer.md", {"context": 1, "snapshot": 2})
        review_ref = reference("review.md", {"context": 1, "verdict": 2, "snapshot": 3})
        acceptance_ref = reference("acceptance.md", {
            "work_id": 1, "version": 2, "snapshot": 3, "verdict": 4,
        })
        check_ref = reference("check.log", {"cwd": 1, "command": 2, "exit_code": 3})
        check_ref.update(line=4, text="1 test passed")
        quality = {
            "schema": "megin-repo-quality-evidence/v1",
            "work_id": REPO_WORK_ID,
            "plan_version": "plan-1",
            "snapshot": snapshot,
            "writer": {"context": "writer-1", "snapshot": snapshot, "source": writer_ref},
            "sources": [],
            "checks": [{"id": "unit", "status": "passed", "exit_code": 0,
                        "executed": 1, "failed": 0, "skipped": 0,
                        "snapshot": snapshot, "output": check_ref}],
            "review": {"context": "reviewer-2", "verdict": "APPROVED",
                       "snapshot": snapshot, "source": review_ref},
            "acceptance": {"work_id": REPO_WORK_ID, "version": "acceptance-1",
                           "snapshot": snapshot, "verdict": "ACCEPTED",
                           "source": acceptance_ref},
        }
        (evidence_dir / "quality.json").write_text(
            json.dumps(quality, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8",
        )
        self.snapshot = snapshot

    def stage_accepted_snapshot(self) -> None:
        workflow = self.repo / "docs" / "work" / REPO_WORK_ID / "workflow.md"
        workflow.write_text(workflow.read_text(encoding="utf-8").replace(
            "- phase: implementation", "- phase: delivery"), encoding="utf-8")
        work = f"docs/work/{REPO_WORK_ID}"
        self.git("add", "app.py", f"{work}/requirements.md", f"{work}/plan-1/plan.md",
                 f"{work}/plan-1/quality-contract.json")

    def test_remote_is_optional_and_full_local_workflow_completes(self) -> None:
        self.prepare_work()
        for gate in ("review", "acceptance"):
            result = self.run_gate("check", gate)
            self.assertEqual(0, result.returncode, result.stderr + result.stdout)
        self.stage_accepted_snapshot()
        delivery_gate = self.run_gate("check", "delivery")
        self.assertEqual(0, delivery_gate.returncode, delivery_gate.stderr + delivery_gate.stdout)
        receipt = {
            "schema": "megin-repo-delivery-result/v1", "work_id": REPO_WORK_ID,
            "plan_version": "plan-1", "accepted_snapshot": self.snapshot,
            "delivery_gate": {
                "stdout": delivery_gate.stdout, "exit_code": delivery_gate.returncode,
                "sha256": hashlib.sha256(delivery_gate.stdout.encode("utf-8")).hexdigest(),
            },
        }
        delivery_path = self.repo / "docs" / "work" / REPO_WORK_ID / "evidence" / "delivery.json"
        delivery_path.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        self.git("commit", "-m", "accepted feature")
        feature_commit = self.git("rev-parse", "HEAD").stdout.strip()
        self.git("switch", "main")
        self.git("merge", "--no-ff", "--no-edit", f"feature/{REPO_WORK_ID}")
        merge_commit = self.git("rev-parse", "HEAD").stdout.strip()
        receipt.update(feature_commit=feature_commit, merge_commit=merge_commit)
        delivery_path.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        workflow = self.repo / "docs" / "work" / REPO_WORK_ID / "workflow.md"
        workflow.write_text(workflow.read_text(encoding="utf-8").replace(
            "- status: active", "- status: complete"), encoding="utf-8")
        completion = self.run_gate("check", "completion")
        self.assertEqual(0, completion.returncode, completion.stderr + completion.stdout)
        self.assertTrue(json.loads(completion.stdout)["ok"])
        released = repo_workspace.release(self.repo, REPO_WORK_ID, "writer-1")
        self.assertTrue(released["released"])
        self.assertFalse((self.repo / ".megin" / "workspace.lock.json").exists())

    def test_selected_remote_advance_blocks_delivery(self) -> None:
        self.prepare_work(with_remote=True)
        for gate in ("review", "acceptance"):
            result = self.run_gate("check", gate)
            self.assertEqual(0, result.returncode, result.stderr + result.stdout)
        self.git("switch", "-c", "remote-advance", "main")
        (self.repo / "remote.txt").write_text("advanced remotely\n", encoding="utf-8")
        self.git("add", "remote.txt")
        self.git("commit", "-m", "advance remote base")
        advanced = self.git("rev-parse", "HEAD").stdout.strip()
        self.git("push", "origin", f"{advanced}:refs/heads/main")
        self.git("switch", f"feature/{REPO_WORK_ID}")
        self.stage_accepted_snapshot()
        result = self.run_gate("check", "delivery")
        self.assertEqual(1, result.returncode, result.stderr + result.stdout)
        self.assertIn("remote base no longer matches approved base_commit", result.stdout)


if __name__ == "__main__":
    unittest.main()
