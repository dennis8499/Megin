"""The parallel runner preserves serial unittest coverage and failures."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/run_unittest.py"
spec = importlib.util.spec_from_file_location("megin_test_runner", SCRIPT)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class TestRunnerTests(unittest.TestCase):
    def test_stable_shards_partition_every_id_exactly_once(self):
        ids = [f"fixture.Case.test_{index}" for index in range(101)]
        shards = [runner.shard_ids(ids, index, 3) for index in range(3)]
        self.assertTrue(runner.coverage(ids, sum(shards, []))["ok"])
        self.assertEqual(shards[1], runner.shard_ids(list(reversed(ids)), 1, 3))
        for index, count in ((-1, 2), (2, 2), (0, 0)):
            with self.subTest(index=index, count=count), self.assertRaises(ValueError):
                runner.shard_ids(ids, index, count)

    def test_coverage_rejects_omitted_duplicate_and_unexpected_ids(self):
        result = runner.coverage(["a", "b"], ["a", "a", "c"])
        self.assertFalse(result["ok"])
        self.assertEqual(result["missing"], ["b"])
        self.assertEqual(result["duplicates"], ["a"])
        self.assertEqual(result["unexpected"], ["c"])

    def test_missing_legacy_integration_dependency_fails_before_execution(self):
        ids = ["test_native_v2.NativeV2Tests.test_v2_receipt_passes_standalone_mergereviewer"]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with mock.patch.dict(runner.os.environ, {"MEGIN_TEST_MERGE_REVIEWER_SCRIPTS": str(root)}):
                self.assertEqual(runner.validate_dependencies(["other.Case.test_behavior"]), {})
                with self.assertRaisesRegex(ValueError, "MEGIN_TEST_MERGE_REVIEWER_SCRIPTS"):
                    runner.validate_dependencies(ids)
                (root / "delivery_binding.py").write_text("fixture\n", encoding="utf-8")
                self.assertEqual(runner.validate_dependencies(ids)["merge_reviewer_scripts"], str(root.resolve()))

    def test_isolated_workers_report_timings_failures_and_serial_parity(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "test_fixture.py").write_text(
                "import unittest\nclass Case(unittest.TestCase):\n"
                " def test_pass(self): self.assertTrue(True)\n"
                " @unittest.skip('fixture')\n def test_skip(self): pass\n"
                " def test_fail(self): self.fail('preserved assertion')\n", encoding="utf-8")
            reports = []
            for workers in (1, 2):
                output = root / f"results-{workers}.json"
                process = subprocess.run([sys.executable, "-B", str(SCRIPT), "--workers", str(workers),
                                          "--start-directory", str(root), "--output", str(output)],
                                         capture_output=True, text=True, encoding="utf-8")
                self.assertEqual(process.returncode, 1, process.stdout + process.stderr)
                report = json.loads(output.read_text(encoding="utf-8"))
                self.assertTrue(report["coverage"]["ok"])
                self.assertEqual(len(report["tests"]), 3)
                self.assertEqual({row["outcome"] for row in report["tests"]}, {"passed", "failed", "skipped"})
                self.assertTrue(all(row["seconds"] >= 0 for row in report["tests"]))
                self.assertIn("preserved assertion", process.stderr)
                self.assertTrue(all(Path(worker["log"]).is_file() for worker in report["workers"]))
                reports.append(report)
            self.assertEqual(reports[0]["inventory"], reports[1]["inventory"])
            self.assertEqual([row["id"] for row in reports[0]["tests"]], [row["id"] for row in reports[1]["tests"]])

    def test_discovery_import_error_is_a_failure_not_an_empty_success(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "test_broken.py").write_text("raise ImportError('fixture import failure')\n", encoding="utf-8")
            process = subprocess.run([sys.executable, "-B", str(SCRIPT), "--start-directory", str(root), "--list"],
                                     capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(process.returncode, 2)
            self.assertIn("fixture import failure", process.stdout)


if __name__ == "__main__":
    unittest.main()
