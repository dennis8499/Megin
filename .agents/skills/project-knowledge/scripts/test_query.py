#!/usr/bin/env python3
"""Focused inner tests for query and context contracts."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
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
    _build_query_performance_fixture,
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
        original_capture = knowledge_query._capture_match_cache_snapshot
        drift_injected = False

        def snapshot_then_drift(
            repo: Path,
            cached: object,
        ) -> object:
            nonlocal drift_injected
            snapshot = original_capture(repo, cached)
            if not drift_injected:
                source.write_text(
                    "Unrelated prefix.\n"
                    "Capability tokens define the authorization boundary.\n",
                    encoding="utf-8",
                    newline="\n",
                )
                drift_injected = True
            return snapshot

        with mock.patch(
            "knowledge_query._capture_match_cache_snapshot",
            side_effect=snapshot_then_drift,
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


class PerformanceTests(unittest.TestCase):
    fixture_root: Path

    def setUp(self) -> None:
        self.repo = _build_query_performance_fixture(self.fixture_root)

    def tearDown(self) -> None:
        _remove_fixture(self.fixture_root)

    def _invoke(self, arguments: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            exit_code = knowledge_main(arguments)
        return exit_code, stdout.getvalue(), stderr.getvalue()

    def test_query_reuses_one_snapshot_and_one_fixed_pattern_search(self) -> None:
        import knowledge_query

        calls: list[tuple[list[str], bytes | None]] = []
        real_run = knowledge_query._run
        real_validate = knowledge_query.QuerySearchSession.validate

        def recording_validate(session: object) -> None:
            real_validate(session)

        def recording_run(command: list[str], **kwargs: object) -> object:
            input_bytes = kwargs.get("input_bytes")
            calls.append(
                (
                    list(command),
                    input_bytes if isinstance(input_bytes, bytes) else None,
                )
            )
            return real_run(command, **kwargs)

        knowledge_query._MATCH_CACHE.clear()
        with (
            mock.patch(
                "knowledge_query._match_cache_fingerprint",
                wraps=knowledge_query._match_cache_fingerprint,
            ) as fingerprints,
            mock.patch.object(
                knowledge_query.QuerySearchSession,
                "validate",
                autospec=True,
                side_effect=recording_validate,
            ) as validations,
            mock.patch("knowledge_query._run", side_effect=recording_run),
        ):
            exit_code, stdout, stderr = self._invoke(
                [
                    "query",
                    "--repo",
                    str(self.repo),
                    "--stage",
                    "implementation",
                    "--query",
                    "violet cedar ember quartz",
                ]
            )

        self.assertEqual(0, exit_code, stderr)
        self.assertEqual("", stderr)
        context = json.loads(stdout)
        self.assertEqual(
            [
                ("canonical", "docs/knowledge/topics/session.md", 5),
                ("raw", "evidence/source-000.md", 1),
                ("raw", "evidence/source-001.md", 1),
                ("raw", "evidence/source-002.md", 1),
                ("raw", "evidence/source-003.md", 1),
            ],
            [
                (item["authority"], item["path"], item["start_line"])
                for item in context["results"]
            ],
        )
        self.assertEqual(1, fingerprints.call_count, "one complete pre capture")
        self.assertEqual(1, validations.call_count, "one independent post validate")
        fixed_calls = [
            (command, input_bytes)
            for command, input_bytes in calls
            if command[0] == "rg" and "--fixed-strings" in command
        ]
        self.assertEqual(1, len(fixed_calls), calls)
        fixed_command, fixed_input = fixed_calls[0]
        self.assertIn("--file", fixed_command)
        self.assertIn("--max-count", fixed_command)
        self.assertIsNotNone(fixed_input)
        patterns = fixed_input.decode("utf-8").splitlines()
        self.assertEqual(66, len(patterns))
        self.assertEqual("docs/knowledge/topics/session.md", patterns[0])
        self.assertEqual("evidence/source-064.md", patterns[-1])
        self.assertLessEqual(len(calls), 10, calls)

    def test_warm_query_reuses_staged_snapshot_when_repository_is_stable(self) -> None:
        import knowledge_query

        arguments = [
            "query",
            "--repo",
            str(self.repo),
            "--stage",
            "implementation",
            "--query",
            "violet cedar ember quartz",
        ]
        knowledge_query._MATCH_CACHE.clear()
        warmed = self._invoke(arguments)
        self.assertEqual(0, warmed[0], warmed[2])

        with (
            mock.patch(
                "knowledge_query._match_cache_fingerprint",
                wraps=knowledge_query._match_cache_fingerprint,
            ) as full_fingerprints,
            mock.patch(
                "knowledge_query._match_cache_dirty_fingerprint",
                wraps=knowledge_query._match_cache_dirty_fingerprint,
            ) as dirty_fingerprints,
            mock.patch(
                "knowledge_query._match_cache_index_snapshot",
                wraps=knowledge_query._match_cache_index_snapshot,
            ) as index_snapshots,
            mock.patch("knowledge_query._run", wraps=knowledge_query._run) as runner,
        ):
            repeated = self._invoke(arguments)

        self.assertEqual(0, repeated[0], repeated[2])
        self.assertEqual(
            json.loads(warmed[1])["results"],
            json.loads(repeated[1])["results"],
        )
        self.assertEqual(0, full_fingerprints.call_count)
        self.assertEqual(0, index_snapshots.call_count)
        self.assertEqual(2, dirty_fingerprints.call_count)
        git_calls = [
            call.args[0]
            for call in runner.call_args_list
            if call.args and call.args[0] and call.args[0][0] == "git"
        ]
        self.assertFalse(
            any("--stage" in command for command in git_calls),
            git_calls,
        )

    def test_pathological_fixed_patterns_preserve_regex_fallback_output(self) -> None:
        import knowledge_query

        first = knowledge_query.Match("docs/knowledge/meta/pages/first.json", 1, "first")
        second = knowledge_query.Match("docs/knowledge/meta/pages/second.json", 2, "second")
        patterns = [f"safe-value-{index:03d}" for index in range(64)]
        patterns.append("pathological\nvalue")
        with (
            mock.patch(
                "knowledge_query._rg_matches",
                side_effect=([first], [second]),
            ) as fallback,
            mock.patch("knowledge_query._run") as direct_runner,
        ):
            matches = knowledge_query._rg_fixed_matches(
                self.repo,
                patterns,
                roots=("docs/knowledge/meta/pages",),
                session=mock.sentinel.query_session,
            )

        self.assertEqual([first, second], matches)
        self.assertEqual(2, fallback.call_count)
        self.assertTrue(
            all(call.kwargs["session"] is mock.sentinel.query_session for call in fallback.call_args_list)
        )
        self.assertTrue(
            all(call.kwargs["roots"] == ("docs/knowledge/meta/pages",) for call in fallback.call_args_list)
        )
        direct_runner.assert_not_called()

    def test_large_index_search_overlays_dirty_and_untracked_worktree_bytes(self) -> None:
        import knowledge_query

        dirty_path = self.repo / "evidence" / "source-000.md"
        dirty_path.write_text(
            "saffron tide worktree replacement.\n",
            encoding="utf-8",
            newline="\n",
        )
        untracked_path = self.repo / "evidence" / "untracked.md"
        untracked_path.write_text(
            "saffron tide untracked addition.\n",
            encoding="utf-8",
            newline="\n",
        )
        commands: list[list[str]] = []
        real_run = knowledge_query._run

        def recording_run(command: list[str], **kwargs: object) -> object:
            commands.append(list(command))
            return real_run(command, **kwargs)

        knowledge_query._MATCH_CACHE.clear()
        with (
            mock.patch.object(knowledge_query, "INDEX_SEARCH_MIN_TRACKED_PATHS", 1),
            mock.patch("knowledge_query._run", side_effect=recording_run),
        ):
            replacement = knowledge_query.query_repository(
                str(self.repo),
                stage="implementation",
                query="saffron tide",
            )
            original = knowledge_query.query_repository(
                str(self.repo),
                stage="implementation",
                query="violet cedar ember quartz",
            )

        replacement_paths = {
            item["path"]
            for item in replacement["results"]
            if item["authority"] == "raw"
        }
        self.assertEqual(
            {"evidence/source-000.md", "evidence/untracked.md"},
            replacement_paths,
        )
        self.assertNotIn(
            "evidence/source-000.md",
            {item["path"] for item in original["results"]},
        )
        self.assertTrue(
            any(
                command[0] == "git"
                and "grep" in command
                and "--cached" in command
                for command in commands
            ),
            commands,
        )
        self.assertFalse(
            any(command[0] == "rg" and command[-1] == "." for command in commands),
            commands,
        )
        overlay_roots = {
            value
            for command in commands
            if command[0] == "rg"
            for value in command
            if value in {"evidence/source-000.md", "evidence/untracked.md"}
        }
        self.assertEqual(
            {"evidence/source-000.md", "evidence/untracked.md"},
            overlay_roots,
        )

    def test_large_index_search_falls_back_for_semantic_attributes(self) -> None:
        import knowledge_query

        (self.repo / ".gitattributes").write_text(
            "*.md filter=semantic-transform\n",
            encoding="utf-8",
            newline="\n",
        )
        subprocess.run(
            ["git", "add", "--", ".gitattributes"],
            cwd=self.repo,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            shell=False,
        )
        commands: list[list[str]] = []
        real_run = knowledge_query._run

        def recording_run(command: list[str], **kwargs: object) -> object:
            commands.append(list(command))
            return real_run(command, **kwargs)

        knowledge_query._MATCH_CACHE.clear()
        with (
            mock.patch.object(knowledge_query, "INDEX_SEARCH_MIN_TRACKED_PATHS", 1),
            mock.patch("knowledge_query._run", side_effect=recording_run),
        ):
            report = knowledge_query.query_repository(
                str(self.repo),
                stage="implementation",
                query="violet cedar ember quartz",
            )

        self.assertTrue(report["results"])
        self.assertTrue(
            any(command[0] == "rg" and command[-1] == "." for command in commands),
            commands,
        )
        self.assertFalse(
            any(
                command[0] == "git"
                and "grep" in command
                and "--cached" in command
                for command in commands
            ),
            commands,
        )
        self.assertFalse(
            any(
                ".gitattributes" in command or "**/.gitattributes" in command
                for command in commands
            ),
            "tracked attribute paths must be reused from the staged snapshot",
        )

    def test_fingerprint_splits_staged_dirty_and_untracked_inventory(self) -> None:
        import knowledge_query

        (self.repo / ".gitattributes").write_text(
            "*.md text\n",
            encoding="utf-8",
            newline="\n",
        )
        subprocess.run(
            ["git", "add", "--", ".gitattributes"],
            cwd=self.repo,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            shell=False,
        )
        dirty_path = self.repo / "evidence" / "source-064.md"
        dirty_path.write_text(
            "violet cedar ember quartz changed source 064.\n",
            encoding="utf-8",
            newline="\n",
        )
        untracked_path = self.repo / "untracked-evidence.md"
        untracked_path.write_text(
            "violet cedar ember quartz untracked.\n",
            encoding="utf-8",
            newline="\n",
        )

        staged = subprocess.run(
            [
                "git",
                "-c",
                "core.quotepath=false",
                "ls-files",
                "--stage",
                "-v",
                "-z",
                "--",
            ],
            cwd=self.repo,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            shell=False,
        ).stdout
        tracked_dirty = subprocess.run(
            [
                "git",
                "-c",
                "core.quotepath=false",
                "diff-files",
                "--name-only",
                "-z",
                "--",
            ],
            cwd=self.repo,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            shell=False,
        ).stdout
        untracked = subprocess.run(
            [
                "git",
                "-c",
                "core.quotepath=false",
                "ls-files",
                "--others",
                "--exclude-standard",
                "-z",
                "--",
            ],
            cwd=self.repo,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            shell=False,
        ).stdout
        dirty_records = sorted(
            {
                value
                for stream in (tracked_dirty, untracked)
                for value in stream.split(b"\0")
                if value
            }
        )
        dirty = b"\0".join(dirty_records) + (b"\0" if dirty_records else b"")
        digest = hashlib.sha256()
        for label, value in ((b"staged", staged), (b"dirty", dirty)):
            digest.update(label)
            digest.update(len(value).to_bytes(8, "big"))
            digest.update(value)
        for raw_path in sorted({value for value in dirty.split(b"\0") if value}):
            relative = knowledge_query.normalized_path(raw_path.decode("utf-8"))
            lexical = self.repo / Path(*relative.split("/"))
            digest.update(len(raw_path).to_bytes(8, "big"))
            digest.update(raw_path)
            if lexical.exists():
                digest.update(hashlib.sha256(lexical.read_bytes()).digest())
            else:
                digest.update(b"missing")
        expected = digest.hexdigest()

        with mock.patch("knowledge_query._run", wraps=knowledge_query._run) as runner:
            actual = knowledge_query._match_cache_fingerprint(self.repo)

        self.assertEqual(expected, actual)
        self.assertIsNotNone(actual)
        self.assertEqual((".gitattributes",), actual.attribute_paths)
        git_commands = [
            call.args[0]
            for call in runner.call_args_list
            if call.args and call.args[0] and call.args[0][0] == "git"
        ]
        self.assertEqual(
            [
                [
                    "git",
                    "-c",
                    "core.quotepath=false",
                    "ls-files",
                    "--stage",
                    "-v",
                    "-z",
                    "--",
                ],
                [
                    "git",
                    "-c",
                    "core.quotepath=false",
                    "diff-files",
                    "--name-only",
                    "-z",
                    "--",
                ],
                [
                    "git",
                    "-c",
                    "core.quotepath=false",
                    "ls-files",
                    "--others",
                    "--exclude-standard",
                    "-z",
                    "--",
                ],
            ],
            git_commands,
        )

    def test_dirty_fingerprint_splits_tracked_and_untracked_inventory(self) -> None:
        import knowledge_query

        dirty_path = self.repo / "evidence" / "source-064.md"
        dirty_path.write_text(
            "violet cedar ember quartz changed source 064.\n",
            encoding="utf-8",
            newline="\n",
        )
        untracked_path = self.repo / "untracked-evidence.md"
        untracked_path.write_text(
            "violet cedar ember quartz untracked.\n",
            encoding="utf-8",
            newline="\n",
        )
        tracked_dirty = subprocess.run(
            [
                "git",
                "-c",
                "core.quotepath=false",
                "diff-files",
                "--name-only",
                "-z",
                "--",
            ],
            cwd=self.repo,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            shell=False,
        ).stdout
        untracked = subprocess.run(
            [
                "git",
                "-c",
                "core.quotepath=false",
                "ls-files",
                "--others",
                "--exclude-standard",
                "-z",
                "--",
            ],
            cwd=self.repo,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            shell=False,
        ).stdout
        dirty_records = sorted(
            {
                value
                for stream in (tracked_dirty, untracked)
                for value in stream.split(b"\0")
                if value
            }
        )
        dirty = b"\0".join(dirty_records) + (b"\0" if dirty_records else b"")
        expected = knowledge_query._dirty_fingerprint(self.repo, dirty)

        with mock.patch("knowledge_query._run", wraps=knowledge_query._run) as runner:
            actual = knowledge_query._match_cache_dirty_fingerprint(self.repo)

        self.assertEqual(expected, actual)
        git_commands = [
            call.args[0]
            for call in runner.call_args_list
            if call.args and call.args[0] and call.args[0][0] == "git"
        ]
        self.assertEqual(
            [
                [
                    "git",
                    "-c",
                    "core.quotepath=false",
                    "diff-files",
                    "--name-only",
                    "-z",
                    "--",
                ],
                [
                    "git",
                    "-c",
                    "core.quotepath=false",
                    "ls-files",
                    "--others",
                    "--exclude-standard",
                    "-z",
                    "--",
                ],
            ],
            git_commands,
        )

    def test_index_snapshot_resolves_normal_git_directory_without_git_process(self) -> None:
        import knowledge_query

        with mock.patch(
            "knowledge_query._run",
            side_effect=AssertionError("normal repository index lookup must be direct"),
        ) as runner:
            snapshot = knowledge_query._match_cache_index_snapshot(self.repo)

        self.assertIsNotNone(snapshot)
        index_path, index_fingerprint = snapshot
        self.assertEqual(self.repo / ".git" / "index", index_path)
        self.assertEqual(
            knowledge_query._match_cache_index_fingerprint(index_path),
            index_fingerprint,
        )
        runner.assert_not_called()

    def test_benchmark_preserves_warm_samples_and_adds_fresh_cold_samples(self) -> None:
        import knowledge_benchmark

        _remove_fixture(self.fixture_root)
        with (
            mock.patch.object(knowledge_benchmark, "FILE_COUNT", 250),
            mock.patch.object(knowledge_benchmark, "PAGE_COUNT", 20),
            mock.patch.object(
                knowledge_benchmark,
                "EXPECTED_FUNCTIONAL_SHA256",
                "6310a73a73d1beb175615d927b429bce350694a95a131a1c68356a69d9f6ba32",
            ),
            mock.patch.object(
                knowledge_benchmark,
                "_cold_query",
                wraps=knowledge_benchmark._cold_query,
            ) as cold_queries,
        ):
            report = knowledge_benchmark.run_benchmark(
                self.fixture_root,
                file_count=250,
                page_count=20,
            )

        durations = report["durations_seconds"]
        self.assertEqual(5, len(durations["queries"]))
        self.assertEqual(5, len(durations["cold_queries"]))
        self.assertEqual(6, cold_queries.call_count)
        self.assertEqual(
            cold_queries.call_args_list[0].kwargs,
            cold_queries.call_args_list[1].kwargs,
        )
        self.assertGreaterEqual(durations["fixture_setup"], 0.0)
        self.assertEqual(report["warm_queries_sha256"], report["cold_queries_sha256"])
        self.assertFalse(self.fixture_root.exists())

    def test_fixture_build_creates_each_planned_directory_once(self) -> None:
        import knowledge_benchmark

        _remove_fixture(self.fixture_root)
        mkdir_calls: list[Path] = []
        git_calls: list[tuple[list[str], bytes | None]] = []
        real_mkdir = Path.mkdir
        real_run = knowledge_benchmark.subprocess.run

        def recording_mkdir(path: Path, *args: object, **kwargs: object) -> None:
            mkdir_calls.append(path.resolve(strict=False))
            real_mkdir(path, *args, **kwargs)

        def recording_run(command: list[str], **kwargs: object) -> object:
            input_bytes = kwargs.get("input")
            git_calls.append(
                (
                    list(command),
                    input_bytes if isinstance(input_bytes, bytes) else None,
                )
            )
            return real_run(command, **kwargs)

        with (
            mock.patch.object(Path, "mkdir", new=recording_mkdir),
            mock.patch("knowledge_benchmark.subprocess.run", side_effect=recording_run),
        ):
            repo = knowledge_benchmark._build_fixture(
                self.fixture_root,
                file_count=50,
                page_count=5,
                reuse_fixture=False,
            )

        expected = {
            self.fixture_root.resolve(strict=False),
            repo.resolve(strict=False),
            *knowledge_benchmark._fixture_parent_directories(
                repo,
                source_count=38,
            ),
        }
        relevant_calls = [path for path in mkdir_calls if path in expected]
        self.assertEqual(expected, set(relevant_calls))
        self.assertEqual(len(expected), len(relevant_calls), relevant_calls)
        self.assertFalse(
            any(call[0][:2] == ["git", "add"] for call in git_calls),
            git_calls,
        )
        import_calls = [
            call for call in git_calls if call[0][:2] == ["git", "fast-import"]
        ]
        self.assertEqual(1, len(import_calls), git_calls)
        import_command, import_input = import_calls[0]
        self.assertEqual(
            ["git", "fast-import", "--quiet"],
            import_command,
        )
        self.assertIsNotNone(import_input)
        import_paths = [
            line.removeprefix(b"M 100644 inline ").decode("utf-8")
            for line in import_input.splitlines()
            if line.startswith(b"M 100644 inline ")
        ]
        self.assertEqual(
            1,
            sum(call[0][:2] == ["git", "read-tree"] for call in git_calls),
            git_calls,
        )
        self.assertEqual(
            1,
            sum(call[0][:2] == ["git", "checkout-index"] for call in git_calls),
            git_calls,
        )
        refresh_calls = [
            index
            for index, call in enumerate(git_calls)
            if call[0][:2] == ["git", "update-index"]
            and "--refresh" in call[0]
        ]
        checkout_calls = [
            index
            for index, call in enumerate(git_calls)
            if call[0][:2] == ["git", "checkout-index"]
        ]
        self.assertEqual(1, len(refresh_calls), git_calls)
        self.assertLess(checkout_calls[0], refresh_calls[0], git_calls)
        tracked = real_run(
            ["git", "ls-files", "-z"],
            cwd=repo,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            shell=False,
        ).stdout
        tracked_paths = [item.decode("utf-8") for item in tracked.split(b"\0") if item]
        self.assertEqual(50, len(import_paths))
        self.assertEqual(set(tracked_paths), set(import_paths))
        self.assertEqual(len(import_paths), len(set(import_paths)))

    def test_benchmark_cleanup_covers_fixture_build_failure(self) -> None:
        import knowledge_benchmark

        _remove_fixture(self.fixture_root)
        with (
            mock.patch(
                "knowledge_benchmark._write",
                side_effect=RuntimeError("injected fixture write failure"),
            ),
            self.assertRaisesRegex(RuntimeError, "injected fixture write failure"),
        ):
            knowledge_benchmark.run_benchmark(
                self.fixture_root,
                file_count=50,
                page_count=5,
            )
        self.assertFalse(self.fixture_root.exists())

    def test_portability_comparator_requires_cold_warm_hash_contract(self) -> None:
        import compare_portability_reports

        functional = {"schema": "test-functional/v1", "queries": []}
        functional_digest = compare_portability_reports.canonical_sha256(functional)
        query_digest = compare_portability_reports.canonical_sha256(functional["queries"])
        reports = [
            {
                "schema": "knowledge-portability-report/v1",
                "outcome": "passed",
                "host": {"os": os_name},
                "file_count": 50_000,
                "page_count": 5_000,
                "source_file_count": 39_998,
                "total_fixture_files": 50_000,
                "tracked_fixture": True,
                "functional": functional,
                "functional_sha256": functional_digest,
                "warm_queries_sha256": query_digest,
                "cold_queries_sha256": query_digest,
                "durations_seconds": {
                    "queries": [0.1, 0.2, 0.3, 0.4, 0.5],
                    "cold_queries": [0.6, 0.7, 0.8, 0.9, 1.0],
                    "index_candidate": 0.6,
                    "fixture_setup": 1.5,
                },
            }
            for os_name in ("windows", "linux")
        ]
        original = compare_portability_reports.EXPECTED_FUNCTIONAL_SHA256
        compare_portability_reports.EXPECTED_FUNCTIONAL_SHA256 = functional_digest
        try:
            valid = compare_portability_reports.compare_reports(reports)
            legacy = json.loads(json.dumps(reports))
            del legacy[0]["durations_seconds"]["cold_queries"]
            missing_cold = compare_portability_reports.compare_reports(legacy)
            mismatched = json.loads(json.dumps(reports))
            mismatched[1]["cold_queries_sha256"] = "0" * 64
            hash_mismatch = compare_portability_reports.compare_reports(mismatched)
        finally:
            compare_portability_reports.EXPECTED_FUNCTIONAL_SHA256 = original

        self.assertEqual("passed", valid["outcome"])
        self.assertEqual("failed", missing_cold["outcome"])
        self.assertTrue(
            any("cold query durations" in item for item in missing_cold["diagnostics"]),
            missing_cold,
        )
        self.assertEqual("failed", hash_mismatch["outcome"])
        self.assertTrue(
            any("cold/warm query hashes" in item for item in hash_mismatch["diagnostics"]),
            hash_mismatch,
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("test_cases", nargs="*")
    parser.add_argument("--fixture-root", type=Path, default=Path(".knowledge-test-tmp"))
    args = parser.parse_args(argv)
    QueryCliTests.fixture_root = args.fixture_root.resolve()
    PerformanceTests.fixture_root = args.fixture_root.resolve()
    test_cases = {
        "QueryCliTests": QueryCliTests,
        "PerformanceTests": PerformanceTests,
    }
    selected = args.test_cases or list(test_cases)
    unknown = sorted(set(selected) - set(test_cases))
    if unknown:
        parser.error(f"unknown test case: {', '.join(unknown)}")
    suite = unittest.TestSuite(
        unittest.defaultTestLoader.loadTestsFromTestCase(test_cases[name])
        for name in selected
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    _remove_fixture(QueryCliTests.fixture_root)
    return 0 if result.wasSuccessful() and not result.skipped else 1


if __name__ == "__main__":
    raise SystemExit(main())
