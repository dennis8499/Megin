#!/usr/bin/env python3
"""Focused contract tests for SDLC stage integration."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import shutil
import subprocess
import unittest
from unittest import mock
from pathlib import Path

import compare_portability_reports
import validate_contracts as knowledge_contracts
from knowledge_governance import canonical_sha256

from test_behavior import (
    _build_governance_fixture,
    _build_promotion_fixture,
    _build_retrieval_fixture,
    _exercise_bug_knowledge_mapping,
    _exercise_human_gate_compatibility,
    _exercise_implementation_knowledge_gate,
    _exercise_planning_co_promotion,
    _exercise_requirements_co_promotion,
    _git,
    _persist_preliminary_review_fixture,
    _remove_fixture,
    _sha256,
    _tree_snapshot,
    _write,
)


OWNERS = {
    "requirements": ".agents/skills/requirements-discovery/SKILL.md",
    "planning": ".agents/skills/technical-planning/SKILL.md",
    "implementation": ".agents/skills/implementation-execution/SKILL.md",
    "bug": ".agents/skills/bug-diagnosis/SKILL.md",
}


def stage_hook_errors(text: str, stage: str) -> list[str]:
    required = {
        "query-command": "project-knowledge/scripts/knowledge_cli.py query",
        "stage": f"--stage {stage}",
        "source-binding": "source_refs",
    }
    folded = text.casefold()
    errors = [label for label, fragment in required.items() if fragment not in text]
    if "read-only" not in folded and "唯讀" not in text:
        errors.append("read-only")
    return errors


class StageHookContractTests(unittest.TestCase):
    workspace: Path
    fixture_root: Path

    def tearDown(self) -> None:
        _remove_fixture(self.fixture_root)

    def test_all_owner_skills_have_stage_specific_preflight(self) -> None:
        for stage, relative in OWNERS.items():
            with self.subTest(stage=stage):
                text = (self.workspace / relative).read_text(encoding="utf-8")
                self.assertEqual([], stage_hook_errors(text, stage))

    def test_each_required_fragment_is_mutation_sensitive(self) -> None:
        template = (
            "project-knowledge/scripts/knowledge_cli.py query --repo . "
            "--stage {stage} --query intent\n"
            "This is read-only and every source_refs entry is re-read.\n"
        )
        for stage in OWNERS:
            valid = template.format(stage=stage)
            self.assertEqual([], stage_hook_errors(valid, stage))
            mutations = [
                valid.replace("project-knowledge/scripts/knowledge_cli.py query", "missing-command"),
                valid.replace(f"--stage {stage}", "--stage missing"),
                valid.replace("read-only", "mutable"),
                valid.replace("source_refs", "citations"),
            ]
            for mutated in mutations:
                    self.assertTrue(stage_hook_errors(mutated, stage), (stage, mutated))

    def test_build_full_inventory_reports_every_git_eligible_source_contract(self) -> None:
        errors, python_count, schema_count = knowledge_contracts.syntax_errors()
        self.assertEqual([], errors)
        completed = subprocess.run(
            [
                "git",
                "-c",
                "core.quotepath=false",
                "ls-files",
                "--cached",
                "--others",
                "--exclude-standard",
                "-z",
            ],
            cwd=self.workspace,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            shell=False,
        )
        self.assertEqual(0, completed.returncode, completed.stderr.decode(errors="replace"))
        relative_paths = [
            raw.decode("utf-8").replace("\\", "/")
            for raw in completed.stdout.split(b"\0")
            if raw
        ]
        expected_python = sum(
            1
            for relative in relative_paths
            if relative.casefold().endswith(".py")
            and (self.workspace / Path(*relative.split("/"))).is_file()
        )
        expected_schemas = sum(
            1
            for relative in relative_paths
            if relative.endswith(".schema.json")
            and (self.workspace / Path(*relative.split("/"))).is_file()
        )
        self.assertEqual(expected_python, python_count)
        self.assertEqual(expected_schemas, schema_count)
        self.assertGreater(python_count, 0)
        self.assertGreater(schema_count, 0)

    def test_requirements_and_knowledge_are_one_approved_promotion(self) -> None:
        report = _exercise_requirements_co_promotion(self.fixture_root)
        self.assertEqual("planning", report["next_phase"])
        self.assertEqual("passed", report["lint"])
        self.assertEqual(6, len(report["affected_paths"]))

    def test_bug_assessment_is_unmaterialized_until_the_shared_requirements_apply(self) -> None:
        report = _exercise_requirements_co_promotion(
            self.fixture_root,
            include_bug_assessment=True,
        )
        self.assertTrue(report["preapproval_absent"])
        self.assertEqual("PREIMAGE_DRIFT", report["collision_code"])
        self.assertTrue(report["collision_zero_mutation"])
        self.assertTrue(report["assessment_materialized"])
        self.assertEqual(2, len(report["review_targets"]))
        self.assertEqual(3, len(report["formal_paths"]))
        self.assertEqual("likely", report["bug_assessment_summary"]["verdict"])
        self.assertEqual(
            "uncertain-diagnosis",
            report["bug_assessment_summary"]["classification_risk"],
        )
        self.assertNotIn(
            "The public command returns an incorrect result.",
            report["summary_rendered"],
        )

    def test_planning_claims_stay_planned_through_the_shared_gate(self) -> None:
        report = _exercise_planning_co_promotion(self.fixture_root)
        self.assertEqual("implementation", report["next_phase"])
        self.assertEqual(4, len(report["formal_paths"]))
        self.assertTrue(
            any(path.endswith("/occurrence_map.yaml") for path in report["formal_paths"])
        )
        self.assertTrue(report["formal_paths"][-1].endswith("/plan.md"))
        self.assertEqual(["planned"], report["evidence_classes"])
        self.assertEqual(2, report["promotion_count"])
        self.assertEqual("passed", report["lint"])
        self.assertEqual("bulk_edit", report["occurrence_summary"]["change_mode"])
        self.assertTrue(report["occurrence_summary"]["manual_review_required"])
        self.assertEqual(
            2,
            report["occurrence_summary"]["manual_review_item_count"],
        )
        self.assertEqual(
            "manual-review-required",
            report["occurrence_summary"]["classification_risk"],
        )

    def test_requirements_no_change_has_a_sealed_receipt_and_no_claim_page(self) -> None:
        import knowledge_governance
        from knowledge_promotion import apply_candidate, seal_candidate_draft
        from knowledge_workflow import build_stage_candidate_draft
        from unittest import mock

        _remove_fixture(self.fixture_root)
        repo = self.fixture_root / "requirements-no-change"
        repo.mkdir(parents=True)
        _git(repo, "init", "-q")
        _write(repo / "README.md", "# Fixture\n")
        _git(repo, "add", ".")
        registry = self.fixture_root / "registry"
        with mock.patch("knowledge_governance.default_registry_root", return_value=registry):
            draft = build_stage_candidate_draft(
                str(repo),
                stage="requirements",
                work_id="work-no-change",
                artifact_path="docs/work/work-no-change/requirements.md",
                artifact_text="# Requirements\n\nStatus: Ready\n",
                title="",
                claim_text="",
                knowledge_decision="no-change",
            )
            sealed = seal_candidate_draft(
                str(repo),
                draft=draft,
                approval_actor="requirements-owner",
                approval_evidence="conversation:no-change-approved",
            )
            self.assertEqual("no-change", sealed["decision"])
            self.assertEqual(3, len(sealed["affected_paths"]))
            applied = apply_candidate(
                str(repo),
                candidate_ref=sealed["candidate_ref"],
                review_sha256=sealed["review_sha256"],
                approval_actor="requirements-owner",
                approval_evidence="conversation:no-change-approved",
            )
            lint = knowledge_governance.lint_repository(str(repo))
        self.assertEqual("no-change", applied["promotion"]["decision"])
        self.assertEqual("passed", lint["outcome"])
        self.assertFalse((repo / "docs/knowledge/meta/pages").exists())

    def test_reviewed_implementation_cannot_skip_the_knowledge_gate(self) -> None:
        report = _exercise_implementation_knowledge_gate(self.fixture_root)
        self.assertEqual("knowledge", report["awaiting_phase"])
        self.assertEqual("awaiting_user", report["awaiting_status"])
        self.assertEqual("complete", report["completed_phase"])
        self.assertTrue(report["product_snapshot_stable"])
        self.assertTrue(report["external_knowledge_rejected"])
        self.assertEqual("passed", report["lint"])
        self.assertEqual("standard", report["outcome_summary"]["work_kind"])
        self.assertEqual("complete", report["outcome_summary"]["result"])
        self.assertEqual(
            "Review the implementation Outcome and proposed observed knowledge "
            "changes before approval.",
            report["gate_purpose"],
        )
        self.assertEqual(
            "Publish an implementation Outcome-derived knowledge revision.",
            report["gate_change"]["description"],
        )

    def test_complete_outcome_rejects_failed_or_not_run_verification(self) -> None:
        from knowledge_outcome import write_implementation_outcome
        from knowledge_query import KnowledgeError

        _remove_fixture(self.fixture_root)
        repo = self.fixture_root / "outcome-certainty"
        repo.mkdir(parents=True)
        _git(repo, "init", "-q")
        _write(repo / "src/change.md", "reviewed change\n")
        _git(repo, "add", ".")
        for outcome in ("failed", "not_run"):
            with self.subTest(outcome=outcome):
                with self.assertRaises(KnowledgeError) as raised:
                    write_implementation_outcome(
                        str(repo),
                        work_id="work-outcome-certainty",
                        implementation_run_id="d" * 64,
                        work_kind="standard",
                        result="complete",
                        summary="The implementation is complete.",
                        changes=[{"path": "src/change.md", "summary": "Changed behavior."}],
                        verification=[{
                            "command_id": "CMD-FULL-001",
                            "outcome": outcome,
                            "evidence_refs": [f"commands/{outcome}.json"],
                        }],
                        review={
                            "verdict": "APPROVED",
                            "evidence_refs": ["review:fresh-review:outcome-certainty-r1"],
                            "report_ref": "reviews/outcome-certainty-r1/report.json",
                            "report_sha256": "e" * 64,
                        },
                        known_deviations=[],
                        knowledge_decision="change",
                        bug_verification_ref=None,
                        created_at="2026-08-31T12:00:00+08:00",
                    )
                self.assertEqual("OUTCOME_CERTAINTY_INVALID", raised.exception.code)
        self.assertFalse((repo / "docs/work/work-outcome-certainty/implementation").exists())

    def test_outcome_requires_a_persisted_approved_preliminary_report(self) -> None:
        from knowledge_outcome import write_implementation_outcome
        from knowledge_query import KnowledgeError, sha256_bytes

        _remove_fixture(self.fixture_root)
        repo = self.fixture_root / "outcome-preliminary-review"
        repo.mkdir(parents=True)
        _git(repo, "init", "-q")
        _write(repo / "src/change.md", "reviewed change\n")
        _git(repo, "add", ".")
        host_temp = self.fixture_root / "host-temp"
        run_id = "e" * 64
        with mock.patch("knowledge_outcome.tempfile.gettempdir", return_value=str(host_temp)):
            review, output_refs = _persist_preliminary_review_fixture(
                implementation_run_id=run_id,
                logical_ref="review:fresh-review:outcome-physical-r1",
                command_ids=["CMD-FULL-001"],
            )
            report_path = (
                host_temp
                / "implementation-execution"
                / "runs"
                / run_id
                / Path(*str(review["report_ref"]).split("/"))
            )
            original_report = report_path.read_bytes()

            def attempt(bound_review: dict[str, object]) -> None:
                write_implementation_outcome(
                    str(repo),
                    work_id="work-outcome-physical",
                    implementation_run_id=run_id,
                    work_kind="standard",
                    result="complete",
                    summary="The implementation is complete.",
                    changes=[{"path": "src/change.md", "summary": "Changed behavior."}],
                    verification=[
                        {
                            "command_id": "CMD-FULL-001",
                            "outcome": "passed",
                            "evidence_refs": [output_refs["CMD-FULL-001"]],
                        }
                    ],
                    review=bound_review,
                    known_deviations=[],
                    knowledge_decision="change",
                    bug_verification_ref=None,
                    created_at="2026-08-31T12:00:00+08:00",
                )

            report_path.unlink()
            with self.assertRaises(KnowledgeError) as missing:
                attempt(review)
            self.assertEqual("PRELIMINARY_REVIEW_MISSING", missing.exception.code)

            report_path.write_bytes(original_report + b" ")
            with self.assertRaises(KnowledgeError) as drifted:
                attempt(review)
            self.assertEqual("PRELIMINARY_REVIEW_DRIFT", drifted.exception.code)

            report = json.loads(original_report.decode("utf-8"))
            report["verdict"] = "BLOCKED"
            unapproved_raw = (
                json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
            ).encode("utf-8")
            report_path.write_bytes(unapproved_raw)
            unapproved_review = dict(review)
            unapproved_review["report_sha256"] = sha256_bytes(unapproved_raw)
            with self.assertRaises(KnowledgeError) as unapproved:
                attempt(unapproved_review)
            self.assertEqual("PRELIMINARY_REVIEW_INVALID", unapproved.exception.code)

        self.assertFalse((repo / "docs/work/work-outcome-physical/implementation").exists())

    def test_preliminary_review_persistence_rejects_ready_misbinding(self) -> None:
        import knowledge_outcome
        from knowledge_query import KnowledgeError

        _remove_fixture(self.fixture_root)
        host_temp = self.fixture_root / "host-temp"
        run_id = "9" * 64
        with mock.patch("knowledge_outcome.tempfile.gettempdir", return_value=str(host_temp)):
            review, _ = _persist_preliminary_review_fixture(
                implementation_run_id=run_id,
                logical_ref="review:fresh-review:ready-bound-valid-r1",
                command_ids=["CMD-FULL-001"],
            )
            run_root = host_temp / "implementation-execution" / "runs" / run_id
            report_path = run_root / Path(*str(review["report_ref"]).split("/"))
            report = json.loads(report_path.read_text(encoding="utf-8"))
            report["logical_ref"] = "review:fresh-review:ready-bound-invalid-r1"
            report["requirement_coverage"][0]["obligation_ref"] = "REQ-404"
            output_mapping = {
                old: old.replace(
                    "reviews/ready-bound-valid-r1/",
                    "reviews/ready-bound-invalid-r1/",
                )
                for old in report["raw_output_refs"]
            }
            report["raw_output_refs"] = [
                output_mapping[old] for old in report["raw_output_refs"]
            ]
            for command in report["command_outcomes"]:
                command["output_ref"] = output_mapping[command["output_ref"]]
            raw_outputs = {
                relative: "command passed\n"
                for relative in report["raw_output_refs"]
            }
            with self.assertRaises(KnowledgeError) as raised:
                knowledge_outcome.persist_preliminary_review_report(
                    implementation_run_id=run_id,
                    report_ref="reviews/ready-bound-invalid-r1/report.json",
                    report=report,
                    raw_outputs=raw_outputs,
                )
            self.assertEqual("PRELIMINARY_REVIEW_INVALID", raised.exception.code)

    def test_outcome_rejects_persisted_review_that_misbinds_ready(self) -> None:
        from knowledge_outcome import write_implementation_outcome
        from knowledge_query import KnowledgeError, sha256_bytes

        _remove_fixture(self.fixture_root)
        repo = self.fixture_root / "outcome-ready-binding"
        repo.mkdir(parents=True)
        _git(repo, "init", "-q")
        _write(repo / "src/change.md", "ready-bound change\n")
        _git(repo, "add", ".")
        host_temp = self.fixture_root / "host-temp"
        run_id = "8" * 64
        with mock.patch("knowledge_outcome.tempfile.gettempdir", return_value=str(host_temp)):
            review, output_refs = _persist_preliminary_review_fixture(
                implementation_run_id=run_id,
                logical_ref="review:fresh-review:outcome-ready-bound-r1",
                command_ids=["CMD-FULL-001"],
            )
            report_path = (
                host_temp
                / "implementation-execution"
                / "runs"
                / run_id
                / Path(*str(review["report_ref"]).split("/"))
            )
            report = json.loads(report_path.read_text(encoding="utf-8"))
            report["requirement_coverage"][0]["obligation_ref"] = "REQ-404"
            invalid_raw = (
                json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
            ).encode("utf-8")
            report_path.write_bytes(invalid_raw)
            invalid_review = dict(review)
            invalid_review["report_sha256"] = sha256_bytes(invalid_raw)
            with self.assertRaises(KnowledgeError) as raised:
                write_implementation_outcome(
                    str(repo),
                    work_id="work-outcome-ready-binding",
                    implementation_run_id=run_id,
                    work_kind="standard",
                    result="complete",
                    summary="The implementation is complete.",
                    changes=[
                        {"path": "src/change.md", "summary": "Changed behavior."}
                    ],
                    verification=[
                        {
                            "command_id": "CMD-FULL-001",
                            "outcome": "passed",
                            "evidence_refs": [output_refs["CMD-FULL-001"]],
                        }
                    ],
                    review=invalid_review,
                    known_deviations=[],
                    knowledge_decision="change",
                    bug_verification_ref=None,
                    created_at="2026-08-31T12:00:00+08:00",
                )
            self.assertEqual("PRELIMINARY_REVIEW_INVALID", raised.exception.code)
        self.assertFalse(
            (repo / "docs/work/work-outcome-ready-binding/implementation").exists()
        )

    def test_outcome_revisions_keep_a_create_only_final_review_fix_history(self) -> None:
        from knowledge_outcome import write_implementation_outcome
        from knowledge_query import KnowledgeError

        _remove_fixture(self.fixture_root)
        repo = self.fixture_root / "outcome-revisions"
        repo.mkdir(parents=True)
        _git(repo, "init", "-q")
        source = repo / "src/change.md"
        _write(source, "first reviewed change\n")
        _git(repo, "add", ".")
        host_temp = self.fixture_root / "host-temp"
        run_id = "f" * 64

        def write_revision(
            revision: int,
            review: dict[str, object],
            output_ref: str,
        ) -> dict[str, object]:
            return write_implementation_outcome(
                str(repo),
                work_id="work-outcome-revisions",
                implementation_run_id=run_id,
                revision=revision,
                work_kind="standard",
                result="complete",
                summary=f"Implementation outcome revision {revision} is reviewed.",
                changes=[{"path": "src/change.md", "summary": "Changed behavior."}],
                verification=[
                    {
                        "command_id": "CMD-FULL-001",
                        "outcome": "passed",
                        "evidence_refs": [output_ref],
                    }
                ],
                review=review,
                known_deviations=[],
                knowledge_decision="change",
                bug_verification_ref=None,
                created_at="2026-08-31T12:00:00+08:00",
            )

        with mock.patch("knowledge_outcome.tempfile.gettempdir", return_value=str(host_temp)):
            review_1, outputs_1 = _persist_preliminary_review_fixture(
                implementation_run_id=run_id,
                logical_ref="review:fresh-review:outcome-revision-r1",
                command_ids=["CMD-FULL-001"],
                round_number=1,
            )
            first = write_revision(1, review_1, outputs_1["CMD-FULL-001"])
            source.write_text("second reviewed change\n", encoding="utf-8", newline="\n")
            review_2, outputs_2 = _persist_preliminary_review_fixture(
                implementation_run_id=run_id,
                logical_ref="review:fresh-review:outcome-revision-r2",
                command_ids=["CMD-FULL-001"],
                round_number=2,
            )
            second = write_revision(2, review_2, outputs_2["CMD-FULL-001"])
            with self.assertRaises(KnowledgeError) as gap:
                write_revision(4, review_2, outputs_2["CMD-FULL-001"])
            self.assertEqual("OUTCOME_REVISION_INVALID", gap.exception.code)

        self.assertTrue(str(first["path"]).endswith("/outcome.json"))
        self.assertTrue(str(second["path"]).endswith("/outcome-2.json"))
        self.assertTrue((repo / "docs/work/work-outcome-revisions/implementation/outcome.md").is_file())
        self.assertTrue((repo / "docs/work/work-outcome-revisions/implementation/outcome-2.md").is_file())

    def test_create_only_pair_preserves_commit_boundary_competitors(self) -> None:
        import knowledge_governance
        import knowledge_outcome
        from knowledge_query import KnowledgeError

        for collision_code in ("OUTCOME_EXISTS", "PRELIMINARY_REVIEW_EXISTS"):
            with self.subTest(collision_code=collision_code):
                _remove_fixture(self.fixture_root)
                root = self.fixture_root / collision_code.casefold()
                first = root / "outcome.md"
                second = root / "outcome.json"
                first_competitor = b"independent first entry\n"
                second_competitor = b"independent second entry\n"
                original_replace = os.replace
                original_publish = getattr(
                    knowledge_governance,
                    "_rename_path_create_only",
                    None,
                )
                first_injected = False
                second_injected = False

                def inject_for_legacy_replace(
                    source: object,
                    destination: object,
                ) -> None:
                    nonlocal first_injected, second_injected
                    destination_path = Path(destination)
                    if destination_path == second and not second_injected:
                        second.parent.mkdir(parents=True, exist_ok=True)
                        second.write_bytes(second_competitor)
                        second_injected = True
                    original_replace(source, destination)
                    if destination_path == first and not first_injected:
                        first.write_bytes(first_competitor)
                        first_injected = True

                def inject_for_atomic_publish(
                    source: Path,
                    destination: Path,
                    **kwargs: object,
                ) -> None:
                    nonlocal first_injected, second_injected
                    if original_publish is None:
                        raise AssertionError("atomic create-only publisher is missing")
                    destination_path = Path(destination)
                    if destination_path == second and not second_injected:
                        second.parent.mkdir(parents=True, exist_ok=True)
                        second.write_bytes(second_competitor)
                        second_injected = True
                    original_publish(source, destination, **kwargs)
                    if destination_path == first and not first_injected:
                        first.write_bytes(first_competitor)
                        first_injected = True

                with (
                    mock.patch(
                        "knowledge_outcome.os.replace",
                        side_effect=inject_for_legacy_replace,
                    ),
                    mock.patch.object(
                        knowledge_governance,
                        "_rename_path_create_only",
                        side_effect=inject_for_atomic_publish,
                        create=True,
                    ),
                    self.assertRaises(KnowledgeError) as raised,
                ):
                    knowledge_outcome._write_pair_create_only(
                        [
                            (first, b"owned markdown\n"),
                            (second, b"owned json\n"),
                        ],
                        collision_code=collision_code,
                    )

                self.assertTrue(first_injected)
                self.assertTrue(second_injected)
                self.assertEqual(collision_code, raised.exception.code)
                self.assertEqual(first_competitor, first.read_bytes())
                self.assertEqual(second_competitor, second.read_bytes())

    def test_create_only_pair_preserves_byte_identical_independent_first_entry(self) -> None:
        import knowledge_governance
        import knowledge_outcome
        from knowledge_query import KnowledgeError

        for collision_code in ("OUTCOME_EXISTS", "PRELIMINARY_REVIEW_EXISTS"):
            with self.subTest(collision_code=collision_code):
                _remove_fixture(self.fixture_root)
                root = self.fixture_root / f"{collision_code.casefold()}-identical"
                first = root / "outcome.md"
                second = root / "outcome.json"
                first_value = b"byte-identical first entry\n"
                second_competitor = b"independent second entry\n"
                original_publish = knowledge_governance._rename_path_create_only
                first_replaced = False
                second_injected = False

                def inject_independent_entries(
                    source: Path,
                    destination: Path,
                    **kwargs: object,
                ) -> None:
                    nonlocal first_replaced, second_injected
                    destination_path = Path(destination)
                    if destination_path == second and not second_injected:
                        second.parent.mkdir(parents=True, exist_ok=True)
                        second.write_bytes(second_competitor)
                        second_injected = True
                    original_publish(source, destination, **kwargs)
                    if destination_path == first and not first_replaced:
                        first.unlink()
                        first.write_bytes(first_value)
                        first_replaced = True

                with (
                    mock.patch.object(
                        knowledge_governance,
                        "_rename_path_create_only",
                        side_effect=inject_independent_entries,
                    ),
                    self.assertRaises(KnowledgeError) as raised,
                ):
                    knowledge_outcome._write_pair_create_only(
                        [
                            (first, first_value),
                            (second, b"owned json\n"),
                        ],
                        collision_code=collision_code,
                    )

                self.assertTrue(first_replaced)
                self.assertTrue(second_injected)
                self.assertEqual(collision_code, raised.exception.code)
                self.assertTrue(first.is_file(), "rollback deleted the independent first entry")
                self.assertEqual(first_value, first.read_bytes())
                self.assertEqual(second_competitor, second.read_bytes())
                self.assertFalse(list(root.glob(".*.owner")))

    def test_verified_bug_maps_to_verified_incident_claims(self) -> None:
        report = _exercise_bug_knowledge_mapping(self.fixture_root, result="verified")
        self.assertEqual(["verified"], report["evidence_classes"])
        self.assertIn("Original symptom after change: absent", report["page_text"])
        self.assertEqual("passed", report["lint"])

    def test_partial_bug_maps_to_unresolved_partial_claims(self) -> None:
        report = _exercise_bug_knowledge_mapping(self.fixture_root, result="partial")
        self.assertEqual(["partial"], report["evidence_classes"])
        self.assertIn("Status: Partial / Unresolved", report["page_text"])
        self.assertEqual("BUG_VERIFICATION_INVALID", report["overclaim_rejected"])
        self.assertEqual("passed", report["lint"])

    def test_candidate_loader_rejects_redirected_registry_ancestor(self) -> None:
        import knowledge_governance
        from knowledge_delivery import build_knowledge_snapshot
        from knowledge_promotion import seal_candidate_draft
        from knowledge_query import KnowledgeError

        _remove_fixture(self.fixture_root)
        repo = self.fixture_root / "candidate-redirect-repo"
        repo.mkdir(parents=True)
        _git(repo, "init", "-q")
        _write(repo / "README.md", "# Candidate redirect fixture\n")
        _git(repo, "add", ".")
        registry = self.fixture_root / "candidate-registry"
        with mock.patch(
            "knowledge_governance.default_registry_root",
            return_value=registry,
        ):
            sealed = seal_candidate_draft(
                str(repo),
                draft={
                    "schema": "knowledge-candidate-draft/v1",
                    "stage": "implementation",
                    "work_id": "work-candidate-redirect",
                    "decision": "no-change",
                    "source_snapshot": [],
                    "operations": [],
                },
                approval_actor="knowledge-owner",
                approval_evidence="conversation:candidate-redirect-approved",
            )

        repo_id = knowledge_governance.repository_id(repo)
        registry_repo = registry / "repos" / repo_id
        external_repo = self.fixture_root / "external-candidate-registry"
        shutil.move(str(registry_repo), str(external_repo))
        try:
            os.symlink(external_repo, registry_repo, target_is_directory=True)
        except (OSError, NotImplementedError):
            completed = subprocess.run(
                [
                    "cmd",
                    "/d",
                    "/c",
                    "mklink",
                    "/J",
                    str(registry_repo),
                    str(external_repo),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                shell=False,
            )
            self.assertEqual(
                0,
                completed.returncode,
                completed.stderr.decode("utf-8", errors="replace"),
            )
        try:
            self.assertTrue(
                registry_repo.is_symlink()
                or getattr(registry_repo, "is_junction", lambda: False)()
            )
            with (
                mock.patch(
                    "knowledge_governance.default_registry_root",
                    return_value=registry,
                ),
                self.assertRaises(KnowledgeError) as raised,
            ):
                build_knowledge_snapshot(str(repo), sealed=sealed)
            self.assertEqual("CANDIDATE_MISSING", raised.exception.code)
        finally:
            if registry_repo.is_symlink():
                registry_repo.unlink()
            else:
                os.rmdir(registry_repo)

    def test_candidate_loader_rejects_candidate_swap_during_read(self) -> None:
        import knowledge_governance
        from knowledge_delivery import build_knowledge_snapshot
        from knowledge_promotion import seal_candidate_draft
        from knowledge_query import KnowledgeError

        _remove_fixture(self.fixture_root)
        repo = self.fixture_root / "candidate-swap-repo"
        repo.mkdir(parents=True)
        _git(repo, "init", "-q")
        _write(repo / "README.md", "# Candidate swap fixture\n")
        _git(repo, "add", ".")
        registry = self.fixture_root / "candidate-swap-registry"
        with mock.patch(
            "knowledge_governance.default_registry_root",
            return_value=registry,
        ):
            sealed = seal_candidate_draft(
                str(repo),
                draft={
                    "schema": "knowledge-candidate-draft/v1",
                    "stage": "implementation",
                    "work_id": "work-candidate-swap",
                    "decision": "no-change",
                    "source_snapshot": [],
                    "operations": [],
                },
                approval_actor="knowledge-owner",
                approval_evidence="conversation:candidate-swap-approved",
            )

        repo_id = knowledge_governance.repository_id(repo)
        promotion_id = sealed["candidate_ref"].split("/")[1]
        candidate_path = (
            registry
            / "repos"
            / repo_id
            / "candidates"
            / promotion_id
            / "candidate.json"
        )
        original_read_bytes = Path.read_bytes
        swapped = False

        def swap_after_read(path: Path) -> bytes:
            nonlocal swapped
            raw = original_read_bytes(path)
            if path == candidate_path and not swapped:
                replacement = candidate_path.with_suffix(".replacement")
                replacement.write_bytes(b"{}\n")
                os.replace(replacement, candidate_path)
                swapped = True
            return raw

        with (
            mock.patch(
                "knowledge_governance.default_registry_root",
                return_value=registry,
            ),
            mock.patch.object(Path, "read_bytes", new=swap_after_read),
            self.assertRaises(KnowledgeError) as raised,
        ):
            build_knowledge_snapshot(str(repo), sealed=sealed)
        self.assertTrue(swapped)
        self.assertEqual("CANDIDATE_INVALID", raised.exception.code)

    def test_promotion_loader_rejects_redirected_registry_ancestor(self) -> None:
        import knowledge_governance
        import knowledge_promotion
        from knowledge_promotion import seal_candidate_draft
        from knowledge_query import KnowledgeError

        _remove_fixture(self.fixture_root)
        repo = self.fixture_root / "promotion-redirect-repo"
        repo.mkdir(parents=True)
        _git(repo, "init", "-q")
        _write(repo / "README.md", "# Promotion redirect fixture\n")
        _git(repo, "add", ".")
        registry = self.fixture_root / "promotion-redirect-registry"
        with mock.patch(
            "knowledge_governance.default_registry_root",
            return_value=registry,
        ):
            sealed = seal_candidate_draft(
                str(repo),
                draft={
                    "schema": "knowledge-candidate-draft/v1",
                    "stage": "implementation",
                    "work_id": "work-promotion-redirect",
                    "decision": "no-change",
                    "source_snapshot": [],
                    "operations": [],
                },
                approval_actor="knowledge-owner",
                approval_evidence="conversation:promotion-redirect-approved",
            )

        repo_id = knowledge_governance.repository_id(repo)
        registry_repo = registry / "repos" / repo_id
        external_repo = self.fixture_root / "external-promotion-registry"
        shutil.move(str(registry_repo), str(external_repo))
        try:
            os.symlink(external_repo, registry_repo, target_is_directory=True)
        except (OSError, NotImplementedError):
            completed = subprocess.run(
                [
                    "cmd",
                    "/d",
                    "/c",
                    "mklink",
                    "/J",
                    str(registry_repo),
                    str(external_repo),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                shell=False,
            )
            self.assertEqual(
                0,
                completed.returncode,
                completed.stderr.decode("utf-8", errors="replace"),
            )
        try:
            with self.assertRaises(KnowledgeError) as raised:
                knowledge_promotion._load_candidate(
                    registry_repo,
                    sealed["candidate_ref"],
                )
            self.assertEqual("CANDIDATE_MISSING", raised.exception.code)
        finally:
            if registry_repo.is_symlink():
                registry_repo.unlink()
            else:
                os.rmdir(registry_repo)

    def test_candidate_sealer_rejects_redirected_registry_ancestor(self) -> None:
        import knowledge_governance
        from knowledge_promotion import seal_candidate_draft
        from knowledge_query import KnowledgeError

        _remove_fixture(self.fixture_root)
        repo = self.fixture_root / "sealer-redirect-repo"
        repo.mkdir(parents=True)
        _git(repo, "init", "-q")
        _write(repo / "README.md", "# Sealer redirect fixture\n")
        _git(repo, "add", ".")
        registry = self.fixture_root / "sealer-redirect-registry"
        repo_id = knowledge_governance.repository_id(repo)
        registry_repo = registry / "repos" / repo_id
        registry_repo.mkdir(parents=True)
        external_repo = self.fixture_root / "external-sealer-registry"
        shutil.move(str(registry_repo), str(external_repo))
        try:
            os.symlink(external_repo, registry_repo, target_is_directory=True)
        except (OSError, NotImplementedError):
            completed = subprocess.run(
                [
                    "cmd",
                    "/d",
                    "/c",
                    "mklink",
                    "/J",
                    str(registry_repo),
                    str(external_repo),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                shell=False,
            )
            self.assertEqual(
                0,
                completed.returncode,
                completed.stderr.decode("utf-8", errors="replace"),
            )
        try:
            with (
                mock.patch(
                    "knowledge_governance.default_registry_root",
                    return_value=registry,
                ),
                self.assertRaises(KnowledgeError) as raised,
            ):
                seal_candidate_draft(
                    str(repo),
                    draft={
                        "schema": "knowledge-candidate-draft/v1",
                        "stage": "implementation",
                        "work_id": "work-sealer-redirect",
                        "decision": "no-change",
                        "source_snapshot": [],
                        "operations": [],
                    },
                    approval_actor="knowledge-owner",
                    approval_evidence="conversation:sealer-redirect-approved",
                )
            self.assertEqual("UNSAFE_REGISTRY", raised.exception.code)
            self.assertFalse((external_repo / "candidates").exists())
        finally:
            if registry_repo.is_symlink():
                registry_repo.unlink()
            else:
                os.rmdir(registry_repo)

    def test_promotion_loader_rejects_candidate_swap_during_read(self) -> None:
        import knowledge_governance
        import knowledge_promotion
        from knowledge_promotion import seal_candidate_draft
        from knowledge_query import KnowledgeError

        _remove_fixture(self.fixture_root)
        repo = self.fixture_root / "promotion-swap-repo"
        repo.mkdir(parents=True)
        _git(repo, "init", "-q")
        _write(repo / "README.md", "# Promotion swap fixture\n")
        _git(repo, "add", ".")
        registry = self.fixture_root / "promotion-swap-registry"
        with mock.patch(
            "knowledge_governance.default_registry_root",
            return_value=registry,
        ):
            sealed = seal_candidate_draft(
                str(repo),
                draft={
                    "schema": "knowledge-candidate-draft/v1",
                    "stage": "implementation",
                    "work_id": "work-promotion-swap",
                    "decision": "no-change",
                    "source_snapshot": [],
                    "operations": [],
                },
                approval_actor="knowledge-owner",
                approval_evidence="conversation:promotion-swap-approved",
            )

        repo_id = knowledge_governance.repository_id(repo)
        promotion_id = sealed["candidate_ref"].split("/")[1]
        repo_root = registry / "repos" / repo_id
        candidate_path = (
            repo_root
            / "candidates"
            / promotion_id
            / "candidate.json"
        )
        original_read_bytes = Path.read_bytes
        swapped = False

        def swap_after_read(path: Path) -> bytes:
            nonlocal swapped
            raw = original_read_bytes(path)
            if path == candidate_path and not swapped:
                replacement = candidate_path.with_suffix(".replacement")
                replacement.write_bytes(b"{}\n")
                os.replace(replacement, candidate_path)
                swapped = True
            return raw

        with (
            mock.patch.object(Path, "read_bytes", new=swap_after_read),
            self.assertRaises(KnowledgeError) as raised,
        ):
            knowledge_promotion._load_candidate(repo_root, sealed["candidate_ref"])
        self.assertTrue(swapped)
        self.assertEqual("CANDIDATE_INVALID", raised.exception.code)

    def test_windows_linux_reports_require_one_functional_oracle(self) -> None:
        functional = {
            "schema": "test-functional/v1",
            "paths": ["a/b"],
            "queries": [],
        }
        digest = canonical_sha256(functional)
        query_digest = canonical_sha256(functional["queries"])
        original = compare_portability_reports.EXPECTED_FUNCTIONAL_SHA256
        compare_portability_reports.EXPECTED_FUNCTIONAL_SHA256 = digest
        try:
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
                    "functional_sha256": digest,
                    "warm_queries_sha256": query_digest,
                    "cold_queries_sha256": query_digest,
                    "durations_seconds": {
                        "queries": [0.1, 0.2, 0.3, 0.4, 0.5],
                        "cold_queries": [0.1, 0.2, 0.3, 0.4, 0.5],
                        "index_candidate": 0.6,
                        "fixture_setup": 1.0,
                    },
                }
                for os_name in ("windows", "linux")
            ]
            comparison = compare_portability_reports.compare_reports(reports)
        finally:
            compare_portability_reports.EXPECTED_FUNCTIONAL_SHA256 = original
        self.assertEqual("passed", comparison["outcome"])
        self.assertEqual(["linux", "windows"], comparison["oses"])

    def test_portability_comparison_fails_on_missing_or_slow_platform(self) -> None:
        functional = {"queries": []}
        query_digest = canonical_sha256(functional["queries"])
        report = {
            "schema": "knowledge-portability-report/v1",
            "outcome": "passed",
            "host": {"os": "windows"},
            "file_count": 50_000,
            "page_count": 5_000,
            "source_file_count": 39_998,
            "total_fixture_files": 50_000,
            "tracked_fixture": False,
            "functional": functional,
            "functional_sha256": canonical_sha256(functional),
            "warm_queries_sha256": query_digest,
            "cold_queries_sha256": query_digest,
            "durations_seconds": {
                "queries": [2.001, 0.2, 0.3, 0.4, 0.5],
                "cold_queries": [0.1, 0.2, 0.3, 0.4, 0.5],
                "index_candidate": 0.6,
                "fixture_setup": 1.0,
            },
        }
        comparison = compare_portability_reports.compare_reports([report])
        self.assertEqual("failed", comparison["outcome"])
        self.assertTrue(any("missing OS reports" in item for item in comparison["diagnostics"]))
        self.assertTrue(any("exceeded" in item for item in comparison["diagnostics"]))
        self.assertTrue(any("tracked-file shape" in item for item in comparison["diagnostics"]))

        unsupported = dict(report)
        unsupported["host"] = {"os": "macos"}
        unsupported_comparison = compare_portability_reports.compare_reports([unsupported])
        self.assertEqual("failed", unsupported_comparison["outcome"])
        self.assertTrue(
            any(
                "unsupported or missing host OS" in item
                for item in unsupported_comparison["diagnostics"]
            )
        )


class HumanGateReviewTests(unittest.TestCase):
    workspace: Path
    fixture_root: Path

    def tearDown(self) -> None:
        _remove_fixture(self.fixture_root)

    def test_bootstrap_and_lint_repair_resume_preserve_gate_summary(self) -> None:
        import knowledge_governance
        from knowledge_cli import main

        def invoke(repo: Path, registry: Path, arguments: list[str]) -> tuple[dict[str, object], str]:
            stdout = io.StringIO()
            stderr = io.StringIO()
            with (
                mock.patch.object(
                    knowledge_governance,
                    "default_registry_root",
                    return_value=registry,
                ),
                contextlib.redirect_stdout(stdout),
                contextlib.redirect_stderr(stderr),
            ):
                exit_code = main(arguments)
            self.assertEqual(0, exit_code, stderr.getvalue())
            return json.loads(stdout.getvalue()), stdout.getvalue()

        bootstrap_repo = _build_governance_fixture(self.fixture_root)
        bootstrap_registry = self.fixture_root / "bootstrap-resume-registry"
        bootstrap, bootstrap_rendered = invoke(
            bootstrap_repo,
            bootstrap_registry,
            [
                "bootstrap",
                "--repo",
                str(bootstrap_repo),
                "--approval-actor",
                "bootstrap-owner",
                "--approval-evidence",
                "fixture:bootstrap-resume",
            ],
        )
        resumed_bootstrap, resumed_bootstrap_rendered = invoke(
            bootstrap_repo,
            bootstrap_registry,
            [
                "review",
                "--repo",
                str(bootstrap_repo),
                "--candidate-ref",
                str(bootstrap["identity"]["candidate_ref"]),
            ],
        )
        self.assertEqual(bootstrap["summary"], resumed_bootstrap["summary"])
        self.assertEqual(bootstrap_rendered, resumed_bootstrap_rendered)

        repair_repo = _build_retrieval_fixture(self.fixture_root)
        repair_registry = self.fixture_root / "repair-resume-registry"
        _write(
            repair_repo / "src/stale-boundary.md",
            "Changed stale advice must not be silently trusted.\n",
        )
        repair, repair_rendered = invoke(
            repair_repo,
            repair_registry,
            [
                "lint",
                "--repo",
                str(repair_repo),
                "--approval-actor",
                "repair-owner",
                "--approval-evidence",
                "fixture:repair-resume",
            ],
        )
        resumed_repair, resumed_repair_rendered = invoke(
            repair_repo,
            repair_registry,
            [
                "review",
                "--repo",
                str(repair_repo),
                "--candidate-ref",
                str(repair["identity"]["candidate_ref"]),
            ],
        )
        self.assertEqual(repair["summary"], resumed_repair["summary"])
        self.assertEqual(repair_rendered, resumed_repair_rendered)

    def test_operation_review_file_target_collision_is_rejected(self) -> None:
        import knowledge_governance
        from knowledge_promotion import seal_candidate_draft
        from knowledge_query import KnowledgeError

        repo = _build_promotion_fixture(self.fixture_root)
        registry = self.fixture_root / "cross-role-collision-registry"
        collision_target = "docs/knowledge/topics/cross-role-collision.md"
        collision_content = "# Existing review source\n"
        _write(repo / collision_target, collision_content)
        _git(repo, "add", ".")
        before_repo = _tree_snapshot(repo)
        before_registry = _tree_snapshot(registry)

        with mock.patch.object(
            knowledge_governance,
            "default_registry_root",
            return_value=registry,
        ):
            for operation_path, kind in (
                (collision_target, "update"),
                ("docs/knowledge/topics/CROSS-ROLE-COLLISION.md", "create"),
            ):
                with self.subTest(operation_path=operation_path):
                    with self.assertRaises(KnowledgeError) as collision:
                        seal_candidate_draft(
                            str(repo),
                            draft={
                                "schema": "knowledge-candidate-draft/v1",
                                "stage": "implementation",
                                "work_id": "work-cross-role-collision",
                                "decision": "change",
                                "source_snapshot": [],
                                "review_files": [
                                    {
                                        "role": "supporting",
                                        "target_path": collision_target,
                                        "content": collision_content,
                                    }
                                ],
                                "operations": [
                                    {
                                        "kind": kind,
                                        "path": operation_path,
                                        "postimage": "# Proposed replacement\n",
                                    }
                                ],
                            },
                            approval_actor="collision-owner",
                            approval_evidence="fixture:cross-role-collision",
                        )
                    self.assertEqual("REVIEW_TARGET_COLLISION", collision.exception.code)

        self.assertEqual(before_repo, _tree_snapshot(repo))
        self.assertEqual(before_registry, _tree_snapshot(registry))

    def test_seal_persists_complete_review_sidecar(self) -> None:
        import knowledge_governance
        from knowledge_promotion import seal_candidate_draft

        repo = _build_promotion_fixture(self.fixture_root)
        registry = self.fixture_root / "human-gate-registry"
        supporting_path = repo / "evidence/human-gate-context.md"
        supporting_text = "# Human Gate context\n\nComplete supporting evidence.\n"
        _write(supporting_path, supporting_text)
        before = _tree_snapshot(repo)
        with mock.patch.object(
            knowledge_governance,
            "default_registry_root",
            return_value=registry,
        ):
            sealed = seal_candidate_draft(
                str(repo),
                draft={
                    "schema": "knowledge-candidate-draft/v1",
                    "stage": "implementation",
                    "work_id": "work-human-gate-review",
                    "decision": "change",
                    "source_snapshot": [],
                    "review_files": [
                        {
                            "role": "supporting",
                            "target_path": "evidence/human-gate-context.md",
                            "content": supporting_text,
                        }
                    ],
                    "operations": [
                        {
                            "kind": "create",
                            "path": "docs/knowledge/topics/human-gate-review.md",
                            "postimage": "# Human gate review\n",
                        }
                    ],
                },
                approval_actor="review-owner",
                approval_evidence="fixture:human-gate-review",
            )

        self.assertIn("review_sha256", sealed)
        self.assertIn("review_ref", sealed)
        candidate_path = (
            registry
            / "repos"
            / sealed["repo_id"]
            / Path(*sealed["candidate_ref"].removeprefix("knowledge:").split("/"))
        )
        review_path = candidate_path.with_name("review.json")
        self.assertTrue(review_path.is_file())
        review_raw = review_path.read_bytes()
        self.assertEqual(_sha256(review_raw), sealed["review_sha256"])
        review = json.loads(review_raw)
        self.assertEqual("human-gate-review/v1", review["schema"])
        self.assertEqual(sealed["candidate_ref"], review["identity"]["candidate_ref"])
        self.assertEqual(sealed["payload_sha256"], review["identity"]["payload_sha256"])
        self.assertEqual("passed", review["validation"]["outcome"])
        expected_stored = {
            "candidate.json",
            *(
                operation["postimage_ref"]
                for operation in json.loads(candidate_path.read_text(encoding="utf-8"))[
                    "operations"
                ]
            ),
            *(
                review_file["stored_path"]
                for review_file in json.loads(
                    candidate_path.read_text(encoding="utf-8")
                )["review_files"]
            ),
        }
        self.assertEqual(
            expected_stored,
            {
                item["stored_path"]
                for item in review["review_bundle"]["manifest"]
            },
        )
        supporting_entry = next(
            item
            for item in review["review_bundle"]["manifest"]
            if item["role"] == "supporting"
        )
        self.assertEqual("evidence/human-gate-context.md", supporting_entry["target_path"])
        self.assertEqual(
            supporting_text.encode("utf-8"),
            (candidate_path.parent / supporting_entry["stored_path"]).read_bytes(),
        )
        self.assertEqual(before, _tree_snapshot(repo))

    def test_review_sidecar_failure_publishes_no_partial_candidate(self) -> None:
        import knowledge_governance
        from knowledge_promotion import seal_candidate_draft

        repo = _build_promotion_fixture(self.fixture_root)
        registry = self.fixture_root / "atomic-review-registry"
        real_atomic_create = knowledge_governance._atomic_create

        def fail_review(path: Path, value: bytes) -> None:
            if path.name == "review.json":
                raise OSError("injected review sidecar failure")
            real_atomic_create(path, value)

        with (
            mock.patch.object(
                knowledge_governance,
                "default_registry_root",
                return_value=registry,
            ),
            mock.patch.object(
                knowledge_governance,
                "_atomic_create",
                side_effect=fail_review,
            ),
            self.assertRaisesRegex(OSError, "injected review sidecar failure"),
        ):
            seal_candidate_draft(
                str(repo),
                draft={
                    "schema": "knowledge-candidate-draft/v1",
                    "stage": "implementation",
                    "work_id": "work-atomic-review",
                    "decision": "change",
                    "source_snapshot": [],
                    "operations": [
                        {
                            "kind": "create",
                            "path": "docs/knowledge/topics/atomic-review.md",
                            "postimage": "# Atomic review\n",
                        }
                    ],
                },
                approval_actor="review-owner",
                approval_evidence="fixture:atomic-review",
            )
        candidates = list(registry.glob("repos/*/candidates/*"))
        self.assertEqual([], candidates)

    def test_review_projection_is_closed_and_summary_only(self) -> None:
        import knowledge_governance
        from knowledge_promotion import review_candidate, seal_candidate_draft

        sentinel = "FULL_PAYLOAD_SENTINEL_TEST_022_1b73d9a4"
        repo = _build_promotion_fixture(self.fixture_root)
        registry = self.fixture_root / "summary-projection-registry"
        with mock.patch.object(
            knowledge_governance,
            "default_registry_root",
            return_value=registry,
        ):
            sealed = seal_candidate_draft(
                str(repo),
                draft={
                    "schema": "knowledge-candidate-draft/v1",
                    "stage": "implementation",
                    "work_id": "work-summary-projection",
                    "decision": "change",
                    "source_snapshot": [],
                    "operations": [
                        {
                            "kind": "create",
                            "path": "docs/knowledge/topics/summary-projection.md",
                            "postimage": "# Summary projection\n\n" + ("large\n" * 8_000) + sentinel,
                        }
                    ],
                },
                approval_actor="review-owner",
                approval_evidence="fixture:summary-projection",
            )
            summary = review_candidate(
                str(repo),
                candidate_ref=sealed["candidate_ref"],
            )

        self.assertEqual("human-gate-summary/v1", summary["schema"])
        candidate_path = (
            registry
            / "repos"
            / sealed["repo_id"]
            / Path(*sealed["candidate_ref"].removeprefix("knowledge:").split("/"))
        )
        candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
        self.assertEqual("gate-specific-summary/v1", candidate["review_projection"])
        self.assertEqual(
            {
                "schema",
                "gate",
                "summary",
                "risk_and_compatibility",
                "validation",
                "review_bundle",
                "identity",
                "prompt",
            },
            set(summary),
        )
        rendered = json.dumps(summary, ensure_ascii=False, sort_keys=True)
        self.assertEqual(
            "Review the standalone Knowledge Candidate and proposed observed knowledge "
            "changes before approval.",
            summary["summary"]["purpose"],
        )
        self.assertEqual(
            {
                "description": (
                    "Publish the standalone Candidate's proposed observed knowledge "
                    "revision."
                ),
                "operation_count": 3,
                "create_count": 3,
                "update_count": 0,
                "review_file_count": 0,
            },
            summary["summary"]["change"],
        )
        self.assertEqual(
            {
                "bug_assessment": None,
                "occurrence": None,
                "implementation_outcome": None,
            },
            summary["risk_and_compatibility"]["material"],
        )
        self.assertNotIn(sentinel, rendered)
        self.assertNotIn('"postimage":', rendered)
        self.assertNotIn('"postimages":', rendered)
        self.assertEqual(sealed["review_sha256"], summary["identity"]["review_sha256"])
        for item in summary["review_bundle"]["manifest"]:
            path = Path(item["direct_path"])
            self.assertTrue(path.is_absolute())
            self.assertTrue(path.is_file())
        schema = json.loads(
            (
                self.workspace
                / ".agents/skills/project-knowledge/schemas/knowledge-contracts.schema.json"
            ).read_text(encoding="utf-8")
        )
        for definition_name in ("humanGateReview", "humanGateSummary"):
            definition = schema["$defs"][definition_name]
            self.assertIs(False, definition["additionalProperties"])

    def test_yaml_occurrence_projection_counts_explicit_manual_review_entries(self) -> None:
        from knowledge_promotion import _occurrence_projection

        occurrence = (
            "schema: occurrence-map/v1\n"
            "change_mode: targeted_edit\n"
            "categories:\n"
            "  code_symbols:\n"
            "    action: manual_review\n"
            "  import_paths:\n"
            "    action: do_not_change\n"
            "exceptions:\n"
            "  - paths: docs/example.md\n"
            "    action: \"manual_review\"\n"
            "  - paths: docs/other.md\n"
            "    action: 'manual_review' # explicit classification\n"
        )
        for suffix in ("yaml", "yml"):
            with self.subTest(suffix=suffix):
                projection = _occurrence_projection(
                    {
                        f"docs/work/work-occurrence/plan/occurrence_map.{suffix}": (
                            occurrence.encode("utf-8")
                        )
                    }
                )
                self.assertIsNotNone(projection)
                self.assertEqual(3, projection["manual_review_item_count"])
                self.assertTrue(projection["manual_review_required"])
                self.assertEqual(
                    "manual-review-required",
                    projection["classification_risk"],
                )

                mutated = _occurrence_projection(
                    {
                        f"docs/work/work-occurrence/plan/occurrence_map.{suffix}": (
                            occurrence.replace("manual_review", "do_not_change")
                        ).encode("utf-8")
                    }
                )
                self.assertIsNotNone(mutated)
                self.assertEqual(0, mutated["manual_review_item_count"])
                self.assertFalse(mutated["manual_review_required"])
                self.assertEqual("none", mutated["classification_risk"])

    def test_review_projection_revalidates_an_already_read_linked_file(self) -> None:
        import knowledge_governance
        from knowledge_promotion import review_candidate, seal_candidate_draft
        from knowledge_query import KnowledgeError

        repo = _build_promotion_fixture(self.fixture_root)
        registry = self.fixture_root / "review-projection-drift-registry"
        with mock.patch.object(
            knowledge_governance,
            "default_registry_root",
            return_value=registry,
        ):
            sealed = seal_candidate_draft(
                str(repo),
                draft={
                    "schema": "knowledge-candidate-draft/v1",
                    "stage": "implementation",
                    "work_id": "work-review-projection-drift",
                    "decision": "change",
                    "source_snapshot": [],
                    "operations": [
                        {
                            "kind": "create",
                            "path": "docs/knowledge/topics/review-projection-drift.md",
                            "postimage": "# Stable before projection\n",
                        }
                    ],
                },
                approval_actor="review-owner",
                approval_evidence="fixture:review-projection-drift",
            )
            candidate_path = (
                registry
                / "repos"
                / sealed["repo_id"]
                / Path(*sealed["candidate_ref"].removeprefix("knowledge:").split("/"))
            )
            candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
            linked_path = candidate_path.parent / Path(
                *candidate["operations"][0]["postimage_ref"].split("/")
            )
            original_read = knowledge_governance._stable_registry_read
            injected = False

            def read_then_mutate(*args: object, **kwargs: object) -> bytes:
                nonlocal injected
                raw = original_read(*args, **kwargs)
                path = Path(args[1])
                if (
                    not injected
                    and path == linked_path
                    and kwargs.get("label") == "human Gate review file"
                ):
                    linked_path.write_bytes(raw + b"drift")
                    injected = True
                return raw

            with mock.patch.object(
                knowledge_governance,
                "_stable_registry_read",
                side_effect=read_then_mutate,
            ):
                with self.assertRaises(KnowledgeError) as drifted:
                    review_candidate(str(repo), candidate_ref=sealed["candidate_ref"])
            self.assertTrue(injected)
            self.assertIn(
                drifted.exception.code,
                {"POSTIMAGE_DRIFT", "REVIEW_FILE_DRIFT", "REVIEW_MANIFEST_DRIFT"},
            )

    def test_human_gate_owner_contract_is_single_source_and_mutation_sensitive(self) -> None:
        authority = (
            self.workspace
            / ".agents/skills/project-knowledge/references/human-gate-review.md"
        )
        self.assertTrue(authority.is_file(), "shared human Gate authority is missing")
        self.assertEqual([], knowledge_contracts.governance_errors())
        pointer = ".agents/skills/project-knowledge/references/human-gate-review.md"
        owner_paths = (
            ".agents/skills/requirements-discovery/references/delivery-protocol.md",
            ".agents/skills/technical-planning/references/delivery-protocol.md",
            ".agents/skills/project-knowledge/SKILL.md",
            ".agents/skills/bug-diagnosis/SKILL.md",
            ".agents/skills/delivery-orchestrator/references/stage-routing.md",
            ".agents/skills/implementation-execution/references/delivery-protocol.md",
        )
        original_read = knowledge_contracts._read
        for owner_path in owner_paths:
            with self.subTest(owner=owner_path):
                def mutated_read(relative: str, target: str = owner_path) -> str:
                    text = original_read(relative)
                    return text.replace(pointer, "missing-human-gate-authority", 1) if relative == target else text

                with mock.patch.object(
                    knowledge_contracts,
                    "_read",
                    side_effect=mutated_read,
                ):
                    errors = knowledge_contracts.governance_errors()
                self.assertTrue(
                    any("human Gate owner" in error for error in errors),
                    (owner_path, errors),
                )

        owner_roots = (
            ".agents/skills/requirements-discovery/",
            ".agents/skills/technical-planning/",
            ".agents/skills/delivery-orchestrator/",
            ".agents/skills/bug-diagnosis/",
            ".agents/skills/implementation-execution/",
            ".agents/skills/project-knowledge/",
        )
        repository_files, inventory_errors = knowledge_contracts._eligible_repository_files()
        self.assertEqual([], inventory_errors)
        active_gate_paths = tuple(
            sorted(
                path.relative_to(self.workspace).as_posix()
                for path in repository_files
                if path.suffix.casefold() == ".md"
                and path.relative_to(self.workspace).as_posix().startswith(owner_roots)
                and not path.relative_to(self.workspace)
                .as_posix()
                .endswith("/scripts/behavior-evaluation-report.md")
            )
        )
        self.assertTrue(active_gate_paths)
        self.assertIn(
            ".agents/skills/requirements-discovery/references/behavior-evaluation.md",
            active_gate_paths,
        )
        self.assertIn(
            ".agents/skills/technical-planning/references/behavior-evaluation.md",
            active_gate_paths,
        )
        self.assertIn(
            ".agents/skills/delivery-orchestrator/references/behavior-evaluation.md",
            active_gate_paths,
        )
        self.assertFalse(
            any(path.endswith("/scripts/behavior-evaluation-report.md") for path in active_gate_paths)
        )

        semantic_variants = (
            "必須逐 byte 貼出候選內容後才可核准。",
            "所有 artifact 內容都要在確認前呈現。",
            "Show the entire payload before approval.",
            "Summary-only elsewhere；Show the entire payload before approval.",
            "Summary-only Chat: present all returned Candidate files in Chat for approval.",
            "Summary-only Chat: paste the complete payload into Chat for approval.",
            "Summary and direct links: show the entire payload before approval.",
        )
        with mock.patch.object(
            knowledge_contracts,
            "_eligible_repository_files",
            return_value=(repository_files, []),
        ):
            for index, active_path in enumerate(active_gate_paths):
                contradiction = semantic_variants[index % len(semantic_variants)]
                with self.subTest(contradictory_instruction=active_path):
                    def contradictory_read(
                        relative: str,
                        target: str = active_path,
                        injected: str = contradiction,
                    ) -> str:
                        text = original_read(relative)
                        return text + f"\n{injected}\n" if relative == target else text

                    with mock.patch.object(
                        knowledge_contracts,
                        "_read",
                        side_effect=contradictory_read,
                    ):
                        errors = knowledge_contracts.governance_errors()
                    self.assertTrue(
                        any(
                            "contradictory human Gate presentation" in error
                            and active_path in error
                            for error in errors
                        ),
                        (active_path, contradiction, errors),
                    )

        allowed_presentation_variants = (
            "Summary-only Chat: do not paste the complete payload into Chat for approval.",
            "Summary and direct links: never show the entire payload before approval.",
            "不得在 Chat 完整展示 Candidate；只提供摘要與直接連結。",
            "封存新版完整 bundle、以摘要和直接連結呈現並重新核准。",
        )
        for instruction in allowed_presentation_variants:
            with self.subTest(allowed_presentation_instruction=instruction):
                self.assertEqual(
                    (),
                    knowledge_contracts.contradictory_human_gate_instruction_lines(
                        instruction
                    ),
                )

    def test_apply_requires_the_exact_current_review_digest(self) -> None:
        import knowledge_governance
        from knowledge_promotion import apply_candidate, seal_candidate_draft
        from knowledge_query import KnowledgeError

        repo = _build_promotion_fixture(self.fixture_root)
        registry = self.fixture_root / "review-binding-registry"
        with mock.patch.object(
            knowledge_governance,
            "default_registry_root",
            return_value=registry,
        ):
            sealed = seal_candidate_draft(
                str(repo),
                draft={
                    "schema": "knowledge-candidate-draft/v1",
                    "stage": "implementation",
                    "work_id": "work-review-binding",
                    "decision": "change",
                    "source_snapshot": [],
                    "operations": [
                        {
                            "kind": "create",
                            "path": "docs/knowledge/bootstrap/catalog.md",
                            "postimage": "# Review binding\n",
                        }
                    ],
                },
                approval_actor="review-owner",
                approval_evidence="fixture:review-binding",
            )
            before = _tree_snapshot(repo)
            with self.assertRaises(KnowledgeError) as missing:
                apply_candidate(
                    str(repo),
                    candidate_ref=sealed["candidate_ref"],
                    approval_actor="review-owner",
                    approval_evidence="fixture:review-binding",
                )
            self.assertEqual("REVIEW_BINDING_MISSING", missing.exception.code)
            self.assertEqual(before, _tree_snapshot(repo))
            with self.assertRaises(KnowledgeError) as drifted:
                apply_candidate(
                    str(repo),
                    candidate_ref=sealed["candidate_ref"],
                    review_sha256="0" * 64,
                    approval_actor="review-owner",
                    approval_evidence="fixture:review-binding",
                )
            self.assertEqual("REVIEW_BINDING_DRIFT", drifted.exception.code)
            self.assertEqual(before, _tree_snapshot(repo))
            applied = apply_candidate(
                str(repo),
                candidate_ref=sealed["candidate_ref"],
                review_sha256=sealed["review_sha256"],
                approval_actor="review-owner",
                approval_evidence="fixture:review-binding",
            )
        self.assertEqual("knowledge-apply/v1", applied["schema"])

    def test_legacy_pending_and_historical_ready_compatibility(self) -> None:
        report = _exercise_human_gate_compatibility(self.fixture_root)
        self.assertEqual("passed", report["apply_lint"])
        self.assertEqual("knowledge-lint/v1", report["automatic_schema"])
        self.assertTrue(report["historical_ready_preserved"])
        self.assertTrue(report["legacy_reseal_required"])
        self.assertTrue(report["review_drift_rejected"])


TEST_CASES = {
    "StageHookContractTests": StageHookContractTests,
    "HumanGateReviewTests": HumanGateReviewTests,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("test_names", nargs="*", choices=sorted(TEST_CASES))
    parser.add_argument("--fixture-root", type=Path, default=Path(".knowledge-test-tmp"))
    args = parser.parse_args(argv)
    for test_case in TEST_CASES.values():
        test_case.workspace = Path.cwd().resolve()
        test_case.fixture_root = args.fixture_root.resolve()
    selected = args.test_names or list(TEST_CASES)
    suite = unittest.TestSuite(
        unittest.defaultTestLoader.loadTestsFromTestCase(TEST_CASES[name])
        for name in selected
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() and not result.skipped else 1


if __name__ == "__main__":
    raise SystemExit(main())
