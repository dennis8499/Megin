#!/usr/bin/env python3
"""Focused tests for bootstrap, lint, promotion, and recovery."""

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
import uuid
from pathlib import Path
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from knowledge_cli import main as knowledge_main
from test_behavior import (
    _build_complete_lint_fixture,
    _build_contradiction_fixture,
    _build_governance_fixture,
    _build_promotion_fixture,
    _build_retrieval_fixture,
    _candidate_draft,
    _git,
    _remove_fixture,
    _tree_snapshot,
    _write,
    _exercise_promotion_security_and_recovery,
)


class GovernanceTests(unittest.TestCase):
    fixture_root: Path

    def tearDown(self) -> None:
        _remove_fixture(self.fixture_root)

    def test_bootstrap_classifier_seals_only_terminal_sources(self) -> None:
        repo = _build_governance_fixture(self.fixture_root)
        registry = self.fixture_root / "registry"
        before = _tree_snapshot(repo)
        stdout = io.StringIO()
        stderr = io.StringIO()
        try:
            import knowledge_governance
        except ImportError:
            registry_patch: contextlib.AbstractContextManager[object] = contextlib.nullcontext()
        else:
            registry_patch = mock.patch.object(
                knowledge_governance,
                "default_registry_root",
                return_value=registry,
            )
        with registry_patch, contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            exit_code = knowledge_main([
                "bootstrap", "--repo", str(repo),
                "--approval-actor", "bootstrap-owner",
                "--approval-evidence", "fixture:bootstrap-approved",
            ])
        self.assertEqual(0, exit_code)
        self.assertEqual("", stderr.getvalue())
        result = json.loads(stdout.getvalue())
        self.assertEqual(
            ["docs/work/work-alpha/requirements.md"],
            result["classification"]["terminal"],
        )
        self.assertEqual(
            ["docs/work/work-alpha/plan/plan.md"],
            result["classification"]["candidate"],
        )
        self.assertEqual(2, len(result["classification"]["conflict"]))
        self.assertEqual(
            ["docs/telemetry/status.json"],
            result["classification"]["unknown"],
        )
        candidate_path = (
            registry
            / "repos"
            / result["repo_id"]
            / Path(*result["candidate_ref"].removeprefix("knowledge:").split("/"))
        )
        self.assertTrue(candidate_path.is_file())
        candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
        self.assertEqual("knowledge-candidate/v1", candidate["schema"])
        self.assertEqual(
            [
                "docs/work/work-alpha/requirements.md",
                "docs/legacy/status.json",
                "docs/legacy/status.md",
            ],
            [source["path"] for source in candidate["source_snapshot"]],
        )
        self.assertEqual(before, _tree_snapshot(repo))

    def test_conflict_produces_separate_contested_quarantine(self) -> None:
        repo = _build_governance_fixture(self.fixture_root)
        registry = self.fixture_root / "registry"
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            mock.patch("knowledge_governance.default_registry_root", return_value=registry),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            exit_code = knowledge_main([
                "bootstrap", "--repo", str(repo),
                "--approval-actor", "bootstrap-owner",
                "--approval-evidence", "fixture:bootstrap-approved",
            ])
        self.assertEqual(0, exit_code)
        self.assertEqual("", stderr.getvalue())
        result = json.loads(stdout.getvalue())
        quarantine_ref = result.get("quarantine_candidate_ref")
        self.assertIsInstance(quarantine_ref, str)
        candidate_path = (
            registry
            / "repos"
            / result["repo_id"]
            / Path(*quarantine_ref.removeprefix("knowledge:").split("/"))
        )
        candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
        self.assertEqual("bootstrap", candidate["stage"])
        self.assertEqual(3, len(candidate["source_snapshot"]))
        sidecar_operation = next(
            item
            for item in candidate["operations"]
            if item["path"].endswith("page-legacy-status-conflict.json")
        )
        sidecar = json.loads(
            (
                candidate_path.parent
                / Path(*sidecar_operation["postimage_ref"].split("/"))
            ).read_text(encoding="utf-8")
        )
        self.assertEqual("contested", sidecar["lifecycle"])
        self.assertEqual(
            {"contested"},
            {claim["lifecycle"] for claim in sidecar["claims"]},
        )

    def test_bootstrap_candidate_applies_one_lint_clean_atomic_baseline(self) -> None:
        import knowledge_governance
        from knowledge_promotion import apply_candidate

        repo = _build_governance_fixture(self.fixture_root)
        registry = self.fixture_root / "registry"
        stdout = io.StringIO()
        with (
            mock.patch("knowledge_governance.default_registry_root", return_value=registry),
            contextlib.redirect_stdout(stdout),
        ):
            self.assertEqual(0, knowledge_main([
                "bootstrap", "--repo", str(repo),
                "--approval-actor", "bootstrap-owner",
                "--approval-evidence", "fixture:bootstrap-approved",
            ]))
            result = json.loads(stdout.getvalue())
            applied = apply_candidate(
                str(repo),
                candidate_ref=result["candidate_ref"],
                approval_actor="bootstrap-owner",
                approval_evidence="fixture:bootstrap-approved",
            )
            lint = knowledge_governance.lint_repository(str(repo))
        self.assertEqual("passed", applied["post_apply_lint"]["outcome"])
        self.assertEqual("passed", lint["outcome"])
        self.assertTrue((repo / "docs/knowledge/index.md").is_file())
        self.assertTrue((repo / "docs/knowledge/glossary.md").is_file())
        self.assertTrue((repo / "docs/knowledge/topics/bootstrap-trusted-artifacts.md").is_file())
        self.assertTrue((repo / "docs/knowledge/incidents/legacy-status-conflict.md").is_file())

    def test_stale_source_drift_produces_stable_repair_candidate(self) -> None:
        repo = _build_retrieval_fixture(self.fixture_root)
        registry = self.fixture_root / "registry"
        (repo / "src/stale-boundary.md").write_text(
            "Changed stale advice must not be silently trusted.\n",
            encoding="utf-8",
            newline="\n",
        )
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            mock.patch("knowledge_governance.default_registry_root", return_value=registry),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            exit_code = knowledge_main([
                "lint", "--repo", str(repo),
                "--approval-actor", "repair-owner",
                "--approval-evidence", "fixture:repair-approved",
            ])
        self.assertEqual(0, exit_code)
        self.assertEqual("", stderr.getvalue())
        report = json.loads(stdout.getvalue())
        self.assertEqual("failed", report["outcome"])
        self.assertIn(
            (
                "SOURCE_HASH_DRIFT",
                "docs/knowledge/meta/pages/page-stale-capability-token.json",
            ),
            {(item["code"], item["path"]) for item in report["diagnostics"]},
        )
        self.assertIsInstance(report.get("repair_candidate_ref"), str)
        self.assertNotIn(
            "claim-stale-capability-token",
            report["eligible_claim_ids"],
        )

    def test_log_only_drift_produces_an_applyable_repair_candidate(self) -> None:
        import knowledge_governance
        from knowledge_promotion import apply_candidate, seal_candidate_draft

        repo = self.fixture_root / f"log-only-repair-{uuid.uuid4().hex}"
        repo.mkdir(parents=True)
        _git(repo, "init", "-q")
        _write(repo / ".gitignore", "docs/knowledge/ignored/\n")
        _git(repo, "add", ".")
        registry = self.fixture_root / "registry"
        with mock.patch.object(
            knowledge_governance,
            "default_registry_root",
            return_value=registry,
        ):
            initial = seal_candidate_draft(
                str(repo),
                draft=_candidate_draft(
                    "docs/knowledge/bootstrap/catalog.md",
                    "# Initial catalog\n",
                ),
                approval_actor="initial-owner",
                approval_evidence="fixture:initial-approved",
            )
            apply_candidate(
                str(repo),
                candidate_ref=initial["candidate_ref"],
                approval_actor="initial-owner",
                approval_evidence="fixture:initial-approved",
            )
            _write(repo / "docs/knowledge/log.md", "# Knowledge Promotion Log\n\n- drift\n")
            repair = knowledge_governance.lint_repository(
                str(repo),
                repair_approval_actor="repair-owner",
                repair_approval_evidence="fixture:log-repair-approved",
            )
            self.assertEqual("failed", repair["outcome"])
            self.assertIsInstance(repair["repair_candidate_ref"], str)
            applied = apply_candidate(
                str(repo),
                candidate_ref=repair["repair_candidate_ref"],
                approval_actor="repair-owner",
                approval_evidence="fixture:log-repair-approved",
            )
            final_lint = knowledge_governance.lint_repository(str(repo))
        self.assertEqual("passed", applied["post_apply_lint"]["outcome"])
        self.assertEqual("passed", final_lint["outcome"])

    def test_symmetric_contradictions_are_decision_required(self) -> None:
        repo = _build_contradiction_fixture(self.fixture_root)
        registry = self.fixture_root / "registry"
        query_stdout = io.StringIO()
        query_stderr = io.StringIO()
        with contextlib.redirect_stdout(query_stdout), contextlib.redirect_stderr(query_stderr):
            query_exit = knowledge_main(
                [
                    "query",
                    "--repo",
                    str(repo),
                    "--stage",
                    "planning",
                    "--query",
                    "storage quorum",
                ]
            )
        self.assertEqual(0, query_exit)
        self.assertEqual("", query_stderr.getvalue())
        self.assertEqual([], json.loads(query_stdout.getvalue())["results"])
        lint_stdout = io.StringIO()
        with (
            mock.patch("knowledge_governance.default_registry_root", return_value=registry),
            contextlib.redirect_stdout(lint_stdout),
        ):
            lint_exit = knowledge_main([
                "lint", "--repo", str(repo),
                "--approval-actor", "repair-owner",
                "--approval-evidence", "fixture:repair-approved",
            ])
        self.assertEqual(0, lint_exit)
        report = json.loads(lint_stdout.getvalue())
        self.assertEqual("decision_required", report["outcome"])
        self.assertEqual([], report["eligible_claim_ids"])
        self.assertIn(
            "CONTRADICTION_DECISION_REQUIRED",
            {item["code"] for item in report["diagnostics"]},
        )

    def test_apply_rejects_preimage_drift_before_any_commit(self) -> None:
        repo = _build_governance_fixture(self.fixture_root)
        registry = self.fixture_root / "registry"
        bootstrap_stdout = io.StringIO()
        with (
            mock.patch("knowledge_governance.default_registry_root", return_value=registry),
            contextlib.redirect_stdout(bootstrap_stdout),
        ):
            self.assertEqual(0, knowledge_main([
                "bootstrap", "--repo", str(repo),
                "--approval-actor", "bootstrap-owner",
                "--approval-evidence", "fixture:bootstrap-approved",
            ]))
        candidate_ref = json.loads(bootstrap_stdout.getvalue())["candidate_ref"]
        unexpected = repo / "docs/knowledge/glossary.md"
        unexpected.parent.mkdir(parents=True, exist_ok=True)
        unexpected.write_text("# Concurrent writer\n", encoding="utf-8", newline="\n")
        before = _tree_snapshot(repo)
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            mock.patch("knowledge_governance.default_registry_root", return_value=registry),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            try:
                exit_code = knowledge_main(
                    [
                        "apply",
                        "--repo",
                        str(repo),
                        "--candidate-ref",
                        candidate_ref,
                        "--approval-actor",
                        "bootstrap-owner",
                        "--approval-evidence",
                        "fixture:bootstrap-approved",
                    ]
                )
            except SystemExit as exc:
                exit_code = int(exc.code)
        self.assertEqual(3, exit_code)
        self.assertEqual("", stdout.getvalue())
        error = json.loads(stderr.getvalue())
        self.assertEqual("PREIMAGE_DRIFT", error["code"])
        self.assertTrue(error["recoverable"])
        self.assertEqual(before, _tree_snapshot(repo))

    def test_apply_revalidates_preimages_after_operation_validation(self) -> None:
        import knowledge_governance
        import knowledge_promotion
        from knowledge_promotion import KnowledgeError, apply_candidate

        repo = _build_governance_fixture(self.fixture_root)
        registry = self.fixture_root / "registry"
        bootstrap_stdout = io.StringIO()
        with (
            mock.patch.object(
                knowledge_governance,
                "default_registry_root",
                return_value=registry,
            ),
            contextlib.redirect_stdout(bootstrap_stdout),
        ):
            self.assertEqual(0, knowledge_main([
                "bootstrap", "--repo", str(repo),
                "--approval-actor", "bootstrap-owner",
                "--approval-evidence", "fixture:bootstrap-approved",
            ]))
        candidate_ref = json.loads(bootstrap_stdout.getvalue())["candidate_ref"]
        concurrent = repo / "docs" / "knowledge" / "glossary.md"
        concurrent_bytes = b"# Concurrent and unapproved glossary\n"
        original_validator = knowledge_promotion._validated_operations
        drift_injected = False
        validation_calls = 0

        def validate_then_create(*args: object, **kwargs: object) -> list[dict[str, object]]:
            nonlocal drift_injected, validation_calls
            validation_calls += 1
            operations = original_validator(*args, **kwargs)
            if validation_calls == 2:
                concurrent.parent.mkdir(parents=True, exist_ok=True)
                concurrent.write_bytes(concurrent_bytes)
                drift_injected = True
            return operations

        with (
            mock.patch.object(
                knowledge_governance,
                "default_registry_root",
                return_value=registry,
            ),
            mock.patch(
                "knowledge_promotion._validated_operations",
                side_effect=validate_then_create,
            ),
            self.assertRaises(KnowledgeError) as raised,
        ):
            apply_candidate(
                str(repo),
                candidate_ref=candidate_ref,
                approval_actor="bootstrap-owner",
                approval_evidence="fixture:bootstrap-approved",
            )

        self.assertTrue(drift_injected)
        self.assertEqual(2, validation_calls)
        self.assertEqual("PREIMAGE_DRIFT", raised.exception.code)
        self.assertEqual(concurrent_bytes, concurrent.read_bytes())
        self.assertFalse((repo / "docs" / "knowledge" / "log.md").exists())
        self.assertFalse(list((repo / "docs" / "knowledge" / "meta" / "promotions").glob("*.json")))

    def test_apply_create_preserves_post_check_commit_boundary_competitor(self) -> None:
        import knowledge_governance
        import knowledge_promotion
        from knowledge_promotion import KnowledgeError, apply_candidate, seal_candidate_draft

        repo = _build_promotion_fixture(self.fixture_root)
        registry = self.fixture_root / "registry"
        target = repo / "docs" / "knowledge" / "bootstrap" / "catalog.md"
        later = b"# Later state before commit\n"
        with mock.patch.object(
            knowledge_governance,
            "default_registry_root",
            return_value=registry,
        ):
            sealed = seal_candidate_draft(
                str(repo),
                draft=_candidate_draft(
                    "docs/knowledge/bootstrap/catalog.md",
                    "# Candidate state\n",
                ),
                approval_actor="commit-reviewer",
                approval_evidence="fixture:commit-boundary",
            )
            original_assert = knowledge_promotion._assert_operation_preimage_current
            injected = False

            def assert_then_compete(
                repo_value: Path,
                candidate: dict[str, object],
                item: dict[str, object],
            ) -> None:
                nonlocal injected
                original_assert(repo_value, candidate, item)
                if Path(item["target"]) == target and not injected:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(later)
                    injected = True

            with (
                mock.patch(
                    "knowledge_promotion._assert_operation_preimage_current",
                    side_effect=assert_then_compete,
                ),
                self.assertRaises(KnowledgeError) as raised,
            ):
                apply_candidate(
                    str(repo),
                    candidate_ref=sealed["candidate_ref"],
                    approval_actor="commit-reviewer",
                    approval_evidence="fixture:commit-boundary",
                )

        self.assertTrue(injected)
        self.assertEqual("PREIMAGE_DRIFT", raised.exception.code)
        self.assertEqual(later, target.read_bytes())
        self.assertFalse(list(repo.glob("docs/knowledge/meta/promotions/*.json")))
        self.assertFalse((repo / "docs" / "knowledge" / "log.md").exists())

    def test_apply_update_preserves_post_check_commit_boundary_competitor(self) -> None:
        import knowledge_governance
        import knowledge_promotion
        from knowledge_promotion import KnowledgeError, apply_candidate, seal_candidate_draft

        repo = _build_promotion_fixture(self.fixture_root)
        registry = self.fixture_root / "registry"
        target = repo / "docs" / "knowledge" / "bootstrap" / "catalog.md"
        original = b"# Original approved state\n"
        competitor = b"# Concurrent state after the final check\n"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(original)
        _git(repo, "add", ".")
        draft = _candidate_draft(
            "docs/knowledge/bootstrap/catalog.md",
            "# Candidate state\n",
        )
        operation = draft["operations"][0]
        operation["kind"] = "update"
        with mock.patch.object(
            knowledge_governance,
            "default_registry_root",
            return_value=registry,
        ):
            sealed = seal_candidate_draft(
                str(repo),
                draft=draft,
                approval_actor="commit-reviewer",
                approval_evidence="fixture:update-commit-boundary",
            )
            original_assert = knowledge_promotion._assert_operation_preimage_current
            injected = False

            def assert_then_compete(
                repo_value: Path,
                candidate: dict[str, object],
                item: dict[str, object],
            ) -> None:
                nonlocal injected
                original_assert(repo_value, candidate, item)
                if Path(item["target"]) == target and not injected:
                    target.write_bytes(competitor)
                    injected = True

            with (
                mock.patch(
                    "knowledge_promotion._assert_operation_preimage_current",
                    side_effect=assert_then_compete,
                ),
                self.assertRaises(KnowledgeError) as raised,
            ):
                apply_candidate(
                    str(repo),
                    candidate_ref=sealed["candidate_ref"],
                    approval_actor="commit-reviewer",
                    approval_evidence="fixture:update-commit-boundary",
                )

        self.assertTrue(injected)
        self.assertEqual("PREIMAGE_DRIFT", raised.exception.code)
        self.assertEqual(competitor, target.read_bytes())
        self.assertFalse(list(repo.glob("docs/knowledge/meta/promotions/*.json")))
        self.assertFalse((repo / "docs" / "knowledge" / "log.md").exists())

    def test_update_retirement_read_failure_restores_preimage_before_rollback(self) -> None:
        import knowledge_governance
        from knowledge_promotion import KnowledgeError, apply_candidate, seal_candidate_draft

        repo = _build_promotion_fixture(self.fixture_root)
        registry = self.fixture_root / "registry"
        target = repo / "docs" / "knowledge" / "bootstrap" / "catalog.md"
        original = b"# Original approved state\n"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(original)
        _git(repo, "add", ".")
        draft = _candidate_draft(
            "docs/knowledge/bootstrap/catalog.md",
            "# Candidate state\n",
        )
        draft["operations"][0]["kind"] = "update"
        original_read_bytes = Path.read_bytes
        retirement_read_failed = False

        def fail_first_retirement_read(path: Path) -> bytes:
            nonlocal retirement_read_failed
            if (
                not retirement_read_failed
                and "commit-boundary" in path.parts
                and path.name.endswith(".preimage")
            ):
                retirement_read_failed = True
                raise OSError("injected retirement read fault")
            return original_read_bytes(path)

        with mock.patch.object(
            knowledge_governance,
            "default_registry_root",
            return_value=registry,
        ):
            sealed = seal_candidate_draft(
                str(repo),
                draft=draft,
                approval_actor="retirement-reviewer",
                approval_evidence="fixture:retirement-read-fault",
            )
            with (
                mock.patch.object(Path, "read_bytes", new=fail_first_retirement_read),
                self.assertRaises(KnowledgeError) as raised,
            ):
                apply_candidate(
                    str(repo),
                    candidate_ref=sealed["candidate_ref"],
                    approval_actor="retirement-reviewer",
                    approval_evidence="fixture:retirement-read-fault",
                )

        self.assertTrue(retirement_read_failed)
        self.assertEqual("PROMOTION_FAILED", raised.exception.code)
        self.assertTrue(raised.exception.recoverable)
        self.assertTrue(target.is_file(), "rollback left the approved target missing")
        self.assertEqual(original, target.read_bytes())
        self.assertFalse(list(repo.glob("docs/knowledge/meta/promotions/*.json")))
        journals = list(registry.glob("repos/*/journals/*/journal.json"))
        self.assertEqual(1, len(journals))
        self.assertEqual(
            "rolled_back",
            json.loads(journals[0].read_text(encoding="utf-8"))["status"],
        )
        self.assertFalse(list(journals[0].parent.glob("commit-boundary/*.preimage")))

    def test_update_retirement_restore_collision_requires_recovery(self) -> None:
        import knowledge_governance
        from knowledge_promotion import KnowledgeError, apply_candidate, seal_candidate_draft

        repo = _build_promotion_fixture(self.fixture_root)
        registry = self.fixture_root / "registry"
        target = repo / "docs" / "knowledge" / "bootstrap" / "catalog.md"
        original = b"# Original approved state\n"
        competitor = b"# Independent state during retirement fault\n"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(original)
        _git(repo, "add", ".")
        draft = _candidate_draft(
            "docs/knowledge/bootstrap/catalog.md",
            "# Candidate state\n",
        )
        draft["operations"][0]["kind"] = "update"
        original_read_bytes = Path.read_bytes
        competitor_injected = False

        def compete_then_fail_retirement_read(path: Path) -> bytes:
            nonlocal competitor_injected
            if (
                not competitor_injected
                and "commit-boundary" in path.parts
                and path.name.endswith(".preimage")
            ):
                target.write_bytes(competitor)
                competitor_injected = True
                raise OSError("injected retirement read fault with competitor")
            return original_read_bytes(path)

        with mock.patch.object(
            knowledge_governance,
            "default_registry_root",
            return_value=registry,
        ):
            sealed = seal_candidate_draft(
                str(repo),
                draft=draft,
                approval_actor="retirement-reviewer",
                approval_evidence="fixture:retirement-restore-collision",
            )
            with (
                mock.patch.object(
                    Path,
                    "read_bytes",
                    new=compete_then_fail_retirement_read,
                ),
                self.assertRaises(KnowledgeError) as raised,
            ):
                apply_candidate(
                    str(repo),
                    candidate_ref=sealed["candidate_ref"],
                    approval_actor="retirement-reviewer",
                    approval_evidence="fixture:retirement-restore-collision",
                )

            self.assertTrue(competitor_injected)
            self.assertEqual("RECOVERY_REQUIRED", raised.exception.code)
            self.assertTrue(raised.exception.recoverable)
            self.assertEqual(competitor, target.read_bytes())
            journals = list(registry.glob("repos/*/journals/*/journal.json"))
            self.assertEqual(1, len(journals))
            self.assertEqual(
                "in_progress",
                json.loads(journals[0].read_text(encoding="utf-8"))["status"],
            )
            retired = list(journals[0].parent.glob("commit-boundary/*.preimage"))
            self.assertEqual(1, len(retired))
            self.assertEqual(original, retired[0].read_bytes())
            with self.assertRaises(KnowledgeError) as retry:
                apply_candidate(
                    str(repo),
                    candidate_ref=sealed["candidate_ref"],
                    approval_actor="retirement-reviewer",
                    approval_evidence="fixture:retirement-restore-collision",
                )
            self.assertEqual("RECOVERY_REQUIRED", retry.exception.code)

    def test_rollback_preserves_state_written_after_own_replace(self) -> None:
        import knowledge_governance
        import knowledge_promotion
        from knowledge_promotion import KnowledgeError, apply_candidate, seal_candidate_draft

        repo = _build_promotion_fixture(self.fixture_root)
        registry = self.fixture_root / "registry"
        target = repo / "docs" / "knowledge" / "bootstrap" / "catalog.md"
        later = b"# Later state during rollback\n"
        with mock.patch.object(
            knowledge_governance,
            "default_registry_root",
            return_value=registry,
        ):
            sealed = seal_candidate_draft(
                str(repo),
                draft=_candidate_draft(
                    "docs/knowledge/bootstrap/catalog.md",
                    "# Candidate state\n",
                ),
                approval_actor="rollback-reviewer",
                approval_evidence="fixture:rollback-boundary",
            )
            original_replace = os.replace
            original_publish = getattr(
                knowledge_governance,
                "_rename_path_create_only",
                None,
            )
            injected = False

            def inject_after_target_replace(source: object, destination: object) -> None:
                nonlocal injected
                original_replace(source, destination)
                destination_path = Path(destination)
                if destination_path == target and not injected:
                    destination_path.write_bytes(later)
                    injected = True

            def inject_after_target_publish(
                source: Path,
                destination: Path,
                **kwargs: object,
            ) -> None:
                nonlocal injected
                if original_publish is None:
                    raise AssertionError("atomic create-only publisher is missing")
                original_publish(source, destination, **kwargs)
                destination_path = Path(destination)
                if destination_path == target and not injected:
                    destination_path.write_bytes(later)
                    injected = True

            with (
                mock.patch(
                    "knowledge_promotion.os.replace",
                    side_effect=inject_after_target_replace,
                ),
                mock.patch.object(
                    knowledge_governance,
                    "_rename_path_create_only",
                    side_effect=inject_after_target_publish,
                    create=True,
                ),
                self.assertRaises(KnowledgeError) as raised,
            ):
                apply_candidate(
                    str(repo),
                    candidate_ref=sealed["candidate_ref"],
                    approval_actor="rollback-reviewer",
                    approval_evidence="fixture:rollback-boundary",
                    fault_at="after-replace-0",
                )

        self.assertTrue(injected)
        self.assertEqual("ROLLBACK_CONFLICT", raised.exception.code)
        self.assertEqual(later, target.read_bytes())
        self.assertFalse(list(repo.glob("docs/knowledge/meta/promotions/*.json")))

    def test_candidate_publish_preserves_commit_boundary_competitor(self) -> None:
        import knowledge_governance
        from knowledge_promotion import KnowledgeError, seal_candidate_draft

        repo = _build_promotion_fixture(self.fixture_root)
        registry = self.fixture_root / "registry"
        original_assert_safe = knowledge_governance._assert_registry_path_safe
        original_replace = os.replace
        final_checks = 0
        competitor_path: Path | None = None
        competitor_inode: int | None = None

        def inject_empty_competitor(root: Path, path: Path) -> None:
            nonlocal final_checks, competitor_path, competitor_inode
            original_assert_safe(root, path)
            candidate_path = Path(path)
            if (
                candidate_path.parent.name == "candidates"
                and not candidate_path.name.startswith(".")
            ):
                final_checks += 1
                if final_checks == 2:
                    candidate_path.mkdir()
                    competitor_path = candidate_path
                    competitor_inode = candidate_path.stat().st_ino

        def emulate_posix_directory_replace(source: object, destination: object) -> None:
            source_path = Path(source)
            destination_path = Path(destination)
            if (
                source_path.is_dir()
                and competitor_path is not None
                and destination_path == competitor_path
                and destination_path.is_dir()
            ):
                destination_path.rmdir()
            original_replace(source, destination)

        with (
            mock.patch.object(
                knowledge_governance,
                "default_registry_root",
                return_value=registry,
            ),
            mock.patch.object(
                knowledge_governance,
                "_assert_registry_path_safe",
                side_effect=inject_empty_competitor,
            ),
            mock.patch.object(
                knowledge_governance.os,
                "replace",
                side_effect=emulate_posix_directory_replace,
            ),
            self.assertRaises(KnowledgeError) as raised,
        ):
            seal_candidate_draft(
                str(repo),
                draft=_candidate_draft(
                    "docs/knowledge/bootstrap/catalog.md",
                    "# Candidate commit-boundary state\n",
                ),
                approval_actor="candidate-reviewer",
                approval_evidence="fixture:candidate-commit-boundary",
            )

        self.assertEqual("CANDIDATE_EXISTS", raised.exception.code)
        self.assertIsNotNone(competitor_path)
        self.assertIsNotNone(competitor_inode)
        assert competitor_path is not None
        self.assertTrue(competitor_path.is_dir())
        self.assertEqual(competitor_inode, competitor_path.stat().st_ino)
        self.assertFalse((competitor_path / "candidate.json").exists())

    def test_candidate_seal_and_lint_enforce_closed_page_contract(self) -> None:
        import knowledge_governance
        from knowledge_promotion import KnowledgeError, seal_candidate_draft

        variants = ("page", "claim", "source")
        for variant in variants:
            with self.subTest(variant=variant):
                repo = _build_retrieval_fixture(self.fixture_root)
                registry = self.fixture_root / "registry"
                sidecars = sorted(
                    (repo / "docs" / "knowledge" / "meta" / "pages").glob("*.json")
                )
                pages = [json.loads(path.read_text(encoding="utf-8")) for path in sidecars]
                _write(
                    repo / "docs" / "knowledge" / "index.md",
                    knowledge_governance.render_index(pages).decode("utf-8"),
                )
                _git(repo, "add", ".")
                self.assertEqual("passed", knowledge_governance.lint_repository(str(repo))["outcome"])
                page_path = sidecars[0]
                page = json.loads(page_path.read_text(encoding="utf-8"))
                if variant == "page":
                    page["unexpected_member"] = "closed"
                elif variant == "claim":
                    page["claims"][0]["unexpected_member"] = "closed"
                else:
                    page["claims"][0]["source_refs"][0]["unexpected_member"] = "closed"
                _write(
                    page_path,
                    json.dumps(page, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                )
                lint = knowledge_governance.lint_repository(str(repo))
                self.assertEqual("failed", lint["outcome"])
                self.assertIn(
                    "PAGE_CONTRACT_INVALID",
                    {item["code"] for item in lint["diagnostics"]},
                )

                content = "# Closed Candidate\n"
                source = "Candidate source remains auditable.\n"
                source_sha = _write(repo / "evidence" / "closed-candidate.md", source)
                _git(repo, "add", ".")
                candidate_page = {
                    "schema": "knowledge-page/v1",
                    "page_id": "page-closed-candidate",
                    "content_path": "docs/knowledge/topics/closed-candidate.md",
                    "content_sha256": knowledge_governance.sha256_bytes(content.encode("utf-8")),
                    "title": "Closed Candidate",
                    "aliases": [],
                    "tags": ["implementation"],
                    "lifecycle": "current",
                    "claims": [
                        {
                            "claim_id": "claim-closed-candidate",
                            "evidence_class": "observed",
                            "lifecycle": "current",
                            "content_anchor": "closed-candidate",
                            "source_refs": [
                                {
                                    "path": "evidence/closed-candidate.md",
                                    "sha256": source_sha,
                                    "locator": {"start_line": 1, "end_line": 1},
                                    "excerpt_sha256": knowledge_governance.sha256_bytes(
                                        source.rstrip("\n").encode("utf-8")
                                    ),
                                }
                            ],
                            "supersedes": [],
                            "contradicts": [],
                        }
                    ],
                    "backlinks": [],
                    "unexpected_member": "closed",
                }
                with (
                    mock.patch.object(
                        knowledge_governance,
                        "default_registry_root",
                        return_value=registry,
                    ),
                    self.assertRaises(KnowledgeError) as raised,
                ):
                    seal_candidate_draft(
                        str(repo),
                        draft={
                            "schema": "knowledge-candidate-draft/v1",
                            "stage": "implementation",
                            "work_id": "work-closed-candidate",
                            "decision": "change",
                            "source_snapshot": [],
                            "operations": [
                                {
                                    "kind": "create",
                                    "path": "docs/knowledge/topics/closed-candidate.md",
                                    "postimage": content,
                                },
                                {
                                    "kind": "create",
                                    "path": "docs/knowledge/meta/pages/page-closed-candidate.json",
                                    "postimage": json.dumps(
                                        candidate_page,
                                        ensure_ascii=False,
                                        sort_keys=True,
                                        indent=2,
                                    ) + "\n",
                                },
                            ],
                        },
                        approval_actor="closed-reviewer",
                        approval_evidence="fixture:closed-candidate",
                    )
                self.assertEqual("PAGE_CONTRACT_INVALID", raised.exception.code)

    def test_complete_lint_reports_every_rule_family_read_only(self) -> None:
        repo = _build_complete_lint_fixture(self.fixture_root)
        registry = self.fixture_root / "registry"
        before = _tree_snapshot(repo)
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            mock.patch("knowledge_governance.default_registry_root", return_value=registry),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            exit_code = knowledge_main([
                "lint", "--repo", str(repo),
                "--approval-actor", "repair-owner",
                "--approval-evidence", "fixture:repair-approved",
            ])
        self.assertEqual(0, exit_code, stderr.getvalue())
        self.assertEqual("", stderr.getvalue())
        report = json.loads(stdout.getvalue())
        codes = {item["code"] for item in report["diagnostics"]}
        self.assertTrue(
            {
                "SOURCE_REF_MISSING",
                "SOURCE_HASH_DRIFT",
                "BACKLINK_MISSING",
                "ORPHAN_PAGE",
                "PAGE_ID_DUPLICATE",
                "INDEX_DRIFT",
                "PROMOTION_LOG_DRIFT",
                "LIFECYCLE_INVALID",
                "CONTRADICTION_ASYMMETRIC",
            }.issubset(codes),
            sorted(codes),
        )
        self.assertTrue(
            {
                "claim-no-provenance",
                "claim-stale-source",
                "claim-illegal-state",
            }.isdisjoint(report["eligible_claim_ids"])
        )
        self.assertIsInstance(report["repair_candidate_ref"], str)
        self.assertEqual(before, _tree_snapshot(repo))

    def test_security_fault_matrix_rolls_back_and_requires_recovery(self) -> None:
        report = _exercise_promotion_security_and_recovery(self.fixture_root)
        self.assertEqual(
            [
                "SECRET_DETECTED",
                "TARGET_IGNORED",
                "TARGET_NOT_ALLOWED",
                "TARGET_REDIRECTED",
                "UNSAFE_PATH",
            ],
            report["safety_codes"],
        )
        self.assertEqual(4, len(report["faults"]))
        self.assertGreater(report["git_commands"], 0)
        self.assertEqual("recovered", report["recovery"])

    def test_real_process_death_recovery_removes_stale_lock_and_allows_retry(self) -> None:
        import knowledge_governance
        from knowledge_promotion import apply_candidate, recover_repository, seal_candidate_draft

        repo = self.fixture_root / f"real-crash-{uuid.uuid4().hex}"
        repo.mkdir(parents=True)
        _git(repo, "init", "-q")
        _write(repo / ".gitignore", "docs/knowledge/ignored/\n")
        _write(repo / "evidence/terminal.md", "Status: Complete\n")
        _git(repo, "add", ".")
        sealed = seal_candidate_draft(
            str(repo),
            draft=_candidate_draft(
                "docs/knowledge/bootstrap/catalog.md",
                "# Real process crash\n",
            ),
            approval_actor="crash-reviewer",
            approval_evidence="fixture:real-process-crash",
        )
        scripts = Path(__file__).resolve().parent
        child = (
            "import os,sys\n"
            f"sys.path.insert(0, {str(scripts)!r})\n"
            "from knowledge_promotion import apply_candidate,SimulatedCrash\n"
            "try:\n"
            f" apply_candidate({str(repo)!r}, candidate_ref={sealed['candidate_ref']!r}, "
            "approval_actor='crash-reviewer', approval_evidence='fixture:real-process-crash', "
            "fault_at='crash-after-replace-0')\n"
            "except SimulatedCrash:\n"
            " os._exit(91)\n"
        )
        completed = subprocess.run(
            [sys.executable, "-X", "utf8", "-B", "-c", child],
            cwd=repo,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            shell=False,
        )
        self.assertEqual(91, completed.returncode, completed.stderr.decode("utf-8", errors="replace"))
        repo_id = knowledge_governance.repository_id(repo)
        registry_repo = knowledge_governance.default_registry_root() / "repos" / repo_id
        lock_path = registry_repo / "promotion.lock"
        self.assertTrue(lock_path.is_file())
        lock_pid = int(lock_path.read_text(encoding="ascii").strip().removeprefix("pid="))
        self.assertNotEqual(os.getpid(), lock_pid)
        try:
            recovered = recover_repository(str(repo))
            self.assertEqual("recovered", recovered["outcome"])
            self.assertFalse(lock_path.exists())
            self.assertFalse((repo / "docs/knowledge/bootstrap/catalog.md").exists())
            applied = apply_candidate(
                str(repo),
                candidate_ref=sealed["candidate_ref"],
                approval_actor="crash-reviewer",
                approval_evidence="fixture:real-process-crash",
            )
            self.assertEqual("passed", applied["post_apply_lint"]["outcome"])
        finally:
            expected_parent = knowledge_governance.default_registry_root() / "repos"
            if registry_repo.parent == expected_parent and registry_repo.is_dir():
                shutil.rmtree(registry_repo)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture-root", type=Path, default=Path(".knowledge-test-tmp"))
    args = parser.parse_args(argv)
    GovernanceTests.fixture_root = args.fixture_root.resolve()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(GovernanceTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    _remove_fixture(GovernanceTests.fixture_root)
    return 0 if result.wasSuccessful() and not result.skipped else 1


if __name__ == "__main__":
    raise SystemExit(main())
