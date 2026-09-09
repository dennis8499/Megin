#!/usr/bin/env python3
"""BDD and inner tests for the optional Windows tgrep search accelerator."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in os.sys.path:
    os.sys.path.insert(0, str(SCRIPT_DIR))

import knowledge_query
from knowledge_cli import main as knowledge_main


class TgrepFixtureMixin:
    fixture_root: Path

    def setUp(self) -> None:
        self.repo = Path(tempfile.mkdtemp(prefix="tgrep-repo-", dir=self.fixture_root))
        (self.repo / ".gitignore").write_text(".tgrep/\n", encoding="utf-8", newline="\n")
        (self.repo / "docs").mkdir()
        (self.repo / ".agents").mkdir()
        (self.repo / "docs" / "visible.md").write_text(
            "Alpha CJK 測試 visible.\n", encoding="utf-8", newline="\n"
        )
        (self.repo / "docs" / "multiple.md").write_text(
            "repeat marker first\nrepeat marker second\n",
            encoding="utf-8",
            newline="\n",
        )
        (self.repo / "docs" / "crlf.md").write_bytes("CRLF marker\r\n".encode("utf-8"))
        (self.repo / ".agents" / "hidden.md").write_text(
            "Hidden CJK marker.\n", encoding="utf-8", newline="\n"
        )
        self._git("init", "-q")
        self._git("config", "user.email", "tgrep-tests@example.invalid")
        self._git("config", "user.name", "tgrep tests")
        self._git("add", ".")
        self._git("commit", "-qm", "fixture")

    def tearDown(self) -> None:
        def onerror(function: object, path: str, _exc_info: object) -> None:
            try:
                os.chmod(path, 0o700)
                function(path)  # type: ignore[operator]
            except OSError:
                pass

        shutil.rmtree(self.repo, onerror=onerror)

    def _git(self, *arguments: str) -> None:
        completed = subprocess.run(
            ["git", "-C", str(self.repo), *arguments],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            shell=False,
        )
        self.assertEqual(0, completed.returncode, completed.stderr.decode("utf-8", "replace"))

    def _invoke(self, arguments: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            exit_code = knowledge_main(arguments)
        return exit_code, stdout.getvalue(), stderr.getvalue()


def _remove_fixture_root(root: Path) -> None:
    if not root.exists() and not root.is_symlink():
        return

    def onerror(function: object, path: str, _exc_info: object) -> None:
        try:
            os.chmod(path, stat.S_IWRITE)
            function(path)  # type: ignore[operator]
        except OSError:
            pass

    if os.name == "nt":
        os.chmod(root, stat.S_IWRITE)
        shutil.rmtree(root, onerror=onerror)
    else:
        shutil.rmtree(root)
    if root.exists():
        raise AssertionError(f"fixture cleanup failed: {root}")


class TgrepCommandTests(unittest.TestCase):
    def test_search_command_has_ripgrep_compatible_flags_without_hidden(self) -> None:
        command = knowledge_query._tgrep_search_command(
            Path("C:/repo"),
            patterns=["CJK"],
            roots=(".",),
            fixed_strings=False,
            index_path=Path("C:/repo/.tgrep"),
        )
        self.assertTrue(command[0].lower().endswith("tgrep.exe"), command)
        for flag in (
            "--no-heading",
            "--line-number",
            "--with-filename",
            "--null",
            "--ignore-case",
            "--color",
            "never",
            "--index-path",
        ):
            self.assertIn(flag, command)
        self.assertNotIn("--hidden", command)
        self.assertIn("--glob", command)
        self.assertIn("!.git/**", command)
        self.assertIn("--regexp", command)
        self.assertIn("CJK", command)

    def test_fixed_command_uses_literal_repeatable_patterns(self) -> None:
        command = knowledge_query._tgrep_search_command(
            Path("C:/repo"),
            patterns=["CJK", "fixed.value"],
            roots=("docs",),
            fixed_strings=True,
            index_path=Path("C:/repo/.tgrep"),
        )
        self.assertIn("--fixed-strings", command)
        self.assertIn("--max-count", command)
        self.assertEqual("1", command[command.index("--max-count") + 1])
        self.assertNotIn("--file", command)
        self.assertEqual(2, command.count("--regexp"))
        self.assertEqual("docs", command[-1])

    def test_parser_accepts_windows_paths_crlf_and_nul(self) -> None:
        matches = knowledge_query._parse_tgrep_matches(
            ".\\docs\\CJK.md\0 2:測試\r\n".replace("\0 ", "\0").encode("utf-8")
        )
        self.assertEqual(
            [knowledge_query.Match("docs/CJK.md", 2, "測試")],
            matches,
        )

    def test_parser_accepts_tgrep_line_output_with_colons_in_text(self) -> None:
        matches = knowledge_query._parse_tgrep_matches(
            b'.\\docs\\record.json:1:{"confirmed_at":"2026-09-01T13:00:00"}\r\n'
        )
        self.assertEqual(
            [
                knowledge_query.Match(
                    "docs/record.json",
                    1,
                    '{"confirmed_at":"2026-09-01T13:00:00"}',
                )
            ],
            matches,
        )

    def test_exit_one_is_a_successful_no_match(self) -> None:
        completed = subprocess.CompletedProcess(
            ["tgrep.exe"], 1, stdout=b"", stderr=b""
        )
        with mock.patch("knowledge_query._run", return_value=completed):
            matches = knowledge_query._tgrep_search(
                Path("C:/repo"),
                patterns=["missing"],
                roots=(".",),
                fixed_strings=False,
                index_path=Path("C:/repo/.tgrep"),
            )
        self.assertEqual([], matches)

    def test_malformed_output_is_a_fallback_signal(self) -> None:
        completed = subprocess.CompletedProcess(
            ["tgrep.exe"], 0, stdout=b"bad-record", stderr=b""
        )
        with mock.patch("knowledge_query._run", return_value=completed):
            matches = knowledge_query._tgrep_search(
                Path("C:/repo"),
                patterns=["marker"],
                roots=(".",),
                fixed_strings=False,
                index_path=Path("C:/repo/.tgrep"),
            )
        self.assertIsNone(matches)

    def test_index_status_requires_a_complete_report(self) -> None:
        complete = subprocess.CompletedProcess(
            ["tgrep.exe"],
            0,
            stdout=(
                b"Index status for C:/repo\n"
                b"  Files:      3\n"
                b"  Trigrams:   12\n"
                b"  Created:    now\n"
            ),
            stderr=b"",
        )
        binary = Path("C:/repo/tgrep.exe")
        repo = Path("C:/repo")
        index_path = repo / ".tgrep"
        with mock.patch("knowledge_query._run", return_value=complete) as runner:
            self.assertTrue(knowledge_query._tgrep_index_status(binary, repo, index_path))
        self.assertEqual(
            [
                str(binary),
                "status",
                "--index-path",
                str(index_path),
                ".",
            ],
            runner.call_args.args[0],
        )

        incomplete = subprocess.CompletedProcess(
            ["tgrep.exe"],
            0,
            stdout=b"No index found at C:/repo/.tgrep\n",
            stderr=b"",
        )
        with mock.patch("knowledge_query._run", return_value=incomplete):
            self.assertFalse(knowledge_query._tgrep_index_status(binary, repo, index_path))


class TgrepIndexStateTests(TgrepFixtureMixin, unittest.TestCase):
    def test_missing_state_does_not_auto_create_index_or_write_query(self) -> None:
        if os.name == "nt":
            shutil.copy2(Path.cwd() / "tgrep.exe", self.repo / "tgrep.exe")
        before = knowledge_query._tree_snapshot_for_tests(self.repo) if hasattr(
            knowledge_query, "_tree_snapshot_for_tests"
        ) else sorted(
            path.relative_to(self.repo).as_posix()
            for path in self.repo.rglob("*")
            if path.is_file()
        )
        exit_code, stdout, stderr = self._invoke(
            [
                "query",
                "--repo",
                str(self.repo),
                "--stage",
                "ad-hoc",
                "--query",
                "visible marker",
            ]
        )
        self.assertEqual(0, exit_code, stderr)
        self.assertEqual("", stderr)
        self.assertFalse((self.repo / ".tgrep").exists())
        after = knowledge_query._tree_snapshot_for_tests(self.repo) if hasattr(
            knowledge_query, "_tree_snapshot_for_tests"
        ) else sorted(
            path.relative_to(self.repo).as_posix()
            for path in self.repo.rglob("*")
            if path.is_file()
        )
        self.assertEqual(before, after)
        self.assertEqual("knowledge-context/v1", json.loads(stdout)["schema"])

    def test_state_writer_is_atomic_and_has_versioned_schema(self) -> None:
        state_path = self.repo / ".tgrep" / "state.json"
        state = {"schema": "tgrep-index-state/v1", "ready": True}
        knowledge_query._write_tgrep_state(state_path, state)
        self.assertEqual(state, json.loads(state_path.read_text(encoding="utf-8")))
        self.assertFalse(list(state_path.parent.glob("*.tmp")))

    def test_state_mismatch_is_fail_closed(self) -> None:
        state = {
            "schema": "tgrep-index-state/v1",
            "ready": True,
            "binary": {"sha256": "0" * 64, "version": "1.0.4"},
            "index": {"path": ".tgrep", "fingerprint": "0" * 64},
            "repository": {"head": "not-current", "branch": "main"},
        }
        self.assertFalse(knowledge_query._tgrep_state_is_valid(self.repo, state))

    def test_index_status_failure_does_not_publish_ready_state(self) -> None:
        if os.name != "nt":
            return
        shutil.copy2(Path.cwd() / "tgrep.exe", self.repo / "tgrep.exe")
        with mock.patch.object(knowledge_query, "_tgrep_index_status", return_value=False) as status:
            exit_code, stdout, stderr = self._invoke(
                ["tgrep-index", "--repo", str(self.repo), "--force"]
            )
        self.assertEqual(3, exit_code)
        self.assertEqual("", stdout)
        self.assertIn("TGREP_INDEX_STATUS_INVALID", stderr)
        status.assert_called_once()
        self.assertFalse((self.repo / ".tgrep" / "state.json").exists())


class TgrepBehaviorTests(TgrepFixtureMixin, unittest.TestCase):
    def test_ready_index_uses_tgrep_for_worktree_search(self) -> None:
        expected = [knowledge_query.Match("docs/visible.md", 1, "Alpha CJK 測試 visible.")]
        with (
            mock.patch.object(knowledge_query.os, "name", "nt"),
            mock.patch("knowledge_query._tgrep_state_is_valid", return_value=True),
            mock.patch("knowledge_query._tgrep_search", return_value=expected) as tgrep,
            mock.patch("knowledge_query._rg_matches", side_effect=AssertionError("rg fallback")),
        ):
            matches = knowledge_query._search_worktree_regex(
                self.repo,
                "CJK",
                roots=(".",),
            )
        self.assertEqual(expected, matches)
        tgrep.assert_called_once()

    def test_failed_tgrep_is_silent_and_falls_back_to_rg(self) -> None:
        expected = [knowledge_query.Match("docs/visible.md", 1, "Alpha CJK 測試 visible.")]
        with (
            mock.patch.object(knowledge_query.os, "name", "nt"),
            mock.patch("knowledge_query._tgrep_state_is_valid", return_value=True),
            mock.patch("knowledge_query._tgrep_search", return_value=None),
            mock.patch("knowledge_query._rg_matches", return_value=expected) as rg,
        ):
            matches = knowledge_query._search_worktree_regex(
                self.repo,
                "CJK",
                roots=(".",),
            )
        self.assertEqual(expected, matches)
        rg.assert_called_once()


class TgrepWindowsParityTests(TgrepFixtureMixin, unittest.TestCase):
    def test_binary_hash_is_stable_when_bundled(self) -> None:
        binary = Path.cwd() / "tgrep.exe"
        self.assertTrue(binary.is_file())
        digest = hashlib.sha256(binary.read_bytes()).hexdigest()
        self.assertEqual(64, len(digest))
        self.assertEqual("bac0a288f6e588e7708c87ace2e381f50d5190269c471c10e1ffb9c524fc02de", digest)

    def test_indexed_and_rg_worktree_results_are_equal(self) -> None:
        binary = Path.cwd() / "tgrep.exe"
        if os.name != "nt":
            before = sorted(path.relative_to(self.repo).as_posix() for path in self.repo.rglob("*") if path.is_file())
            exit_code, _stdout, stderr = self._invoke(
                ["tgrep-index", "--repo", str(self.repo), "--force"]
            )
            self.assertEqual(4, exit_code)
            self.assertEqual("", _stdout)
            self.assertIn("TGREP_UNSUPPORTED_PLATFORM", stderr)
            after = sorted(path.relative_to(self.repo).as_posix() for path in self.repo.rglob("*") if path.is_file())
            self.assertEqual(before, after)
            return
        shutil.copy2(binary, self.repo / "tgrep.exe")
        exit_code, stdout, stderr = self._invoke(
            ["tgrep-index", "--repo", str(self.repo), "--force"]
        )
        self.assertEqual(0, exit_code, stderr)
        self.assertEqual("", stderr)
        result = json.loads(stdout)
        self.assertEqual("tgrep-index/v1", result["schema"])
        self.assertEqual("ready", result["status"])
        self.assertTrue((self.repo / ".tgrep" / "state.json").is_file())

        knowledge_query._MATCH_CACHE.clear()
        with mock.patch(
            "knowledge_query._tgrep_search",
            wraps=knowledge_query._tgrep_search,
        ) as tgrep_search:
            indexed = knowledge_query._search_worktree_regex(self.repo, "CJK")
        self.assertGreaterEqual(tgrep_search.call_count, 1)
        knowledge_query._MATCH_CACHE.clear()

        with mock.patch(
            "knowledge_query._tgrep_search",
            wraps=knowledge_query._tgrep_search,
        ) as tgrep_search:
            indexed_fixed = knowledge_query._rg_fixed_matches(
                self.repo,
                ["repeat marker"],
                roots=(".",),
            )
        self.assertGreaterEqual(tgrep_search.call_count, 1)
        self.assertEqual(
            [knowledge_query.Match("docs/multiple.md", 1, "repeat marker first")],
            indexed_fixed,
        )

        knowledge_query._MATCH_CACHE.clear()
        with mock.patch("knowledge_query._tgrep_state_is_valid", return_value=False):
            fallback_fixed = knowledge_query._rg_fixed_matches(
                self.repo,
                ["repeat marker"],
                roots=(".",),
            )
        self.assertEqual(indexed_fixed, fallback_fixed)

        knowledge_query._MATCH_CACHE.clear()
        with mock.patch(
            "knowledge_query._tgrep_search",
            wraps=knowledge_query._tgrep_search,
        ) as tgrep_search:
            fixed = knowledge_query._rg_fixed_matches(
                self.repo,
                ["CRLF marker"],
                roots=(".",),
            )
        self.assertGreaterEqual(tgrep_search.call_count, 1)
        self.assertEqual(["docs/crlf.md"], [match.path for match in fixed])
        self.assertEqual("CRLF marker", fixed[0].line_text)

        knowledge_query._MATCH_CACHE.clear()
        with mock.patch("knowledge_query._tgrep_state_is_valid", return_value=False):
            fallback = knowledge_query._search_worktree_regex(self.repo, "CJK")
        self.assertEqual(indexed, fallback)

    def test_staged_snapshot_remains_git_authoritative(self) -> None:
        if os.name != "nt":
            return
        binary = Path.cwd() / "tgrep.exe"
        shutil.copy2(binary, self.repo / "tgrep.exe")
        self._git("add", "tgrep.exe")
        (self.repo / "docs" / "visible.md").write_text(
            "staged marker\n",
            encoding="utf-8",
            newline="\n",
        )
        self._git("add", "docs/visible.md")
        exit_code, _stdout, stderr = self._invoke(
            ["tgrep-index", "--repo", str(self.repo), "--force"]
        )
        self.assertEqual(0, exit_code, stderr)

        knowledge_query._MATCH_CACHE.clear()
        with mock.patch.object(knowledge_query, "INDEX_SEARCH_MIN_TRACKED_PATHS", 0):
            session = knowledge_query.QuerySearchSession(self.repo)
            self.assertTrue(session.index_search_enabled)
            with mock.patch(
                "knowledge_query._tgrep_search",
                wraps=knowledge_query._tgrep_search,
            ) as tgrep_search:
                matches = knowledge_query._rg_fixed_matches(
                    self.repo,
                    ["staged marker"],
                    roots=(".",),
                    session=session,
                )
        self.assertEqual(
            [knowledge_query.Match("docs/visible.md", 1, "staged marker")],
            matches,
        )
        tgrep_search.assert_not_called()

    def test_dirty_and_untracked_overlay_is_searched_by_tgrep(self) -> None:
        if os.name != "nt":
            return
        binary = Path.cwd() / "tgrep.exe"
        shutil.copy2(binary, self.repo / "tgrep.exe")
        (self.repo / "docs" / "visible.md").write_text(
            "worktree replacement marker\nworktree replacement marker again\n",
            encoding="utf-8",
            newline="\n",
        )
        (self.repo / "untracked.md").write_text(
            "untracked replacement marker\nuntracked replacement marker again\n",
            encoding="utf-8",
            newline="\n",
        )
        exit_code, _stdout, stderr = self._invoke(
            ["tgrep-index", "--repo", str(self.repo), "--force"]
        )
        self.assertEqual(0, exit_code, stderr)
        knowledge_query._MATCH_CACHE.clear()
        with mock.patch(
            "knowledge_query._tgrep_search",
            wraps=knowledge_query._tgrep_search,
        ) as tgrep_search:
            indexed = knowledge_query._search_worktree_regex(
                self.repo, "replacement", roots=(".",)
            )
        self.assertGreaterEqual(tgrep_search.call_count, 2)
        self.assertEqual(
            {"docs/visible.md", "untracked.md"},
            {match.path for match in indexed},
        )

        knowledge_query._MATCH_CACHE.clear()
        with mock.patch(
            "knowledge_query._tgrep_search",
            wraps=knowledge_query._tgrep_search,
        ) as tgrep_search:
            indexed_fixed = knowledge_query._rg_fixed_matches(
                self.repo,
                ["replacement marker"],
                roots=(".",),
            )
        self.assertGreaterEqual(tgrep_search.call_count, 2)
        self.assertEqual(
            {
                "docs/visible.md": "worktree replacement marker",
                "untracked.md": "untracked replacement marker",
            },
            {match.path: match.line_text for match in indexed_fixed},
        )

        knowledge_query._MATCH_CACHE.clear()
        with mock.patch("knowledge_query._tgrep_state_is_valid", return_value=False):
            fallback_fixed = knowledge_query._rg_fixed_matches(
                self.repo,
                ["replacement marker"],
                roots=(".",),
            )
        self.assertEqual(indexed_fixed, fallback_fixed)
        (self.repo / "docs" / "visible.md").write_text(
            "stale replacement changed after index\n",
            encoding="utf-8",
            newline="\n",
        )
        self.assertFalse(knowledge_query._tgrep_state_is_valid(self.repo))


class TgrepLinuxFallbackTests(TgrepFixtureMixin, unittest.TestCase):
    def test_linux_never_executes_exe(self) -> None:
        if os.name == "nt":
            self.assertFalse(knowledge_query._tgrep_state_is_valid(self.repo, None))
            return
        with mock.patch("knowledge_query._run", wraps=knowledge_query._run) as runner:
            report = knowledge_query.query_repository(
                str(self.repo), stage="implementation", query="CJK"
            )
        self.assertEqual("knowledge-context/v1", report["schema"])
        self.assertFalse(
            any(call.args[0] and str(call.args[0][0]).lower().endswith("tgrep.exe") for call in runner.call_args_list)
        )


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("test_cases", nargs="*")
    parser.add_argument("--fixture-root", type=Path, default=Path(".knowledge-test-tmp"))
    args = parser.parse_args(argv)
    TgrepFixtureMixin.fixture_root = args.fixture_root.resolve()
    TgrepFixtureMixin.fixture_root.mkdir(parents=True, exist_ok=True)
    known = {
        name: globals()[name]
        for name in (
            "TgrepBehaviorTests",
            "TgrepCommandTests",
            "TgrepIndexStateTests",
            "TgrepWindowsParityTests",
            "TgrepLinuxFallbackTests",
        )
    }
    selected = args.test_cases or list(known)
    unknown = sorted(set(selected) - set(known))
    if unknown:
        parser.error(f"unknown test case: {', '.join(unknown)}")
    suite = unittest.TestSuite(
        unittest.defaultTestLoader.loadTestsFromTestCase(known[name]) for name in selected
    )
    try:
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    finally:
        _remove_fixture_root(TgrepFixtureMixin.fixture_root)
    return 0 if result.wasSuccessful() and not result.skipped else 1


if __name__ == "__main__":
    raise SystemExit(main())
