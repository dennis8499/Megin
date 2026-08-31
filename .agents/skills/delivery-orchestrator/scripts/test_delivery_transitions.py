#!/usr/bin/env python3
"""DeliveryTransitionTests isolated contract suite."""

import os
import subprocess
import tempfile
from unittest import mock

from _delivery_test_support import *  # noqa: F403
import _delivery_record as delivery_record


def persist_bug_assessment(
    delivery: Path,
    bug_id: str = "bug-sample-failure",
    *,
    relation: str = "intake",
    work_id: str | None = None,
    disposition: str = "delivery",
    sensitive: bool = False,
    embedded_secret: str | None = None,
) -> tuple[str, str, str, str]:
    root = delivery / "docs" / "bugs" / bug_id
    root.mkdir(parents=True)
    markdown = root / "assessment-1.md"
    markdown.write_text("# Redacted BUG assessment\n", encoding="utf-8", newline="\n")
    markdown_relative = f"docs/bugs/{bug_id}/assessment-1.md"
    assessment_relative = f"docs/bugs/{bug_id}/assessment-1.json"
    assessment = {
        "schema": "bug-assessment/v1",
        "bug_id": bug_id,
        "revision": 1,
        "markdown": {"path": markdown_relative, "sha256": digest(markdown)},
        "source": {
            "relation": relation,
            "work_id": work_id,
            "reported_by": "user",
            "evidence_refs": ["conversation:bug-report"],
        },
        "observed_behavior": (
            f"The public result exposed {embedded_secret}."
            if embedded_secret is not None
            else "The public result is incorrect."
        ),
        "expected_behavior": "The public result matches the approved contract.",
        "impact": "The primary journey cannot complete.",
        "verdict": "confirmed",
        "severity": "critical",
        "reproduction": {
            "status": "reproduced",
            "symptom_oracle": "expected and actual differ",
            "steps": ["run the public fixture"],
            "sample": "three of three controlled runs",
            "command_refs": ["host-temp:commands/repro"],
            "evidence_refs": ["host-temp:outputs/repro"],
        },
        "root_cause": {
            "status": "confirmed",
            "confidence": "high",
            "summary": "A controlled pre/post probe identifies the first invariant violation.",
            "evidence_refs": ["host-temp:traces/root-cause"],
        },
        "hypotheses": [],
        "active_hypothesis_id": None,
        "risk": {
            "security_privacy_or_data_risk": sensitive,
            "redacted_summary": (
                "Credential-like evidence is stored outside the repository."
                if sensitive
                else None
            ),
            "secure_evidence_refs": ["vault:bug-case-123"] if sensitive else [],
            "human_reviewer": "Security owner Alice" if sensitive else None,
        },
        "disposition": disposition,
        "evidence_refs": ["host-temp:assessment/index"],
        "next_action": "Approve Requirements and plan the smallest root-cause fix.",
        "created_at": "2026-08-30T00:00:00+08:00",
    }
    sidecar = root / "assessment-1.json"
    sidecar.write_text(
        json.dumps(assessment, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return assessment_relative, digest(sidecar), markdown_relative, digest(markdown)


class DeliveryTransitionTests(DeliveryFixture):
    def test_blocked_recovery_must_resume_the_same_phase(self) -> None:
        primary = self.make_repo()
        delivery = Path(self.start(primary, "blocked-work")["worktree"])
        self.transition(delivery, "blocked-work", "requirements", "active", "requirements_started")
        self.transition(delivery, "blocked-work", "requirements", "blocked", "requirements_blocked")
        self.assert_error(
            "ILLEGAL_TRANSITION",
            lambda: self.transition(delivery, "blocked-work", "planning", "active", "wrong_phase_resume"),
        )
        resumed = self.transition(
            delivery,
            "blocked-work",
            "requirements",
            "active",
            "requirements_unblocked",
        )
        self.assertEqual("requirements", resumed["phase"])
        self.assertEqual("active", resumed["status"])
        record = self.record(delivery, "blocked-work")
        self.assertEqual([], workspace.validate_record(record))


    def test_two_approval_gates_loops_complete_and_freeze(self) -> None:
        primary = self.make_repo()
        started = self.start(primary, "approval-work")
        delivery = Path(started["worktree"])
        self.enter_requirements(delivery, "approval-work")

        self.assert_error(
            "MISSING_GATE",
            lambda: self.transition(delivery, "approval-work", "planning", "active", "gate_skipped"),
        )
        requirements_path, requirements_sha = self.approve_requirements(delivery, "approval-work")

        self.assert_error(
            "MISSING_GATE",
            lambda: self.transition(delivery, "approval-work", "implementation", "active", "third_prompt_forbidden"),
        )
        handoff_path, handoff_payload = self.approve_plan(
            delivery,
            "approval-work",
            requirements_path,
            requirements_sha,
        )
        after_plan = self.record(delivery, "approval-work")
        self.assertEqual("implementation", after_plan["phase"])
        self.assertEqual(handoff_path, after_plan["plans"]["current_handoff_path"])

        run_id = "a" * 64
        self.transition(
            delivery,
            "approval-work",
            "implementation",
            "active",
            "implementation_started",
            implementation_run_id=run_id,
            implementation_ledger_ref="implementation:run-a",
            implementation_status="Active",
        )
        self.transition(
            delivery,
            "approval-work",
            "planning",
            "active",
            "implementation_reapproval",
            implementation_run_id=run_id,
            implementation_ledger_ref="implementation:run-a",
            implementation_status="Awaiting upstream reapproval",
        )
        self.assert_error(
            "ARTIFACT_ALREADY_APPROVED",
            lambda: self.transition(
                delivery,
                "approval-work",
                "implementation",
                "active",
                "old_plan_cannot_be_reapproved",
                handoff_path=handoff_path,
                candidate_revision="candidate-1",
                payload_sha256=handoff_payload,
                plan_approval_refs=["conversation:plan-1"],
            ),
        )
        self.transition(delivery, "approval-work", "requirements", "active", "planning_gap")
        self.transition(delivery, "approval-work", "requirements", "awaiting_user", "requirements_2_candidate")

        self.assert_error(
            "ARTIFACT_ALREADY_APPROVED",
            lambda: self.transition(
                delivery,
                "approval-work",
                "planning",
                "active",
                "old_requirements_cannot_be_reapproved",
                requirements_path=requirements_path,
                requirements_sha256=requirements_sha,
                requirements_approval_refs=["conversation:req-1"],
            ),
        )

        invalid_path = delivery / "docs" / "work" / "approval-work" / "requirements-3.md"
        invalid_path.write_text("wrong suffix\n", encoding="utf-8")
        self.assert_error(
            "INVALID_REVISION",
            lambda: self.transition(
                delivery,
                "approval-work",
                "planning",
                "active",
                "requirements_wrong_suffix",
                requirements_path="docs/work/approval-work/requirements-3.md",
                requirements_sha256=digest(invalid_path),
                requirements_approval_refs=["conversation:req-3"],
            ),
        )
        requirements_2_path, requirements_2_sha = self.approve_requirements(delivery, "approval-work", 2)
        self.approve_plan(delivery, "approval-work", requirements_2_path, requirements_2_sha, 2)

        new_run_id = hashlib.sha256(f"{self.root}:approval-work".encode("utf-8")).hexdigest()
        ledger_ref, review_ref, snapshot_ref = self.persist_complete_implementation(
            delivery,
            "approval-work",
            new_run_id,
        )
        completed = self.transition(
            delivery,
            "approval-work",
            "complete",
            "complete",
            "delivery_completed",
            implementation_run_id=new_run_id,
            implementation_ledger_ref=ledger_ref,
            implementation_status="Complete",
            evidence_refs=[ledger_ref, review_ref, snapshot_ref, "evidence/delivery_completed.json"],
        )
        self.assertEqual("complete", completed["status"])
        record = self.record(delivery, "approval-work")
        self.assertEqual(2, len(record["requirements"]["revisions"]))
        self.assertEqual(2, len(record["plans"]["revisions"]))
        self.assertEqual([], workspace.validate_record(record))
        self.assert_error(
            "COMPLETE_FROZEN",
            lambda: self.transition(delivery, "approval-work", "complete", "complete", "repeat_complete"),
        )
        self.assert_error("COMPLETE_FROZEN", lambda: self.start(primary, "approval-work", generation=2))


class DeliveryBugOverlayTests(DeliveryFixture):
    def start_bug(self, primary: Path, work_id: str = "bug-delivery-work") -> Path:
        started = workspace.start_workspace(
            primary,
            work_id,
            REQUEST_SHA,
            root=self.registry,
            work_kind="bug",
            bug_id="bug-sample-failure",
        )
        return Path(started["worktree"])

    def test_legacy_standard_record_stays_valid_without_bug_fields(self) -> None:
        primary = self.make_repo()
        delivery = Path(self.start(primary, "legacy-standard-work")["worktree"])
        record = self.record(delivery, "legacy-standard-work")
        self.assertNotIn("work_kind", record)
        self.assertNotIn("bugs", record)
        self.assertEqual([], workspace.validate_record(record))

    def test_public_cli_exposes_named_bug_transition_contracts(self) -> None:
        args = workspace._parser().parse_args(
            [
                "transition",
                "--repo", ".",
                "--work-id", "sample-work",
                "--phase", "implementation",
                "--status", "active",
                "--event", "bug_evidence",
                "--evidence-ref", "evidence/bug.json",
                "--deferred-bug-id", "bug-sample-failure",
                "--deferred-bug-relation", "unrelated",
                "--deferred-bug-status", "pending",
                "--deferred-bug-evidence-ref", "vault:bug-case-123",
                "--deferred-bug-sensitive",
                "--deferred-bug-redacted-summary", "Credential-like evidence is stored outside the repository.",
                "--deferred-bug-human-reviewer", "Security owner Alice",
                "--bug-verification-path", "docs/bugs/bug-sample-failure/verifications/sample-work.json",
                "--bug-verification-sha256", "a" * 64,
                "--bug-verification-result", "partial",
                "--known-secret-env", "BUG_SECRET_VALUE",
            ]
        )
        self.assertEqual("unrelated", args.deferred_bug_relation)
        self.assertEqual(["vault:bug-case-123"], args.deferred_bug_evidence_ref)
        self.assertTrue(args.deferred_bug_sensitive)
        self.assertEqual("Security owner Alice", args.deferred_bug_human_reviewer)
        self.assertEqual("partial", args.bug_verification_result)
        self.assertEqual(["BUG_SECRET_VALUE"], args.known_secret_env)
        prior = os.environ.get("BUG_SECRET_VALUE")
        os.environ["BUG_SECRET_VALUE"] = "ultraviolet-harbor-9472"
        try:
            self.assertEqual(
                ("ultraviolet-harbor-9472",),
                workspace._known_secret_values_from_env(args.known_secret_env),
            )
        finally:
            if prior is None:
                os.environ.pop("BUG_SECRET_VALUE", None)
            else:
                os.environ["BUG_SECRET_VALUE"] = prior

    def test_primary_assessment_consumer_scans_in_memory_known_secret_values(self) -> None:
        primary = self.make_repo()
        delivery = self.start_bug(primary, "bug-secret-scan-work")
        self.transition(delivery, "bug-secret-scan-work", "requirements", "active", "requirements_started")
        self.transition(
            delivery,
            "bug-secret-scan-work",
            "requirements",
            "awaiting_user",
            "requirements_candidate",
        )
        requirements = delivery / "docs" / "work" / "bug-secret-scan-work" / "requirements.md"
        requirements.parent.mkdir(parents=True)
        requirements.write_text("# BUG requirements\n\nStatus: Ready\n", encoding="utf-8", newline="\n")
        secret = "ultraviolet-harbor-9472"
        assessment_path, assessment_sha, markdown_path, markdown_sha = persist_bug_assessment(
            delivery,
            embedded_secret=secret,
        )
        error = self.assert_error(
            "INVALID_BUG_ASSESSMENT",
            lambda: self.transition(
                delivery,
                "bug-secret-scan-work",
                "planning",
                "active",
                "secret_assessment_rejected",
                requirements_path="docs/work/bug-secret-scan-work/requirements.md",
                requirements_sha256=digest(requirements),
                requirements_approval_refs=["conversation:req-bug"],
                bug_assessment_id="bug-sample-failure",
                bug_assessment_path=assessment_path,
                bug_assessment_sha256=assessment_sha,
                bug_assessment_markdown_path=markdown_path,
                bug_assessment_markdown_sha256=markdown_sha,
                known_secret_values=[secret],
            ),
        )
        self.assertNotIn(secret, str(error))

        sidecar = delivery / Path(*assessment_path.split("/"))
        clean = json.loads(sidecar.read_text(encoding="utf-8"))
        clean["observed_behavior"] = "The public result is incorrect."
        canonical = json.dumps(clean, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        sidecar.write_bytes(
            canonical.replace(
                '"impact":',
                f'"impact":"{secret}","impact":',
                1,
            ).encode("utf-8")
        )
        duplicate_error = self.assert_error(
            "INVALID_BUG_ASSESSMENT",
            lambda: self.transition(
                delivery,
                "bug-secret-scan-work",
                "planning",
                "active",
                "duplicate_key_secret_assessment_rejected",
                requirements_path="docs/work/bug-secret-scan-work/requirements.md",
                requirements_sha256=digest(requirements),
                requirements_approval_refs=["conversation:req-bug"],
                bug_assessment_id="bug-sample-failure",
                bug_assessment_path=assessment_path,
                bug_assessment_sha256=digest(sidecar),
                bug_assessment_markdown_path=markdown_path,
                bug_assessment_markdown_sha256=markdown_sha,
                known_secret_values=[secret],
            ),
        )
        self.assertNotIn(secret, str(duplicate_error))
        record = self.record(delivery, "bug-secret-scan-work")
        self.assertEqual("requirements", record["phase"])
        self.assertEqual([], record["bugs"]["assessments"])

    def test_primary_assessment_rejects_directory_redirect_before_dereference(self) -> None:
        primary = self.make_repo()
        delivery = self.start_bug(primary, "bug-redirect-work")
        self.transition(delivery, "bug-redirect-work", "requirements", "active", "requirements_started")
        self.transition(
            delivery,
            "bug-redirect-work",
            "requirements",
            "awaiting_user",
            "requirements_candidate",
        )
        requirements = delivery / "docs" / "work" / "bug-redirect-work" / "requirements.md"
        requirements.parent.mkdir(parents=True)
        requirements.write_text("# BUG requirements\n\nStatus: Ready\n", encoding="utf-8", newline="\n")

        redirect_target = delivery / "redirect-target"
        redirect_target.mkdir()
        redirect = delivery / "docs" / "bugs"
        if os.name == "nt":
            created = subprocess.run(
                ["cmd", "/d", "/c", "mklink", "/J", str(redirect), str(redirect_target)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(0, created.returncode, created.stderr.decode("utf-8", "replace"))
        else:
            redirect.symlink_to(redirect_target, target_is_directory=True)
        try:
            assessment_path, assessment_sha, markdown_path, markdown_sha = persist_bug_assessment(delivery)
            assessment_file = delivery / Path(*assessment_path.split("/"))
            markdown_file = delivery / Path(*markdown_path.split("/"))
            guarded = {assessment_file, markdown_file}
            original_canonical_path = delivery_record.canonical_path
            original_is_file = Path.is_file
            original_read_bytes = Path.read_bytes

            def reject_canonical_path(path: Path | str) -> Path:
                if Path(path) in guarded:
                    raise AssertionError("redirected assessment was resolved")
                return original_canonical_path(path)

            def reject_is_file(path: Path) -> bool:
                if path in guarded:
                    raise AssertionError("redirected assessment was dereferenced by is_file")
                return original_is_file(path)

            def reject_read_bytes(path: Path) -> bytes:
                if path in guarded:
                    raise AssertionError("redirected assessment was read")
                return original_read_bytes(path)

            with (
                mock.patch.object(delivery_record, "canonical_path", side_effect=reject_canonical_path),
                mock.patch.object(Path, "is_file", reject_is_file),
                mock.patch.object(Path, "read_bytes", reject_read_bytes),
            ):
                self.assert_error(
                    "INVALID_BUG_ASSESSMENT",
                    lambda: self.transition(
                        delivery,
                        "bug-redirect-work",
                        "planning",
                        "active",
                        "redirected_assessment_rejected",
                        requirements_path="docs/work/bug-redirect-work/requirements.md",
                        requirements_sha256=digest(requirements),
                        requirements_approval_refs=["conversation:req-bug"],
                        bug_assessment_id="bug-sample-failure",
                        bug_assessment_path=assessment_path,
                        bug_assessment_sha256=assessment_sha,
                        bug_assessment_markdown_path=markdown_path,
                        bug_assessment_markdown_sha256=markdown_sha,
                    ),
                )
        finally:
            os.rmdir(redirect) if os.name == "nt" else redirect.unlink()

    def test_repo_file_rejects_redirect_swapped_after_precheck(self) -> None:
        primary = self.make_repo()
        delivery = Path(self.start(primary, "artifact-race-work")["worktree"])
        source_dir = delivery / "safe-source"
        source_dir.mkdir()
        artifact = source_dir / "artifact.txt"
        artifact.write_text("approved bytes\n", encoding="utf-8", newline="\n")
        expected = digest(artifact)
        target = delivery / "redirect-target"
        target.mkdir()
        (target / "artifact.txt").write_bytes(artifact.read_bytes())
        original_dir = delivery / "original-source"
        swapped = False

        def swap_after_precheck(path: Path, root: Path) -> bool:
            nonlocal swapped
            if not swapped and path == artifact:
                source_dir.rename(original_dir)
                if os.name == "nt":
                    created = subprocess.run(
                        ["cmd", "/d", "/c", "mklink", "/J", str(source_dir), str(target)],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        check=False,
                    )
                    self.assertEqual(0, created.returncode, created.stderr.decode("utf-8", "replace"))
                else:
                    source_dir.symlink_to(target, target_is_directory=True)
                swapped = True
            return False

        try:
            with mock.patch.object(
                delivery_record,
                "_has_reparse_component",
                side_effect=swap_after_precheck,
            ):
                with self.assertRaises(workspace.DeliveryError) as raised:
                    delivery_record._verify_repo_file(
                        self.record(delivery, "artifact-race-work"),
                        "safe-source/artifact.txt",
                        expected,
                    )
            self.assertEqual("INVALID_PATH", raised.exception.code)
            self.assertTrue(swapped)
        finally:
            if swapped:
                os.rmdir(source_dir) if os.name == "nt" else source_dir.unlink()
                original_dir.rename(source_dir)

    def test_generation_materialization_rejects_redirected_parent(self) -> None:
        with tempfile.TemporaryDirectory(prefix="delivery-materialize-redirect-") as temporary:
            destination = Path(temporary) / "generation"
            destination.mkdir()
            alternate = destination / "alternate"
            alternate.mkdir()
            redirect = destination / "docs"
            if os.name == "nt":
                created = subprocess.run(
                    ["cmd", "/d", "/c", "mklink", "/J", str(redirect), str(alternate)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                )
                self.assertEqual(0, created.returncode, created.stderr.decode("utf-8", "replace"))
            else:
                redirect.symlink_to(alternate, target_is_directory=True)
            value = b"approved bytes\n"
            try:
                with self.assertRaises(workspace.DeliveryError) as raised:
                    delivery_record._materialize_approved_upstream(
                        destination,
                        [
                            {
                                "path": "docs/artifact.txt",
                                "sha256": hashlib.sha256(value).hexdigest(),
                                "bytes": value,
                            }
                        ],
                    )
                self.assertEqual("INVALID_PATH", raised.exception.code)
                self.assertFalse((alternate / "artifact.txt").exists())
            finally:
                os.rmdir(redirect) if os.name == "nt" else redirect.unlink()

    def test_global_inbox_rolls_back_when_run_record_write_fails_and_retry_succeeds(self) -> None:
        primary = self.make_repo()
        delivery = Path(self.start(primary, "inbox-atomic-work")["worktree"])
        self.enter_requirements(delivery, "inbox-atomic-work")
        requirements_path, requirements_sha = self.approve_requirements(delivery, "inbox-atomic-work")
        self.approve_plan(delivery, "inbox-atomic-work", requirements_path, requirements_sha)
        pending = {
            "deferred_bug_id": "bug-unrelated-atomic-inbox",
            "deferred_bug_relation": "unrelated",
            "deferred_bug_status": "pending",
            "deferred_bug_evidence_refs": ["host-temp:bug/atomic-inbox"],
        }
        record_before = copy.deepcopy(self.record(delivery, "inbox-atomic-work"))
        inbox = (
            self.registry
            / "repos"
            / record_before["repo_id"]
            / "bug-inbox"
            / "bug-unrelated-atomic-inbox.json"
        )
        with mock.patch.object(
            delivery_record,
            "_atomic_write_json",
            side_effect=OSError("forced run-record write failure"),
        ):
            with self.assertRaisesRegex(OSError, "forced run-record write failure"):
                self.transition(
                    delivery,
                    "inbox-atomic-work",
                    "implementation",
                    "active",
                    "unrelated_bug_deferred_atomic",
                    **pending,
                )
        self.assertFalse(inbox.exists(), "failed transition must not leave an orphan inbox")
        self.assertEqual(record_before, self.record(delivery, "inbox-atomic-work"))

        self.transition(
            delivery,
            "inbox-atomic-work",
            "implementation",
            "active",
            "unrelated_bug_deferred_atomic",
            **pending,
        )
        self.assertTrue(inbox.is_file())

    def test_global_inbox_retry_adopts_only_a_matching_crash_orphan(self) -> None:
        primary = self.make_repo()
        delivery = Path(self.start(primary, "inbox-crash-recovery-work")["worktree"])
        self.enter_requirements(delivery, "inbox-crash-recovery-work")
        requirements_path, requirements_sha = self.approve_requirements(
            delivery,
            "inbox-crash-recovery-work",
        )
        self.approve_plan(
            delivery,
            "inbox-crash-recovery-work",
            requirements_path,
            requirements_sha,
        )
        bug_id = "bug-unrelated-crash-orphan"
        evidence_refs = ["host-temp:bug/crash-orphan"]
        orphan = delivery_record._create_global_bug_inbox(
            self.registry,
            self.record(delivery, "inbox-crash-recovery-work"),
            bug_id=bug_id,
            evidence_refs=evidence_refs,
            sensitive=False,
            redacted_summary=None,
            human_reviewer=None,
        )
        self.assertTrue(orphan[3])

        self.transition(
            delivery,
            "inbox-crash-recovery-work",
            "implementation",
            "active",
            "unrelated_bug_recovered_after_crash",
            deferred_bug_id=bug_id,
            deferred_bug_relation="unrelated",
            deferred_bug_status="pending",
            deferred_bug_evidence_refs=evidence_refs,
        )
        self.assertEqual(orphan[2], json.loads(orphan[1].read_text(encoding="utf-8")))
        deferred = self.record(delivery, "inbox-crash-recovery-work")["bugs"]["deferred"]
        self.assertEqual([bug_id], [item["bug_id"] for item in deferred])

        self.assert_error(
            "BUG_INBOX_EXISTS",
            lambda: self.transition(
                delivery,
                "inbox-crash-recovery-work",
                "implementation",
                "active",
                "unrelated_bug_duplicate_rejected",
                deferred_bug_id=bug_id,
                deferred_bug_relation="unrelated",
                deferred_bug_status="pending",
                deferred_bug_evidence_refs=evidence_refs,
            ),
        )

    def test_bug_requirements_gate_atomically_binds_valid_assessment(self) -> None:
        primary = self.make_repo()
        delivery = self.start_bug(primary)
        self.transition(delivery, "bug-delivery-work", "requirements", "active", "requirements_started")
        self.transition(delivery, "bug-delivery-work", "requirements", "awaiting_user", "requirements_candidate")
        requirements = delivery / "docs" / "work" / "bug-delivery-work" / "requirements.md"
        requirements.parent.mkdir(parents=True)
        requirements.write_text("# BUG requirements\n\nStatus: Ready\n", encoding="utf-8", newline="\n")

        common = {
            "requirements_path": "docs/work/bug-delivery-work/requirements.md",
            "requirements_sha256": digest(requirements),
            "requirements_approval_refs": ["conversation:req-bug"],
        }
        self.assert_error(
            "MISSING_BUG_ASSESSMENT",
            lambda: self.transition(
                delivery,
                "bug-delivery-work",
                "planning",
                "active",
                "bug_assessment_missing",
                **common,
            ),
        )

        assessment_path, assessment_sha, markdown_path, markdown_sha = persist_bug_assessment(delivery)
        bug_fields = {
            "bug_assessment_id": "bug-sample-failure",
            "bug_assessment_path": assessment_path,
            "bug_assessment_sha256": assessment_sha,
            "bug_assessment_markdown_path": markdown_path,
            "bug_assessment_markdown_sha256": markdown_sha,
        }
        wrong = dict(bug_fields)
        wrong["bug_assessment_sha256"] = "f" * 64
        self.assert_error(
            "INVALID_BUG_ASSESSMENT",
            lambda: self.transition(
                delivery,
                "bug-delivery-work",
                "planning",
                "active",
                "bug_assessment_wrong_hash",
                **common,
                **wrong,
            ),
        )

        result = self.transition(
            delivery,
            "bug-delivery-work",
            "planning",
            "active",
            "bug_requirements_approved",
            **common,
            **bug_fields,
        )
        self.assertEqual("planning", result["phase"])
        record = self.record(delivery, "bug-delivery-work")
        self.assertEqual("bug", record["work_kind"])
        self.assertEqual("bug-sample-failure", record["bugs"]["primary_bug_id"])
        self.assertEqual(assessment_path, record["bugs"]["assessments"][0]["path"])
        self.assertEqual(assessment_sha, record["bugs"]["assessments"][0]["sha256"])
        self.assertEqual([], workspace.validate_record(record))

    def test_deferred_bug_materializes_and_global_inbox_is_create_only(self) -> None:
        primary = self.make_repo()
        delivery = Path(self.start(primary, "discovered-bug-work")["worktree"])
        self.enter_requirements(delivery, "discovered-bug-work")
        requirements_path, requirements_sha = self.approve_requirements(delivery, "discovered-bug-work")
        self.approve_plan(delivery, "discovered-bug-work", requirements_path, requirements_sha)

        pending = {
            "deferred_bug_id": "bug-unrelated-cache-drift",
            "deferred_bug_relation": "unrelated",
            "deferred_bug_status": "pending",
            "deferred_bug_evidence_refs": ["vault:bug-case-123"],
            "deferred_bug_sensitive": True,
            "deferred_bug_redacted_summary": "Credential-like evidence is stored outside the repository.",
            "deferred_bug_human_reviewer": "Security owner Alice",
        }
        missing_reviewer = dict(pending)
        missing_reviewer["deferred_bug_human_reviewer"] = None
        self.assert_error(
            "INVALID_DEFERRED_BUG",
            lambda: self.transition(
                delivery,
                "discovered-bug-work",
                "implementation",
                "active",
                "sensitive_bug_missing_owner",
                **missing_reviewer,
            ),
        )
        self.transition(
            delivery,
            "discovered-bug-work",
            "implementation",
            "active",
            "unrelated_bug_deferred",
            **pending,
        )
        record = self.record(delivery, "discovered-bug-work")
        self.assertIsNone(record["bugs"]["primary_bug_id"])
        self.assertEqual("pending", record["bugs"]["deferred"][0]["status"])
        inbox = (
            self.registry
            / "repos"
            / record["repo_id"]
            / "bug-inbox"
            / "bug-unrelated-cache-drift.json"
        )
        self.assertTrue(inbox.is_file())
        inbox_payload = json.loads(inbox.read_text(encoding="utf-8"))
        self.assertEqual(
            {
                "sensitive": True,
                "redacted_summary": "Credential-like evidence is stored outside the repository.",
                "human_reviewer": "Security owner Alice",
            },
            inbox_payload["risk"],
        )
        self.assertEqual(["vault:bug-case-123"], inbox_payload["redacted_evidence_refs"])
        before = inbox.read_bytes()

        assessment_path, assessment_sha, markdown_path, markdown_sha = persist_bug_assessment(
            delivery,
            "bug-unrelated-cache-drift",
            relation="unrelated",
            work_id="discovered-bug-work",
            disposition="deferred-inbox",
            sensitive=True,
        )
        self.transition(
            delivery,
            "discovered-bug-work",
            "implementation",
            "active",
            "unrelated_bug_materialized",
            deferred_bug_id="bug-unrelated-cache-drift",
            deferred_bug_relation="unrelated",
            deferred_bug_status="materialized",
            deferred_bug_evidence_refs=["vault:bug-case-123"],
            deferred_bug_sensitive=True,
            deferred_bug_redacted_summary="Credential-like evidence is stored outside the repository.",
            deferred_bug_human_reviewer="Security owner Alice",
            deferred_bug_assessment_path=assessment_path,
            deferred_bug_assessment_sha256=assessment_sha,
            deferred_bug_assessment_markdown_path=markdown_path,
            deferred_bug_assessment_markdown_sha256=markdown_sha,
        )
        record = self.record(delivery, "discovered-bug-work")
        self.assertEqual(["pending", "materialized"], [item["status"] for item in record["bugs"]["deferred"]])
        self.assertEqual(before, inbox.read_bytes(), "materialization must not overwrite the global inbox entry")
        self.assertEqual([], workspace.validate_record(record))

        self.assert_error(
            "BUG_INBOX_EXISTS",
            lambda: self.transition(
                delivery,
                "discovered-bug-work",
                "implementation",
                "active",
                "duplicate_inbox_write",
                **pending,
            ),
        )
        regenerated = workspace.start_workspace(
            primary,
            "discovered-bug-work",
            REQUEST_SHA,
            root=self.registry,
            generation=2,
        )
        generation_two = Path(regenerated["worktree"])
        self.assertEqual(
            (delivery / Path(*assessment_path.split("/"))).read_bytes(),
            (generation_two / Path(*assessment_path.split("/"))).read_bytes(),
        )
        self.assertEqual(
            (delivery / Path(*markdown_path.split("/"))).read_bytes(),
            (generation_two / Path(*markdown_path.split("/"))).read_bytes(),
        )

    def test_affecting_bug_requires_planning_reapproval(self) -> None:
        primary = self.make_repo()
        delivery = Path(self.start(primary, "affecting-bug-work")["worktree"])
        self.enter_requirements(delivery, "affecting-bug-work")
        requirements_path, requirements_sha = self.approve_requirements(delivery, "affecting-bug-work")
        self.approve_plan(delivery, "affecting-bug-work", requirements_path, requirements_sha)
        run_id = "d" * 64
        self.transition(
            delivery,
            "affecting-bug-work",
            "implementation",
            "active",
            "implementation_started",
            implementation_run_id=run_id,
            implementation_ledger_ref="implementation:run-d",
            implementation_status="Active",
        )
        fields = {
            "deferred_bug_id": "bug-contract-gap",
            "deferred_bug_relation": "affecting-current-work",
            "deferred_bug_status": "pending",
            "deferred_bug_evidence_refs": ["host-temp:bugs/contract-gap/redacted"],
        }
        self.assert_error(
            "BUG_REQUIRES_REAPPROVAL",
            lambda: self.transition(
                delivery,
                "affecting-bug-work",
                "implementation",
                "active",
                "invalid_inline_fix",
                **fields,
            ),
        )
        result = self.transition(
            delivery,
            "affecting-bug-work",
            "planning",
            "active",
            "bug_requires_reapproval",
            implementation_run_id=run_id,
            implementation_ledger_ref="implementation:run-d",
            implementation_status="Awaiting upstream reapproval",
            **fields,
        )
        self.assertEqual("planning", result["phase"])
        self.assertIsNone(self.record(delivery, "affecting-bug-work")["plans"]["current_handoff_path"])

    def test_bug_complete_requires_a_valid_nonfailed_verification_record(self) -> None:
        primary = self.make_repo()
        delivery = self.start_bug(primary, "bug-verification-work")
        self.enter_requirements(delivery, "bug-verification-work")
        requirements = delivery / "docs" / "work" / "bug-verification-work" / "requirements.md"
        requirements.parent.mkdir(parents=True)
        requirements.write_text("# BUG requirements\n\nStatus: Ready\n", encoding="utf-8", newline="\n")
        assessment_path, assessment_sha, markdown_path, markdown_sha = persist_bug_assessment(delivery)
        self.transition(
            delivery,
            "bug-verification-work",
            "planning",
            "active",
            "bug_requirements_approved",
            requirements_path="docs/work/bug-verification-work/requirements.md",
            requirements_sha256=digest(requirements),
            requirements_approval_refs=["conversation:req-bug"],
            bug_assessment_id="bug-sample-failure",
            bug_assessment_path=assessment_path,
            bug_assessment_sha256=assessment_sha,
            bug_assessment_markdown_path=markdown_path,
            bug_assessment_markdown_sha256=markdown_sha,
        )
        self.approve_plan(
            delivery,
            "bug-verification-work",
            "docs/work/bug-verification-work/requirements.md",
            digest(requirements),
        )
        run_id = hashlib.sha256(f"{self.root}:bug-verification".encode("utf-8")).hexdigest()
        ledger_ref, review_ref, snapshot_ref = self.persist_complete_implementation(
            delivery,
            "bug-verification-work",
            run_id,
        )
        verification_relative = "docs/bugs/bug-sample-failure/verifications/bug-verification-work.json"
        verification_path = delivery / Path(*verification_relative.split("/"))
        verified_bytes = verification_path.read_bytes()

        complete_fields = {
            "implementation_run_id": run_id,
            "implementation_ledger_ref": ledger_ref,
            "implementation_status": "Complete",
            "evidence_refs": [ledger_ref, review_ref, snapshot_ref, verification_relative],
        }
        self.assert_error(
            "INVALID_BUG_VERIFICATION",
            lambda: self.transition(
                delivery,
                "bug-verification-work",
                "implementation",
                "active",
                "early_bug_verification_binding",
                bug_verification_path=verification_relative,
                bug_verification_sha256=digest(verification_path),
                bug_verification_result="verified",
                **complete_fields,
            ),
        )
        self.assertIsNone(self.record(delivery, "bug-verification-work")["bugs"]["verification"])
        self.assert_error(
            "MISSING_BUG_VERIFICATION",
            lambda: self.transition(
                delivery,
                "bug-verification-work",
                "complete",
                "complete",
                "missing_bug_verification",
                **complete_fields,
            ),
        )
        failed = json.loads(verified_bytes.decode("utf-8"))
        failed["result"] = "failed"
        failed["original_reproduction"]["post_fix"]["status"] = "present"
        failed["full_verification"][0].update(
            {"outcome": "failed", "exit_code": 1, "failure_count": 1}
        )
        failed["summary"] = "The original symptom remains present."
        verification_path.write_text(
            json.dumps(failed, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        self.assert_error(
            "FAILED_BUG_VERIFICATION",
            lambda: self.transition(
                delivery,
                "bug-verification-work",
                "complete",
                "complete",
                "failed_bug_verification",
                bug_verification_path=verification_relative,
                bug_verification_sha256=digest(verification_path),
                bug_verification_result="failed",
                **complete_fields,
            ),
        )

        verification_path.write_bytes(verified_bytes)
        run_dir = Path(tempfile.gettempdir()).resolve() / "implementation-execution" / "runs" / run_id
        pre_fix_evidence = run_dir / "commands" / "bug-pre.txt"
        persisted_pre_fix = pre_fix_evidence.read_bytes()
        pre_fix_evidence.unlink()
        self.assert_error(
            "INVALID_BUG_VERIFICATION",
            lambda: self.transition(
                delivery,
                "bug-verification-work",
                "complete",
                "complete",
                "missing_physical_bug_evidence",
                bug_verification_path=verification_relative,
                bug_verification_sha256=digest(verification_path),
                bug_verification_result="verified",
                **complete_fields,
            ),
        )
        pre_fix_evidence.write_bytes(persisted_pre_fix)
        result = self.transition(
            delivery,
            "bug-verification-work",
            "complete",
            "complete",
            "verified_bug_complete",
            bug_verification_path=verification_relative,
            bug_verification_sha256=digest(verification_path),
            bug_verification_result="verified",
            **complete_fields,
        )
        self.assertEqual("complete", result["status"])
        record = self.record(delivery, "bug-verification-work")
        self.assertEqual("verified", record["bugs"]["verification"]["result"])
        self.assertEqual("verified", record["implementations"]["runs"][-1]["bug_verification_result"])

    def test_complete_rejects_unmaterialized_deferred_bug_evidence(self) -> None:
        primary = self.make_repo()
        delivery = Path(self.start(primary, "pending-bug-work")["worktree"])
        self.enter_requirements(delivery, "pending-bug-work")
        requirements_path, requirements_sha = self.approve_requirements(delivery, "pending-bug-work")
        self.approve_plan(delivery, "pending-bug-work", requirements_path, requirements_sha)
        self.transition(
            delivery,
            "pending-bug-work",
            "implementation",
            "active",
            "current_scope_bug_pending",
            deferred_bug_id="bug-current-scope-regression",
            deferred_bug_relation="current-scope",
            deferred_bug_status="pending",
            deferred_bug_evidence_refs=["host-temp:bugs/current-scope/redacted"],
        )
        run_id = hashlib.sha256(f"{self.root}:pending-bug".encode("utf-8")).hexdigest()
        ledger_ref, review_ref, snapshot_ref = self.persist_complete_implementation(
            delivery,
            "pending-bug-work",
            run_id,
        )
        self.assert_error(
            "PENDING_BUG_EVIDENCE",
            lambda: self.transition(
                delivery,
                "pending-bug-work",
                "complete",
                "complete",
                "pending_bug_complete",
                implementation_run_id=run_id,
                implementation_ledger_ref=ledger_ref,
                implementation_status="Complete",
                evidence_refs=[ledger_ref, review_ref, snapshot_ref],
            ),
        )

    def test_approved_partial_verification_can_complete_without_overclaim(self) -> None:
        primary = self.make_repo()
        delivery = self.start_bug(primary, "bug-partial-work")
        self.enter_requirements(delivery, "bug-partial-work")
        requirements = delivery / "docs" / "work" / "bug-partial-work" / "requirements.md"
        requirements.parent.mkdir(parents=True)
        requirements.write_text("# BUG requirements\n\nStatus: Ready\n", encoding="utf-8", newline="\n")
        assessment_path, assessment_sha, markdown_path, markdown_sha = persist_bug_assessment(delivery)
        self.transition(
            delivery,
            "bug-partial-work",
            "planning",
            "active",
            "bug_requirements_approved",
            requirements_path="docs/work/bug-partial-work/requirements.md",
            requirements_sha256=digest(requirements),
            requirements_approval_refs=["conversation:req-bug"],
            bug_assessment_id="bug-sample-failure",
            bug_assessment_path=assessment_path,
            bug_assessment_sha256=assessment_sha,
            bug_assessment_markdown_path=markdown_path,
            bug_assessment_markdown_sha256=markdown_sha,
        )
        self.approve_plan(
            delivery,
            "bug-partial-work",
            "docs/work/bug-partial-work/requirements.md",
            digest(requirements),
            bug_verification_target="partial",
        )
        run_id = hashlib.sha256(f"{self.root}:bug-partial".encode("utf-8")).hexdigest()
        ledger_ref, review_ref, snapshot_ref = self.persist_complete_implementation(
            delivery,
            "bug-partial-work",
            run_id,
        )
        verification_relative = "docs/bugs/bug-sample-failure/verifications/bug-partial-work.json"
        verification_path = delivery / Path(*verification_relative.split("/"))
        run_dir = Path(tempfile.gettempdir()).resolve() / "implementation-execution" / "runs" / run_id
        review_path = run_dir / "reviews" / "round-1" / "report.json"
        review = json.loads(review_path.read_text(encoding="utf-8"))
        honest_summary = review["summary"]
        review["summary"] = "BUG is verified fixed."
        review_path.write_text(
            json.dumps(review, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        transition_fields = {
            "implementation_run_id": run_id,
            "implementation_ledger_ref": ledger_ref,
            "implementation_status": "Complete",
            "bug_verification_path": verification_relative,
            "bug_verification_sha256": digest(verification_path),
            "bug_verification_result": "partial",
            "evidence_refs": [ledger_ref, review_ref, snapshot_ref, verification_relative],
        }
        self.assert_error(
            "MISSING_GATE",
            lambda: self.transition(
                delivery,
                "bug-partial-work",
                "complete",
                "complete",
                "partial_review_overclaim",
                **transition_fields,
            ),
        )
        review["summary"] = honest_summary
        review_path.write_text(
            json.dumps(review, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        secret = "ultraviolet-harbor-9472"
        verification_bytes = verification_path.read_bytes()
        verification = json.loads(verification_bytes.decode("utf-8"))
        canonical = json.dumps(
            verification,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        verification_path.write_bytes(
            canonical.replace(
                '"summary":',
                f'"summary":"{secret}","summary":',
                1,
            ).encode("utf-8")
        )
        duplicate_fields = dict(transition_fields)
        duplicate_fields["bug_verification_sha256"] = digest(verification_path)
        duplicate_error = self.assert_error(
            "INVALID_BUG_VERIFICATION",
            lambda: self.transition(
                delivery,
                "bug-partial-work",
                "complete",
                "complete",
                "partial_duplicate_key_secret_rejected",
                known_secret_values=[secret],
                **duplicate_fields,
            ),
        )
        self.assertNotIn(secret, str(duplicate_error))
        verification_path.write_bytes(verification_bytes)
        result = self.transition(
            delivery,
            "bug-partial-work",
            "complete",
            "complete",
            "partial_bug_complete",
            **transition_fields,
        )
        self.assertEqual("complete", result["status"])
        verification = json.loads(verification_path.read_text(encoding="utf-8"))
        self.assertEqual("partial", verification["result"])
        self.assertNotIn("verified", verification["summary"].lower())


class DeliveryTerminalContractTests(DeliveryFixture):
    def test_complete_rejects_logical_refs_without_persisted_ledger_and_review(self) -> None:
        primary = self.make_repo()
        delivery = Path(self.start(primary, "terminal-proof-work")["worktree"])
        self.enter_requirements(delivery, "terminal-proof-work")
        requirements_path, requirements_sha = self.approve_requirements(delivery, "terminal-proof-work")
        self.approve_plan(delivery, "terminal-proof-work", requirements_path, requirements_sha)
        run_id = hashlib.sha256(f"{self.root}:forged".encode("utf-8")).hexdigest()
        ledger_ref = f"implementation:runs/{run_id}/run.json"
        review_ref = "implementation:reviews/round-1/report.json"

        self.assert_error(
            "MISSING_GATE",
            lambda: self.transition(
                delivery,
                "terminal-proof-work",
                "complete",
                "complete",
                "forged_complete",
                implementation_run_id=run_id,
                implementation_ledger_ref=ledger_ref,
                implementation_status="Complete",
                evidence_refs=[ledger_ref, review_ref],
            ),
        )
        forged = copy.deepcopy(self.record(delivery, "terminal-proof-work"))
        forged["implementations"] = {
            "current_run_id": run_id,
            "runs": [{"run_id": run_id, "ledger_ref": ledger_ref, "status": "Complete"}],
        }
        workspace._append_event(
            forged,
            kind="forged_complete",
            phase="complete",
            status="complete",
            evidence_refs=[ledger_ref, review_ref],
        )
        errors = workspace.validate_record(forged)
        self.assertTrue(any("not persisted" in error for error in errors), errors)

    def test_complete_rejects_post_review_workspace_drift(self) -> None:
        primary = self.make_repo()
        delivery = Path(self.start(primary, "snapshot-drift-work")["worktree"])
        self.enter_requirements(delivery, "snapshot-drift-work")
        requirements_path, requirements_sha = self.approve_requirements(delivery, "snapshot-drift-work")
        self.approve_plan(delivery, "snapshot-drift-work", requirements_path, requirements_sha)
        run_id = hashlib.sha256(f"{self.root}:snapshot-drift".encode("utf-8")).hexdigest()
        ledger_ref, review_ref, snapshot_ref = self.persist_complete_implementation(
            delivery,
            "snapshot-drift-work",
            run_id,
        )
        (delivery / "post-review-product.txt").write_text(
            "unreviewed product bytes\n",
            encoding="utf-8",
            newline="\n",
        )
        self.assert_error(
            "MISSING_GATE",
            lambda: self.transition(
                delivery,
                "snapshot-drift-work",
                "complete",
                "complete",
                "drifted_complete",
                implementation_run_id=run_id,
                implementation_ledger_ref=ledger_ref,
                implementation_status="Complete",
                evidence_refs=[ledger_ref, review_ref, snapshot_ref],
            ),
        )
        self.assertEqual("implementation", self.record(delivery, "snapshot-drift-work")["phase"])

    def test_complete_rejects_terminal_ready_and_wp_continuity_drift(self) -> None:
        primary = self.make_repo()
        delivery = Path(self.start(primary, "terminal-continuity-work")["worktree"])
        self.enter_requirements(delivery, "terminal-continuity-work")
        requirements_path, requirements_sha = self.approve_requirements(
            delivery,
            "terminal-continuity-work",
        )
        handoff_path, _ = self.approve_plan(
            delivery,
            "terminal-continuity-work",
            requirements_path,
            requirements_sha,
        )
        run_id = hashlib.sha256(f"{self.root}:terminal-continuity".encode("utf-8")).hexdigest()
        ledger_ref, review_ref, snapshot_ref = self.persist_complete_implementation(
            delivery,
            "terminal-continuity-work",
            run_id,
        )
        run_dir = Path(tempfile.gettempdir()).resolve() / "implementation-execution" / "runs" / run_id
        handoff = json.loads(
            (delivery / Path(*handoff_path.split("/"))).read_text(encoding="utf-8")
        )

        source_manifest = run_dir / "source-manifest.json"
        source_manifest.write_text("[]\n", encoding="utf-8", newline="\n")
        self.assert_error(
            "MISSING_GATE",
            lambda: self.transition(
                delivery,
                "terminal-continuity-work",
                "complete",
                "complete",
                "source_manifest_drift",
                implementation_run_id=run_id,
                implementation_ledger_ref=ledger_ref,
                implementation_status="Complete",
                evidence_refs=[ledger_ref, review_ref, snapshot_ref],
            ),
        )
        source_manifest.write_text(
            json.dumps(handoff["sources"], ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )

        wp_ledger = run_dir / "wp-ledger.json"
        wp_ledger.write_text('{"WP-001":"Pending"}\n', encoding="utf-8", newline="\n")
        self.assert_error(
            "MISSING_GATE",
            lambda: self.transition(
                delivery,
                "terminal-continuity-work",
                "complete",
                "complete",
                "wp_ledger_drift",
                implementation_run_id=run_id,
                implementation_ledger_ref=ledger_ref,
                implementation_status="Complete",
                evidence_refs=[ledger_ref, review_ref, snapshot_ref],
            ),
        )
        wp_ledger.write_text(
            json.dumps(
                {wp["wp_id"]: "Verified" for wp in handoff["work_packages"]},
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )

        capability_path = run_dir / "evidence/capability.json"
        capability_text = capability_path.read_text(encoding="utf-8")
        capability_path.write_text("evidence\n", encoding="utf-8", newline="\n")
        self.assert_error(
            "MISSING_GATE",
            lambda: self.transition(
                delivery,
                "terminal-continuity-work",
                "complete",
                "complete",
                "capability_shape_drift",
                implementation_run_id=run_id,
                implementation_ledger_ref=ledger_ref,
                implementation_status="Complete",
                evidence_refs=[ledger_ref, review_ref, snapshot_ref],
            ),
        )
        capability_path.write_text(capability_text, encoding="utf-8", newline="\n")

        integrity_path = run_dir / "integrity/global-1-ready-source.json"
        integrity_text = integrity_path.read_text(encoding="utf-8")
        integrity_path.write_text("{}\n", encoding="utf-8", newline="\n")
        self.assert_error(
            "MISSING_GATE",
            lambda: self.transition(
                delivery,
                "terminal-continuity-work",
                "complete",
                "complete",
                "integrity_shape_drift",
                implementation_run_id=run_id,
                implementation_ledger_ref=ledger_ref,
                implementation_status="Complete",
                evidence_refs=[ledger_ref, review_ref, snapshot_ref],
            ),
        )
        integrity_path.write_text(integrity_text, encoding="utf-8", newline="\n")


    def test_handoff_binding_rejects_wrong_spec_hash_and_approval(self) -> None:
        primary = self.make_repo()
        delivery = Path(self.start(primary, "binding-work")["worktree"])
        self.enter_requirements(delivery, "binding-work")
        requirements_path, requirements_sha = self.approve_requirements(delivery, "binding-work")
        self.transition(delivery, "binding-work", "planning", "awaiting_user", "plan_candidate")
        handoff_path, payload, evidence = self.ready_handoff(
            delivery,
            "binding-work",
            requirements_path,
            "f" * 64,
        )
        self.assert_error(
            "INVALID_HANDOFF",
            lambda: self.transition(
                delivery,
                "binding-work",
                "implementation",
                "active",
                "bad_spec_hash",
                handoff_path=handoff_path,
                candidate_revision="candidate-1",
                payload_sha256=payload,
                plan_approval_refs=[evidence],
            ),
        )

        handoff_path, payload, evidence = self.ready_handoff(
            delivery,
            "binding-work",
            requirements_path,
            requirements_sha,
        )
        self.assert_error(
            "INVALID_HANDOFF",
            lambda: self.transition(
                delivery,
                "binding-work",
                "implementation",
                "active",
                "bad_plan_evidence",
                handoff_path=handoff_path,
                candidate_revision="candidate-1",
                payload_sha256=payload,
                plan_approval_refs=["conversation:different"],
            ),
        )


    def test_ready_handoff_requires_full_contract_and_exactly_one_total_spec_source(self) -> None:
        primary = self.make_repo()
        delivery = Path(self.start(primary, "strict-ready-work")["worktree"])
        self.enter_requirements(delivery, "strict-ready-work")
        requirements_path, requirements_sha = self.approve_requirements(delivery, "strict-ready-work")
        self.transition(delivery, "strict-ready-work", "planning", "awaiting_user", "strict_plan_candidate")
        handoff_path, payload, evidence = self.ready_handoff(
            delivery,
            "strict-ready-work",
            requirements_path,
            requirements_sha,
        )
        handoff_file = delivery / Path(*handoff_path.split("/"))
        valid = json.loads(handoff_file.read_text(encoding="utf-8"))
        validator = workspace._contract_validator()
        self.assertEqual([], validator.validate_instance(valid, workspace._ready_plan_schema()))
        self.assertEqual([], validator.validate_ready_cross_references(valid))

        invalid_schema = copy.deepcopy(valid)
        invalid_schema["unexpected_secret_field"] = "do-not-reflect-this-value"
        invalid_schema["candidate"]["payload_sha256"] = workspace._ready_payload_sha256(invalid_schema)
        handoff_file.write_text(
            json.dumps(invalid_schema, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        error = self.assert_error(
            "INVALID_HANDOFF",
            lambda: self.transition(
                delivery,
                "strict-ready-work",
                "implementation",
                "active",
                "invalid_ready_schema",
                handoff_path=handoff_path,
                candidate_revision="candidate-1",
                payload_sha256=invalid_schema["candidate"]["payload_sha256"],
                plan_approval_refs=[evidence],
            ),
        )
        self.assertNotIn("do-not-reflect-this-value", str(error))

        extra_spec = copy.deepcopy(valid)
        extra_spec["sources"].append(
            {
                "source_id": "SRC-002",
                "kind": "spec",
                "location": "app.txt",
                "revision": "baseline",
                "sha256": digest(delivery / "app.txt"),
                "plan_refs": ["REQ-002"],
                "wp_refs": ["WP-001"],
            }
        )
        extra_spec["work_packages"][0]["source_refs"].append("SRC-002")
        extra_spec["candidate"]["payload_sha256"] = workspace._ready_payload_sha256(extra_spec)
        self.assertEqual([], validator.validate_instance(extra_spec, workspace._ready_plan_schema()))
        self.assertEqual([], validator.validate_ready_cross_references(extra_spec))
        handoff_file.write_text(
            json.dumps(extra_spec, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        self.assert_error(
            "INVALID_HANDOFF",
            lambda: self.transition(
                delivery,
                "strict-ready-work",
                "implementation",
                "active",
                "extra_spec_rejected",
                handoff_path=handoff_path,
                candidate_revision="candidate-1",
                payload_sha256=extra_spec["candidate"]["payload_sha256"],
                plan_approval_refs=[evidence],
            ),
        )


    def test_resume_and_generation_fail_closed_on_approved_artifact_drift(self) -> None:
        primary = self.make_repo()
        delivery = Path(self.start(primary, "drift-work")["worktree"])
        self.enter_requirements(delivery, "drift-work")
        requirements_path, requirements_sha = self.approve_requirements(delivery, "drift-work")
        self.approve_plan(delivery, "drift-work", requirements_path, requirements_sha)

        requirements_file = delivery / Path(*requirements_path.split("/"))
        requirements_file.write_text("drifted requirements\n", encoding="utf-8")
        self.assert_error(
            "ARTIFACT_DRIFT",
            lambda: workspace.locate_workspace(primary, root=self.registry, work_id="drift-work"),
        )
        self.assert_error("ARTIFACT_DRIFT", lambda: self.start(primary, "drift-work", generation=2))
        destination = primary.parent / f"{primary.name}.worktrees" / "drift-work-r2"
        self.assertFalse(destination.exists())
        branch = git(primary, "show-ref", "--verify", "refs/heads/delivery/drift-work-r2", check=False)
        self.assertNotEqual(0, branch.returncode)

    def test_generation_rejects_base_byte_mismatch_before_git_mutation(self) -> None:
        primary = self.make_repo()
        (primary / ".gitattributes").write_text("app.txt eol=crlf\n", encoding="utf-8", newline="\n")
        git(primary, "add", ".gitattributes")
        git(primary, "commit", "-m", "declare checkout eol")
        git(primary, "checkout-index", "-f", "--", "app.txt")
        delivery = Path(self.start(primary, "base-bytes-work")["worktree"])
        self.enter_requirements(delivery, "base-bytes-work")
        requirements_path, requirements_sha = self.approve_requirements(delivery, "base-bytes-work")
        self.transition(delivery, "base-bytes-work", "planning", "awaiting_user", "plan_candidate")
        handoff_path, _, evidence = self.ready_handoff(
            delivery,
            "base-bytes-work",
            requirements_path,
            requirements_sha,
        )
        handoff_file = delivery / Path(*handoff_path.split("/"))
        handoff = json.loads(handoff_file.read_text(encoding="utf-8"))
        handoff["sources"].append(
            {
                "source_id": "SRC-002",
                "kind": "project",
                "location": "app.txt",
                "revision": "recorded-base",
                "sha256": digest(delivery / "app.txt"),
                "plan_refs": ["REQ-002"],
                "wp_refs": ["WP-001"],
            }
        )
        handoff["work_packages"][0]["source_refs"].append("SRC-002")
        handoff["candidate"]["payload_sha256"] = workspace._ready_payload_sha256(handoff)
        handoff_file.write_text(
            json.dumps(handoff, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        self.transition(
            delivery,
            "base-bytes-work",
            "implementation",
            "active",
            "plan_approved",
            handoff_path=handoff_path,
            candidate_revision="candidate-1",
            payload_sha256=handoff["candidate"]["payload_sha256"],
            plan_approval_refs=[evidence],
        )
        base_bytes = git(primary, "show", "HEAD:app.txt").stdout
        self.assertNotEqual(hashlib.sha256(base_bytes).hexdigest(), digest(delivery / "app.txt"))
        before_worktrees = git(primary, "worktree", "list", "--porcelain").stdout
        self.assert_error(
            "SOURCE_NOT_MATERIALIZABLE",
            lambda: self.start(primary, "base-bytes-work", generation=2),
        )
        self.assertEqual(before_worktrees, git(primary, "worktree", "list", "--porcelain").stdout)
        destination = primary.parent / f"{primary.name}.worktrees" / "base-bytes-work-r2"
        self.assertFalse(destination.exists())
        branch = git(primary, "show-ref", "--verify", "refs/heads/delivery/base-bytes-work-r2", check=False)
        self.assertNotEqual(0, branch.returncode)
        self.assertEqual(1, self.record(primary, "base-bytes-work")["current_generation"])


    def test_unmaterialized_local_ready_source_is_rejected_before_implementation(self) -> None:
        primary = self.make_repo()
        delivery = Path(self.start(primary, "source-material-work")["worktree"])
        self.enter_requirements(delivery, "source-material-work")
        requirements_path, requirements_sha = self.approve_requirements(delivery, "source-material-work")
        self.transition(delivery, "source-material-work", "planning", "awaiting_user", "source_plan_candidate")
        handoff_path, _, evidence = self.ready_handoff(
            delivery,
            "source-material-work",
            requirements_path,
            requirements_sha,
        )
        local_source = delivery / "local-evidence.txt"
        local_source.write_text("untracked evidence\n", encoding="utf-8", newline="\n")
        handoff_file = delivery / Path(*handoff_path.split("/"))
        handoff = json.loads(handoff_file.read_text(encoding="utf-8"))
        handoff["sources"].append(
            {
                "source_id": "SRC-002",
                "kind": "project",
                "location": "local-evidence.txt",
                "revision": "working-copy",
                "sha256": digest(local_source),
                "plan_refs": ["REQ-002"],
                "wp_refs": ["WP-001"],
            }
        )
        handoff["work_packages"][0]["source_refs"].append("SRC-002")
        handoff["candidate"]["payload_sha256"] = workspace._ready_payload_sha256(handoff)
        handoff_file.write_text(
            json.dumps(handoff, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        validator = workspace._contract_validator()
        self.assertEqual([], validator.validate_instance(handoff, workspace._ready_plan_schema()))
        self.assertEqual([], validator.validate_ready_cross_references(handoff))
        self.assert_error(
            "SOURCE_NOT_MATERIALIZABLE",
            lambda: self.transition(
                delivery,
                "source-material-work",
                "implementation",
                "active",
                "unmaterialized_source_rejected",
                handoff_path=handoff_path,
                candidate_revision="candidate-1",
                payload_sha256=handoff["candidate"]["payload_sha256"],
                plan_approval_refs=[evidence],
            ),
        )
        record = self.record(delivery, "source-material-work")
        self.assertIsNone(record["plans"]["current_handoff_path"])
        self.assertEqual("planning", record["phase"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
