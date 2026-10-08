"""Single-Repo evidence extensions exercised against real Git delivery fixtures."""

from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest

import test_repo_workflow as workflow
import quality_gate as q
import verification_inputs as vi
import behavior_trace as bt
import delivery_receipt as dr


class DeliveryEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.fixture = workflow.RepoWorkflowTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.prepare_work()
        self.repo = self.fixture.repo
        self.work = workflow.REPO_WORK_ID
        self.folder = self.repo / "docs/work" / self.work
        self.contract_path = self.folder / "plan-1/quality-contract.json"
        self.contract = q.read_json(self.contract_path)

    def save_contract(self):
        self.contract_path.write_text(json.dumps(self.contract, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    def enable_inputs(self):
        raw = vi.git_bytes(self.repo, "show", self.fixture.base + ":README.md")
        self.contract["verification_inputs"] = [{"commit": self.fixture.base,
                "files": [{"path": "README.md", "sha256": hashlib.sha256(raw).hexdigest()}], "check_ids": ["unit"]}]
        self.save_contract()
        self.fixture.write_accepted_evidence()
        digest = q.snapshot(self.repo, self.work)["verification_inputs_sha256"]
        path = self.folder / "evidence/check.log"
        path.write_text(path.read_text(encoding="utf-8") + "Verification inputs SHA-256: " + digest + "\n", encoding="utf-8")
        quality_path = self.folder / "evidence/quality.json"
        quality = q.read_json(quality_path)
        result = quality["checks"][0]
        result["verification_inputs_sha256"] = digest
        result["output"]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        result["output"]["claims"]["verification_inputs"] = {"line": 5, "text": "Verification inputs SHA-256: " + digest}
        quality_path.write_text(json.dumps(quality, indent=2) + "\n", encoding="utf-8")
        return raw, digest

    def complete(self):
        self.contract["process_records"].append(f"docs/work/{self.work}/evidence/receipt.json")
        self.save_contract()
        self.fixture.write_accepted_evidence()
        if self.contract.get("verification_inputs"):
            self.enable_inputs()
        self.fixture.stage_accepted_snapshot()
        result = self.fixture.run_gate("check", "delivery")
        self.assertEqual(0, result.returncode, result.stderr + result.stdout)
        delivery = {"schema": "megin-repo-delivery-result/v1", "work_id": self.work,
                    "plan_version": "plan-1", "accepted_snapshot": self.fixture.snapshot,
                    "delivery_gate": {"stdout": result.stdout, "exit_code": 0,
                                      "sha256": hashlib.sha256(result.stdout.encode()).hexdigest()}}
        self.fixture.git("commit", "-m", "accepted feature")
        delivery["feature_commit"] = self.fixture.git("rev-parse", "HEAD").stdout.strip()
        self.fixture.git("switch", "main")
        self.fixture.git("merge", "--no-ff", "--no-edit", f"feature/{self.work}")
        delivery["merge_commit"] = self.fixture.git("rev-parse", "HEAD").stdout.strip()
        (self.folder / "evidence/delivery.json").write_text(json.dumps(delivery, indent=2) + "\n", encoding="utf-8")
        self.assertTrue(q.check_completion(self.repo, self.work)["ok"])
        path = self.folder / "workflow.md"
        path.write_text(path.read_text(encoding="utf-8").replace("- status: active", "- status: complete"), encoding="utf-8")
        return dr.export_receipt(self.repo, self.work)

    def test_legacy_snapshot_has_no_new_fields_or_digest(self):
        snapshot = q.snapshot(self.repo, self.work)
        self.assertNotIn("verification_inputs_sha256", snapshot)
        _, _, records = q.load_contract(self.repo, self.work)
        self.assertEqual(q.digest_entries(q.worktree_entries(self.repo, self.work, records)), snapshot["product_sha256"])

    def test_installed_cli_does_not_create_cache_or_change_product_snapshot(self):
        before = q.snapshot(self.repo, self.work)["product_sha256"]
        scripts = self.repo / ".agents/skills/megin/scripts"
        environment = os.environ.copy()
        environment.pop("PYTHONDONTWRITEBYTECODE", None)
        with tempfile.TemporaryDirectory() as destination:
            commands = [("quality_gate.py", ["snapshot"], 0),
                        ("repo_workspace.py", ["fingerprint"], 0),
                        ("behavior_trace.py", [], 0),
                        ("verification_inputs.py", ["--destination", destination], 0),
                        ("delivery_receipt.py", [], 1)]
            for name, extra, expected in commands:
                arguments = [sys.executable, "-X", "utf8", str(scripts / name), *extra, "--repo", str(self.repo)]
                if name != "repo_workspace.py":
                    arguments.extend(["--work-id", self.work])
                result = subprocess.run(arguments, env=environment, capture_output=True, text=True,
                                        encoding="utf-8", check=False)
                self.assertEqual(expected, result.returncode, result.stdout + result.stderr)
                self.assertNotIn("Traceback", result.stderr)
        self.assertEqual([], list(scripts.rglob("__pycache__")))
        self.assertEqual(before, q.snapshot(self.repo, self.work)["product_sha256"])

    def test_fixed_committed_bytes_are_materialized_and_bound_to_raw_evidence(self):
        raw, digest = self.enable_inputs()
        self.assertTrue(q.check(self.repo, self.work, "review")["ok"])
        inputs = q.fixed_inputs(self.repo, self.contract)
        (self.repo / "README.md").write_text("different live bytes\n", encoding="utf-8")
        self.assertEqual(inputs, q.fixed_inputs(self.repo, self.contract))
        with tempfile.TemporaryDirectory() as tmp:
            result = vi.materialize_inputs(self.repo, self.contract["verification_inputs"], {"unit"}, Path(tmp))
            self.assertEqual(digest, result["sha256"])
            self.assertEqual(raw, (Path(tmp) / self.fixture.base / "README.md").read_bytes())
        quality_path = self.folder / "evidence/quality.json"
        quality = q.read_json(quality_path)
        quality["checks"][0].pop("verification_inputs_sha256")
        quality_path.write_text(json.dumps(quality), encoding="utf-8")
        self.assertTrue(any("fixed input digest" in r for r in q.check(self.repo, self.work, "review")["reasons"]))

    def test_bad_digest_unknown_check_and_sibling_input_are_rejected_before_write(self):
        self.enable_inputs()
        for mutate in (lambda v: v[0]["files"][0].update(sha256="0" * 64),
                       lambda v: v[0].update(check_ids=["missing"]),
                       lambda v: v[0].update(repo_path="sibling"),
                       lambda v: v[0]["files"][0].update(path="../secret")):
            value = copy.deepcopy(self.contract["verification_inputs"])
            mutate(value)
            with tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(ValueError):
                    vi.materialize_inputs(self.repo, value, {"unit"}, Path(tmp))
                self.assertEqual([], list(Path(tmp).iterdir()))
        with self.assertRaises(ValueError):
            vi.materialize_inputs(self.repo, self.contract["verification_inputs"], {"unit"}, self.repo / "inputs")

    def test_scenario_coverage_and_preflight_failures(self):
        contract = {"checks": [{"id": "unit"}], "scenario_ids": ["SCN-01"],
                    "behavior_trace": [{"scenario_id": "SCN-01", "observable": "returns accepted",
                                        "assertion": "assert.equal(value, 'accepted')", "check_id": "unit",
                                        "implementation_paths": ["app.py"]}]}
        bt.validate_trace(contract)
        for mutate in (lambda v: v["behavior_trace"][0].update(assertion=""),
                       lambda v: v["scenario_ids"].append("SCN-02"),
                       lambda v: v["behavior_trace"][0].update(check_id="missing"),
                       lambda v: v["behavior_trace"][0].update(implementation_paths=["../sibling/app.py"])):
            value = copy.deepcopy(contract)
            mutate(value)
            with self.assertRaises(ValueError):
                bt.validate_trace(value)
        probes = {"runner_preflight": [{"id": "python", "argv": [sys.executable, "-c", "print('ready')"], "cwd": "."}]}
        self.assertTrue(bt.preflight(self.repo, probes)["ok"])
        probes["runner_preflight"][0]["argv"] = [sys.executable, "-c", "raise SystemExit(4)"]
        self.assertEqual("failed", bt.preflight(self.repo, probes)["results"][0]["status"])
        probes["runner_preflight"][0]["argv"] = ["missing-megin-runner-9b33"]
        self.assertEqual("environment_error", bt.preflight(self.repo, probes)["results"][0]["status"])
        probes["runner_preflight"].append(copy.deepcopy(probes["runner_preflight"][0]))
        with self.assertRaises(ValueError):
            bt.validate_preflight(probes)

    def test_receipt_survives_later_product_skills_and_branch_changes(self):
        receipt = self.complete()
        (self.repo / "app.py").write_text("value = 'later'\n", encoding="utf-8")
        (self.repo / ".agents/skills/megin/SKILL.md").write_text("later installed skill\n", encoding="utf-8")
        self.fixture.git("add", "app.py", ".agents/skills/megin/SKILL.md")
        self.fixture.git("commit", "-m", "later work")
        self.fixture.git("branch", "-f", f"feature/{self.work}", "HEAD")
        self.assertEqual(receipt, dr.export_receipt(self.repo, self.work))
        (self.folder / "plan-1/plan.md").write_text("tampered approved plan\n", encoding="utf-8")
        with self.assertRaises(q.InvalidEvidence):
            dr.export_receipt(self.repo, self.work)

    def test_receipt_fixed_input_proof_and_output_ownership(self):
        self.enable_inputs()
        receipt = self.complete()
        output = self.folder / "evidence/receipt.json"
        dr.write_receipt(self.repo, self.work, output, receipt)
        dr.write_receipt(self.repo, self.work, output, receipt)
        with self.assertRaises(q.InvalidEvidence):
            dr.write_receipt(self.repo, self.work, self.folder / "evidence/quality.json", receipt)
        output.write_text("different receipt", encoding="utf-8")
        with self.assertRaises(q.InvalidEvidence):
            dr.write_receipt(self.repo, self.work, output, receipt)
        quality_path = self.folder / "evidence/quality.json"
        quality = q.read_json(quality_path)
        quality["checks"][0].pop("verification_inputs_sha256")
        quality_path.write_text(json.dumps(quality), encoding="utf-8")
        with self.assertRaises(q.InvalidEvidence):
            dr.export_receipt(self.repo, self.work)

    def test_delegated_actor_cannot_replace_native_human_acceptance(self):
        path = self.folder / "evidence/quality.json"
        value = q.read_json(path)
        value["acceptance"]["actor_kind"] = "delegated_agent"
        path.write_text(json.dumps(value), encoding="utf-8")
        self.fixture.stage_accepted_snapshot()
        self.assertFalse(q.check(self.repo, self.work, "delivery")["ok"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
