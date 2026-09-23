"""Exercise the quality gates against disposable Git repositories."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / ".agents/skills/megin/scripts/quality_gate.py"
WORK_ID = "work-20260922-quality-gates"


class QualityGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.repo = Path(self.temporary.name)
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Quality Gate Test")
        self.git("config", "user.email", "quality@example.invalid")
        (self.repo / "README.md").write_text("base\n", encoding="utf-8")
        self.git("add", "README.md")
        self.git("commit", "-m", "base")
        self.base = self.git("rev-parse", "HEAD").stdout.strip()
        self.git("switch", "-c", f"feature/{WORK_ID}")
        self.work = self.repo / "docs/work" / WORK_ID
        (self.work / "plan-3").mkdir(parents=True)
        (self.work / "evidence").mkdir()
        (self.repo / "app.py").write_text("value = 1\n", encoding="utf-8")
        self.contract = {
            "schema": "megin-quality-contract/v1",
            "work_id": WORK_ID,
            "plan_version": "plan-3",
            "allowed_paths": ["app.py", f"docs/work/{WORK_ID}/"],
            "checks": [{"id": "unit", "kind": "test", "command": "test unit"}],
            "process_records": [
                f"docs/work/{WORK_ID}/evidence/quality.json",
                f"docs/work/{WORK_ID}/evidence/handoff.md",
                f"docs/work/{WORK_ID}/evidence/unit.log",
                f"docs/work/{WORK_ID}/evidence/review.md",
                f"docs/work/{WORK_ID}/evidence/review-2.md",
                f"docs/work/{WORK_ID}/evidence/acceptance.md",
            ],
        }
        self.write_json("plan-3/quality-contract.json", self.contract)
        (self.work / "plan-3/plan.md").write_text("approved plan\n", encoding="utf-8")
        (self.work / "workflow.md").write_text(
            f"- work_id: {WORK_ID}\n- plan_version: plan-3\n"
            f"- base_branch: main\n- base_commit: {self.base}\n"
            f"- feature_branch: feature/{WORK_ID}\n"
            f"- quality_ref: docs/work/{WORK_ID}/evidence/quality.json\n",
            encoding="utf-8",
        )
        self.write("evidence/handoff.md", "pending\n")
        self.write("evidence/unit.log", "Command: test unit\nExit code: 0\n1 passed\n")
        self.write("evidence/review.md", "pending\n")
        self.write("evidence/acceptance.md", "pending\n")
        first = self.run_gate("snapshot")
        self.assertEqual(0, first.returncode, first.stderr)
        self.snapshot = json.loads(first.stdout)["product_sha256"]
        self.handoff_text = f"- context: writer-1\n- snapshot: {self.snapshot}\n"
        self.review_text = (
            f"- context: reviewer-2\n- verdict: APPROVED\n- snapshot: {self.snapshot}\n"
        )
        self.acceptance_text = (
            f"- work_id: {WORK_ID}\n- version: acceptance-1\n"
            f"- snapshot: {self.snapshot}\n- verdict: ACCEPTED\n"
        )
        self.write("evidence/handoff.md", self.handoff_text)
        self.write("evidence/review.md", self.review_text)
        self.write("evidence/acceptance.md", self.acceptance_text)
        self.evidence = {
            "schema": "megin-quality-evidence/v1",
            "work_id": WORK_ID,
            "plan_version": "plan-3",
            "snapshot": self.snapshot,
            "writer": {
                "context": "writer-1", "snapshot": self.snapshot,
                "source": self.ref("evidence/handoff.md", {"context": 1, "snapshot": 2}),
            },
            "sources": [],
            "checks": [{
                "id": "unit", "status": "passed", "exit_code": 0,
                "executed": 1, "failed": 0, "skipped": 0,
                "snapshot": self.snapshot,
                "output": {
                    **self.ref("evidence/unit.log", {"command": 1, "exit_code": 2}),
                    "line": 3, "text": "1 passed",
                },
            }],
            "review": {
                "context": "reviewer-2", "verdict": "APPROVED",
                "snapshot": self.snapshot,
                "source": self.ref(
                    "evidence/review.md", {"context": 1, "verdict": 2, "snapshot": 3},
                ),
            },
            "acceptance": {
                "work_id": WORK_ID, "version": "acceptance-1",
                "snapshot": self.snapshot, "verdict": "ACCEPTED",
                "source": self.ref(
                    "evidence/acceptance.md",
                    {"work_id": 1, "version": 2, "snapshot": 3, "verdict": 4},
                ),
            },
        }
        self.save_evidence()

    def git(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            ["git", *arguments], cwd=self.repo, text=True, encoding="utf-8",
            errors="replace", capture_output=True, check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        return result

    def write(self, name: str, contents: str) -> None:
        (self.work / name).write_text(contents, encoding="utf-8")

    def write_json(self, name: str, value: object) -> None:
        self.write(name, json.dumps(value, ensure_ascii=False))

    def ref(self, name: str, claims: dict[str, int] | None = None) -> dict[str, object]:
        path = self.work / name
        result: dict[str, object] = {
            "path": path.relative_to(self.repo).as_posix(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        if claims:
            lines = path.read_text(encoding="utf-8").splitlines()
            result["claims"] = {
                name: {"line": number, "text": lines[number - 1]}
                for name, number in claims.items()
            }
        return result

    def save_evidence(self) -> None:
        self.write_json("evidence/quality.json", self.evidence)

    def run_gate(self, action: str, gate: str | None = None) -> subprocess.CompletedProcess[str]:
        arguments = [sys.executable, "-B", str(SCRIPT), action, "--repo", str(self.repo), "--work-id", WORK_ID]
        if gate:
            arguments.extend(["--gate", gate])
        return subprocess.run(arguments, text=True, capture_output=True, check=False)

    def test_complete_evidence_passes_all_three_gates(self) -> None:
        for gate in ("review", "acceptance"):
            result = self.run_gate("check", gate)
            self.assertEqual(0, result.returncode, (gate, result.stdout, result.stderr))
        self.git("add", "-A")
        result = self.run_gate("check", "delivery")
        self.assertEqual(0, result.returncode, (result.stdout, result.stderr))
        delivery = json.loads(result.stdout)
        self.assertEqual(self.snapshot, delivery["staged_snapshot"])
        self.assertIn("app.py", delivery["staged_paths"])

    def test_failed_blocked_skipped_and_zero_tests_stop_acceptance(self) -> None:
        for status, executed, skipped in (
            ("failed", 1, 0), ("blocked", 1, 0), ("not_run", 0, 0),
            ("passed", 0, 0), ("passed", 1, 1),
        ):
            with self.subTest(status=status, executed=executed, skipped=skipped):
                check = self.evidence["checks"][0]
                check.update(status=status, executed=executed, skipped=skipped)
                self.save_evidence()
                self.assertEqual(1, self.run_gate("check", "acceptance").returncode)

    def test_self_review_and_missing_review_stop_acceptance(self) -> None:
        self.evidence["review"]["context"] = "writer-1"
        self.save_evidence()
        self.assertEqual(1, self.run_gate("check", "acceptance").returncode)
        del self.evidence["review"]
        self.save_evidence()
        self.assertEqual(1, self.run_gate("check", "acceptance").returncode)
        self.assertEqual(0, self.run_gate("check", "review").returncode)

    def test_product_drift_including_untracked_file_stops_review(self) -> None:
        (self.repo / "new-file.py").write_text("untracked = True\n", encoding="utf-8")
        self.assertEqual(1, self.run_gate("check", "review").returncode)

    def test_staging_keeps_content_digest_but_is_rejected_before_delivery(self) -> None:
        self.git("add", "app.py")
        self.assertEqual(self.snapshot, json.loads(self.run_gate("snapshot").stdout)["product_sha256"])
        self.assertEqual(1, self.run_gate("check", "review").returncode)

    def test_deletion_changes_snapshot(self) -> None:
        (self.repo / "README.md").unlink()
        self.assertEqual(1, self.run_gate("check", "review").returncode)

    def test_new_process_record_keeps_product_snapshot(self) -> None:
        self.write("evidence/review-2.md", "later review\n")
        self.assertEqual(self.snapshot, json.loads(self.run_gate("snapshot").stdout)["product_sha256"])

    def test_unlisted_executable_evidence_changes_product_snapshot(self) -> None:
        self.write("evidence/executable-fixture.json", '{"behavior": "changed"}\n')
        self.assertNotEqual(
            self.snapshot, json.loads(self.run_gate("snapshot").stdout)["product_sha256"],
        )
        self.assertEqual(1, self.run_gate("check", "review").returncode)

    def test_changed_cited_report_or_contract_stops_gate(self) -> None:
        self.write("evidence/handoff.md", "changed writer result\n")
        self.assertEqual(1, self.run_gate("check", "review").returncode)
        self.write("evidence/handoff.md", self.handoff_text)
        changed = {**self.contract, "checks": [{"id": "unit", "kind": "test", "command": "changed"}]}
        self.write_json("plan-3/quality-contract.json", changed)
        self.assertEqual(1, self.run_gate("check", "review").returncode)

    def test_changed_supporting_source_stops_gate(self) -> None:
        self.evidence["sources"] = [self.ref("evidence/review.md")]
        self.save_evidence()
        self.write("evidence/review.md", "changed review\n")
        self.assertEqual(1, self.run_gate("check", "review").returncode)

    def test_malformed_evidence_is_not_a_gate_failure(self) -> None:
        self.write("evidence/quality.json", "not json")
        self.assertEqual(2, self.run_gate("check", "review").returncode)

    def test_malformed_ids_and_boolean_counts_are_rejected(self) -> None:
        self.contract["checks"] = [{"id": [], "kind": "test", "command": "test unit"}]
        self.write_json("plan-3/quality-contract.json", self.contract)
        self.assertEqual(2, self.run_gate("check", "review").returncode)
        self.contract["checks"] = [{"id": "unit", "kind": "test", "command": "test unit"}]
        self.write_json("plan-3/quality-contract.json", self.contract)
        self.evidence["checks"][0]["executed"] = True
        self.save_evidence()
        self.assertEqual(1, self.run_gate("check", "acceptance").returncode)

    def test_output_count_needs_a_locator_in_raw_log(self) -> None:
        del self.evidence["checks"][0]["output"]["line"]
        self.save_evidence()
        self.assertEqual(1, self.run_gate("check", "acceptance").returncode)

    def test_review_requires_each_approved_result_and_raw_source(self) -> None:
        self.evidence["checks"] = []
        self.save_evidence()
        self.assertEqual(1, self.run_gate("check", "review").returncode)

    def test_review_checks_output_reference_and_per_check_snapshot_separately(self) -> None:
        check = self.evidence["checks"][0]
        original_output = check["output"]
        del check["output"]
        self.save_evidence()
        self.assertEqual(1, self.run_gate("check", "review").returncode)

        check["output"] = original_output
        self.write("evidence/unit.log", "changed output\n")
        self.save_evidence()
        self.assertEqual(1, self.run_gate("check", "review").returncode)

        self.write("evidence/unit.log", "Command: test unit\nExit code: 0\n1 passed\n")
        check["output"] = self.ref(
            "evidence/unit.log", {"command": 1, "exit_code": 2},
        )
        check["output"].update(line=3, text="1 passed")
        check["snapshot"] = "0" * 64
        self.save_evidence()
        self.assertEqual(1, self.run_gate("check", "review").returncode)

    def test_dot_segments_cannot_escape_evidence_directory(self) -> None:
        source = self.ref("plan-3/plan.md")
        source["path"] = f"docs/work/{WORK_ID}/evidence/../plan-3/plan.md"
        self.evidence["writer"]["source"] = source
        self.save_evidence()
        self.assertEqual(2, self.run_gate("check", "review").returncode)

        self.evidence["writer"]["source"] = self.ref(
            "evidence/handoff.md", {"context": 1, "snapshot": 2},
        )
        self.save_evidence()
        workflow = self.work / "workflow.md"
        workflow.write_text(
            workflow.read_text(encoding="utf-8").replace(
                "evidence/quality.json", "evidence/../evidence/quality.json",
            ),
            encoding="utf-8",
        )
        self.assertEqual(2, self.run_gate("check", "review").returncode)

    def test_single_dot_segment_is_not_a_canonical_evidence_path(self) -> None:
        source = self.evidence["writer"]["source"]
        source["path"] = f"docs/work/{WORK_ID}/evidence/./handoff.md"
        self.save_evidence()
        self.assertEqual(2, self.run_gate("check", "review").returncode)

    def test_delivery_compares_staged_bytes_with_accepted_snapshot(self) -> None:
        self.git("add", "-A")
        (self.repo / "app.py").write_text("value = 2\n", encoding="utf-8")
        self.git("add", "app.py")
        (self.repo / "app.py").write_text("value = 1\n", encoding="utf-8")
        result = self.run_gate("check", "delivery")
        self.assertEqual(1, result.returncode)
        self.assertIn("staged product bytes differ", result.stdout)
        self.assertIn("unstaged or untracked product paths", result.stdout)

    def test_delivery_separately_rejects_untracked_product_path(self) -> None:
        self.git("add", "-A")
        (self.repo / "late.py").write_text("late = True\n", encoding="utf-8")
        result = self.run_gate("check", "delivery")
        self.assertEqual(1, result.returncode)
        self.assertIn("unstaged or untracked product paths", result.stdout)

    def test_raw_review_must_agree_with_structured_approval(self) -> None:
        self.write(
            "evidence/review.md",
            f"- context: reviewer-2\n- verdict: CHANGES_REQUIRED\n"
            f"- snapshot: {self.snapshot}\n",
        )
        self.evidence["review"]["source"] = self.ref(
            "evidence/review.md", {"context": 1, "verdict": 2, "snapshot": 3},
        )
        self.save_evidence()
        self.assertEqual(1, self.run_gate("check", "acceptance").returncode)

    def test_contexts_and_acceptance_version_must_be_nonempty_strings(self) -> None:
        self.evidence["writer"]["context"] = ["writer-1"]
        self.evidence["review"]["context"] = {"id": "reviewer-2"}
        self.save_evidence()
        self.assertEqual(1, self.run_gate("check", "acceptance").returncode)

        self.evidence["writer"]["context"] = "writer-1"
        self.evidence["review"]["context"] = "reviewer-2"
        self.evidence["acceptance"]["version"] = {"id": "acceptance-1"}
        self.save_evidence()
        self.git("add", "-A")
        self.assertEqual(1, self.run_gate("check", "delivery").returncode)

    def test_raw_acceptance_must_agree_with_structured_acceptance(self) -> None:
        self.write(
            "evidence/acceptance.md",
            f"- work_id: {WORK_ID}\n- version: acceptance-1\n"
            f"- snapshot: {self.snapshot}\n- verdict: REJECTED\n",
        )
        self.evidence["acceptance"]["source"] = self.ref(
            "evidence/acceptance.md",
            {"work_id": 1, "version": 2, "snapshot": 3, "verdict": 4},
        )
        self.save_evidence()
        self.git("add", "-A")
        self.assertEqual(1, self.run_gate("check", "delivery").returncode)


if __name__ == "__main__":
    unittest.main()
