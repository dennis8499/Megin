#!/usr/bin/env python3
"""DeliveryTransitionTests isolated contract suite."""

import tempfile

from _delivery_test_support import *  # noqa: F403


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
