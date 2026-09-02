#!/usr/bin/env python3
"""Focused inner tests for query and context contracts."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import unittest
from unittest import mock
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from knowledge_cli import main as knowledge_main
from test_behavior import (
    _build_golden_fixture,
    _build_retrieval_fixture,
    _evaluate_golden,
    _remove_fixture,
    _tree_snapshot,
)


class QueryCliTests(unittest.TestCase):
    fixture_root: Path

    def setUp(self) -> None:
        self.repo = _build_retrieval_fixture(self.fixture_root)

    def tearDown(self) -> None:
        _remove_fixture(self.fixture_root)

    def _invoke(self, arguments: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            exit_code = knowledge_main(arguments)
        return exit_code, stdout.getvalue(), stderr.getvalue()

    def test_query_returns_closed_context_without_writes(self) -> None:
        before = _tree_snapshot(self.repo)
        exit_code, stdout, stderr = self._invoke(
            [
                "query",
                "--repo",
                str(self.repo),
                "--stage",
                "ad-hoc",
                "--query",
                "capability token",
            ]
        )
        self.assertEqual(0, exit_code)
        self.assertEqual("", stderr)
        context = json.loads(stdout)
        self.assertEqual(
            {"schema", "stage", "query", "results", "diagnostics", "generated_at"},
            set(context),
        )
        self.assertEqual("knowledge-context/v1", context["schema"])
        self.assertLessEqual(len(context["results"]), 5)
        self.assertEqual(before, _tree_snapshot(self.repo))

    def test_invalid_query_returns_versioned_error(self) -> None:
        exit_code, stdout, stderr = self._invoke(
            [
                "query",
                "--repo",
                str(self.repo),
                "--stage",
                "ad-hoc",
                "--query",
                "   ",
            ]
        )
        self.assertEqual(2, exit_code)
        self.assertEqual("", stdout)
        error = json.loads(stderr)
        self.assertEqual(
            {"schema", "code", "message", "evidence_refs", "recoverable"},
            set(error),
        )
        self.assertEqual("knowledge-error/v1", error["schema"])
        self.assertEqual("INVALID_QUERY", error["code"])
        self.assertFalse(error["recoverable"])

    def test_ranking_uses_authority_and_stage_without_recency(self) -> None:
        exit_code, stdout, stderr = self._invoke(
            [
                "query",
                "--repo",
                str(self.repo),
                "--stage",
                "requirements",
                "--query",
                "capability token",
            ]
        )
        self.assertEqual(0, exit_code)
        self.assertEqual("", stderr)
        results = json.loads(stdout)["results"]
        self.assertGreaterEqual(len(results), 2)
        self.assertEqual("canonical", results[0]["authority"])
        self.assertEqual(1260, results[0]["score"])
        self.assertIn("stage:requirements", results[0]["match_reasons"])
        self.assertTrue(all(item["lifecycle"] == "current" for item in results))
        self.assertGreater(results[0]["score"], results[-1]["score"])

    def test_golden_evaluator_enforces_recall_and_citations(self) -> None:
        repo, cases = _build_golden_fixture(self.fixture_root)
        report = _evaluate_golden(repo, cases)
        self.assertEqual(20, report["queries"])
        self.assertGreaterEqual(report["top_five_hits"], 18)
        self.assertEqual(report["citation_count"], report["valid_citations"])
        self.assertEqual(0, report["ineligible_hits"])

    def test_current_claim_source_drift_is_excluded_without_aborting_query(self) -> None:
        source = self.repo / "src/stale-boundary.md"
        source.write_text("Changed current claim source.\n", encoding="utf-8", newline="\n")
        exit_code, stdout, stderr = self._invoke(
            [
                "query",
                "--repo",
                str(self.repo),
                "--stage",
                "requirements",
                "--query",
                "stale capability token",
            ]
        )
        self.assertEqual(0, exit_code, stderr)
        self.assertEqual("", stderr)
        self.assertNotIn(
            "docs/knowledge/incidents/stale-capability-token.md",
            {item["path"] for item in json.loads(stdout)["results"]},
        )

    def test_same_query_cache_is_read_only_and_invalidates_on_byte_drift(self) -> None:
        import knowledge_query

        arguments = [
            "query",
            "--repo",
            str(self.repo),
            "--stage",
            "requirements",
            "--query",
            "capability token",
        ]
        first = self._invoke(arguments)
        self.assertEqual(0, first[0], first[2])
        with mock.patch("knowledge_query._run", wraps=knowledge_query._run) as observed:
            second = self._invoke(arguments)
        self.assertEqual(0, second[0], second[2])
        self.assertEqual(json.loads(first[1])["results"], json.loads(second[1])["results"])
        self.assertFalse(
            any(call.args[0][0] == "rg" for call in observed.call_args_list),
            "same repository bytes and query should reuse the process-local match index",
        )

        source = self.repo / "src/security-boundary.md"
        source.write_text(
            "Capability tokens define the changed authorization boundary.\n",
            encoding="utf-8",
            newline="\n",
        )
        with mock.patch("knowledge_query._run", wraps=knowledge_query._run) as invalidated:
            third = self._invoke(arguments)
        self.assertEqual(0, third[0], third[2])
        self.assertTrue(
            any(call.args[0][0] == "rg" for call in invalidated.call_args_list),
            "tracked byte drift must invalidate cached matches",
        )

    def test_cache_hit_rejects_drift_after_fingerprint_before_source_read(self) -> None:
        import knowledge_query

        arguments = [
            "query",
            "--repo",
            str(self.repo),
            "--stage",
            "requirements",
            "--query",
            "capability token",
        ]
        warmed = self._invoke(arguments)
        self.assertEqual(0, warmed[0], warmed[2])

        source = self.repo / "src/security-boundary.md"
        original_fingerprint = knowledge_query._match_cache_fingerprint
        drift_injected = False

        def fingerprint_then_drift(repo: Path) -> str | None:
            nonlocal drift_injected
            fingerprint = original_fingerprint(repo)
            if not drift_injected:
                source.write_text(
                    "Unrelated prefix.\n"
                    "Capability tokens define the authorization boundary.\n",
                    encoding="utf-8",
                    newline="\n",
                )
                drift_injected = True
            return fingerprint

        with mock.patch(
            "knowledge_query._match_cache_fingerprint",
            side_effect=fingerprint_then_drift,
        ):
            exit_code, stdout, stderr = self._invoke(arguments)

        self.assertTrue(drift_injected)
        self.assertEqual(3, exit_code, stderr)
        self.assertEqual("", stdout)
        error = json.loads(stderr)
        self.assertEqual("SOURCE_DRIFT", error["code"])
        self.assertTrue(error["recoverable"])

    def test_cache_hit_rejects_sidecar_drift_before_return(self) -> None:
        import knowledge_query

        arguments = [
            "query",
            "--repo",
            str(self.repo),
            "--stage",
            "requirements",
            "--query",
            "capability token",
        ]
        warmed = self._invoke(arguments)
        self.assertEqual(0, warmed[0], warmed[2])
        self.assertTrue(
            any(item["authority"] == "canonical" for item in json.loads(warmed[1])["results"])
        )

        sidecar_path = (
            self.repo
            / "docs"
            / "knowledge"
            / "meta"
            / "pages"
            / "page-security-capability-token.json"
        )
        original_validator = knowledge_query._validate_result_snapshot
        drift_injected = False

        def drift_sidecar_then_validate(*args: object, **kwargs: object) -> None:
            nonlocal drift_injected
            sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
            sidecar["lifecycle"] = "stale"
            sidecar["claims"][0]["lifecycle"] = "stale"
            sidecar_path.write_text(
                json.dumps(sidecar, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
                newline="\n",
            )
            drift_injected = True
            original_validator(*args, **kwargs)

        with mock.patch(
            "knowledge_query._validate_result_snapshot",
            side_effect=drift_sidecar_then_validate,
        ):
            exit_code, stdout, stderr = self._invoke(arguments)

        self.assertTrue(drift_injected)
        self.assertEqual(3, exit_code, stderr)
        self.assertEqual("", stdout)
        error = json.loads(stderr)
        self.assertEqual("SOURCE_DRIFT", error["code"])
        self.assertTrue(error["recoverable"])

    def test_redirected_parent_is_ineligible_for_query_reads(self) -> None:
        tracked_parent = self.repo / "src/redirected-parent"
        tracked_source = tracked_parent / "external.md"
        tracked_parent.mkdir(parents=True)
        tracked_source.write_text("Redirected evidence token.\n", encoding="utf-8", newline="\n")
        from test_behavior import _git

        _git(self.repo, "add", ".")
        external = self.fixture_root / "redirect-target"
        external.mkdir(parents=True)
        (external / "external.md").write_text(
            "Redirected evidence token.\n",
            encoding="utf-8",
            newline="\n",
        )
        shutil.rmtree(tracked_parent)
        try:
            os.symlink(external, tracked_parent, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            if os.name != "nt":
                self.fail(f"REPARSE_CAPABILITY_REQUIRED: {exc}")
            powershell = shutil.which("pwsh") or shutil.which("powershell")
            if powershell is None:
                self.fail(f"REPARSE_CAPABILITY_REQUIRED: {exc}")
            completed = subprocess.run(
                [
                    powershell,
                    "-NoLogo",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    (
                        "$ErrorActionPreference='Stop'; "
                        "New-Item -ItemType Junction "
                        "-Path $env:KNOWLEDGE_TEST_LINK "
                        "-Target $env:KNOWLEDGE_TEST_TARGET "
                        "| Out-Null"
                    ),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                env={
                    **os.environ,
                    "KNOWLEDGE_TEST_LINK": str(tracked_parent),
                    "KNOWLEDGE_TEST_TARGET": str(external),
                },
                shell=False,
            )
            if completed.returncode != 0:
                detail = completed.stderr.decode("utf-8", errors="replace").strip()
                self.fail(f"REPARSE_CAPABILITY_REQUIRED: {detail or exc}")
        try:
            from knowledge_query import KnowledgeError, _eligible_paths, _read_eligible

            eligible = _eligible_paths(self.repo)
            self.assertNotIn("src/redirected-parent/external.md", eligible)
            with self.assertRaises(KnowledgeError) as raised:
                _read_eligible(self.repo, "src/redirected-parent/external.md", eligible)
            self.assertEqual("SOURCE_INELIGIBLE", raised.exception.code)
        finally:
            is_junction = getattr(tracked_parent, "is_junction", lambda: False)
            self.assertTrue(tracked_parent.is_symlink() or is_junction())
            self.assertEqual(external.resolve(strict=True), tracked_parent.resolve(strict=True))
            if tracked_parent.is_symlink():
                tracked_parent.unlink()
            else:
                os.rmdir(tracked_parent)
            self.assertFalse(tracked_parent.exists())
            self.assertTrue((external / "external.md").is_file())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture-root", type=Path, default=Path(".knowledge-test-tmp"))
    args = parser.parse_args(argv)
    QueryCliTests.fixture_root = args.fixture_root.resolve()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(QueryCliTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    _remove_fixture(QueryCliTests.fixture_root)
    return 0 if result.wasSuccessful() and not result.skipped else 1


if __name__ == "__main__":
    raise SystemExit(main())


