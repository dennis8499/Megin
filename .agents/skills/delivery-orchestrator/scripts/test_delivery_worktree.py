#!/usr/bin/env python3
"""DeliveryWorktreeTests isolated contract suite."""

from _delivery_test_support import *  # noqa: F403


class DeliveryWorktreeTests(DeliveryFixture):
    def test_work_id_validation_and_generation(self) -> None:
        self.assertEqual("valid-id", workspace.validate_work_id("valid-id"))
        for value in ("ab", "UPPER", "bad/id", "bad-", "bad--id", "con", "a" * 65):
            with self.subTest(value=value):
                self.assert_error("INVALID_WORK_ID", lambda value=value: workspace.validate_work_id(value))

        generated = workspace.generate_work_id("0" * 64, "1" * 40, REQUEST_SHA, "Fix OAuth refresh token")
        self.assertRegex(generated, r"^work-\d{8}-fix-oauth-refresh-token-[a-f0-9]{8}$")
        one_word = workspace.generate_work_id("0" * 64, "1" * 40, REQUEST_SHA, "cache")
        self.assertIn("-cache-work-", one_word)
        non_ascii = workspace.generate_work_id("0" * 64, "1" * 40, REQUEST_SHA, "修正登入")
        self.assertIn("-general-work-", non_ascii)


    def test_public_cli_returns_json_for_probe_start_locate_and_transition(self) -> None:
        primary = self.make_repo()

        def cli(*arguments: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
            return run(
                [sys.executable, "-X", "utf8", "-B", str(SCRIPT), *arguments],
                check=check,
            )

        probe_result = cli(
            "probe",
            "--repo",
            str(primary),
            "--topic",
            "cache repair",
            "--request-sha256",
            REQUEST_SHA,
        )
        probe = json.loads(probe_result.stdout)
        self.assertTrue(probe["strict_clean"])
        self.assertRegex(probe["suggested_work_id"], r"^work-\d{8}-cache-repair-[a-f0-9]{8}$")

        start_result = cli(
            "start",
            "--repo",
            str(primary),
            "--work-id",
            "cli-work",
            "--request-sha256",
            REQUEST_SHA,
            "--registry-root",
            str(self.registry),
        )
        started = json.loads(start_result.stdout)
        self.assertEqual("created", started["outcome"])

        transition_result = cli(
            "transition",
            "--repo",
            str(primary),
            "--work-id",
            "cli-work",
            "--phase",
            "requirements",
            "--status",
            "active",
            "--event",
            "requirements_started",
            "--evidence-ref",
            "evidence/cli.json",
            "--registry-root",
            str(self.registry),
        )
        self.assertEqual("requirements", json.loads(transition_result.stdout)["phase"])

        locate_result = cli(
            "locate",
            "--repo",
            str(primary),
            "--work-id",
            "cli-work",
            "--registry-root",
            str(self.registry),
        )
        self.assertEqual("located", json.loads(locate_result.stdout)["outcome"])

        (primary / "dirty.txt").write_text("dirty\n", encoding="utf-8")
        failure = cli(
            "start",
            "--repo",
            str(primary),
            "--work-id",
            "another-cli-work",
            "--request-sha256",
            REQUEST_SHA,
            "--registry-root",
            str(self.registry),
            check=False,
        )
        self.assertEqual(2, failure.returncode)
        self.assertEqual("DIRTY_PRIMARY", json.loads(failure.stderr)["error"])


    def test_clean_start_preserves_primary_and_dirty_resume(self) -> None:
        primary = self.make_repo()
        external_sentinel = self.root / "external-sentinel.bin"
        external_sentinel.write_bytes(b"external state must remain unchanged")
        sentinel_sha = digest(external_sentinel)
        before = primary_snapshot(primary)
        result = self.start(primary)
        delivery = Path(result["worktree"])

        self.assertEqual("created", result["outcome"])
        self.assertEqual("delivery/work-test-001", result["branch"])
        self.assertTrue(delivery.is_dir())
        self.assertEqual(before, primary_snapshot(primary))
        self.assertEqual(sentinel_sha, digest(external_sentinel))
        delivery_probe = workspace.probe_repository(delivery)
        self.assertFalse(delivery_probe["is_primary"])
        self.assertTrue(delivery_probe["strict_clean"])

        (primary / "user-untracked.txt").write_text("user bytes\n", encoding="utf-8")
        existing = self.start(primary)
        self.assertEqual("existing", existing["outcome"])
        located = workspace.locate_workspace(primary, root=self.registry, work_id="work-test-001")
        self.assertEqual(delivery.resolve(), Path(located["worktree"]).resolve())

        (delivery / "progress.txt").write_text("committed progress\n", encoding="utf-8")
        git(delivery, "add", "progress.txt")
        git(delivery, "commit", "-m", "progress")
        located_after_commit = workspace.locate_workspace(delivery, root=self.registry, work_id="work-test-001")
        self.assertEqual("located", located_after_commit["outcome"])


    def test_resume_selection_is_explicit_when_multiple_active(self) -> None:
        primary = self.make_repo()
        first = self.start(primary, "resume-one")
        second = self.start(primary, "resume-two")
        explicit = workspace.locate_workspace(primary, root=self.registry, work_id="resume-two")
        self.assertEqual(Path(second["worktree"]).resolve(), Path(explicit["worktree"]).resolve())
        error = self.assert_error(
            "AMBIGUOUS_WORK",
            lambda: workspace.locate_workspace(primary, root=self.registry),
        )
        self.assertEqual({"work_ids": ["resume-one", "resume-two"]}, error.details)
        from_linked = workspace.locate_workspace(first["worktree"], root=self.registry, work_id="resume-one")
        self.assertEqual("located", from_linked["outcome"])


    def test_revision_suffix_uses_smallest_available_without_overwrite(self) -> None:
        primary = self.make_repo()
        delivery = Path(self.start(primary, "collision-revision-work")["worktree"])
        self.enter_requirements(delivery, "collision-revision-work")
        artifact_root = delivery / "docs" / "work" / "collision-revision-work"
        artifact_root.mkdir(parents=True, exist_ok=True)
        requirements_sentinel = artifact_root / "requirements.md"
        requirements_sentinel.write_text("pre-existing user requirements\n", encoding="utf-8")
        requirements_path, requirements_sha = self.approve_requirements(
            delivery,
            "collision-revision-work",
            2,
        )
        self.assertEqual("pre-existing user requirements\n", requirements_sentinel.read_text(encoding="utf-8"))

        plan_sentinel = artifact_root / "plan"
        plan_sentinel.mkdir()
        (plan_sentinel / "user.txt").write_text("pre-existing plan bytes\n", encoding="utf-8")
        self.approve_plan(
            delivery,
            "collision-revision-work",
            requirements_path,
            requirements_sha,
            2,
        )
        self.assertEqual("pre-existing plan bytes\n", (plan_sentinel / "user.txt").read_text(encoding="utf-8"))
        record = self.record(delivery, "collision-revision-work")
        self.assertEqual("docs/work/collision-revision-work/requirements-2.md", record["requirements"]["current_path"])
        self.assertEqual("docs/work/collision-revision-work/plan-2/handoff.json", record["plans"]["current_handoff_path"])
        self.assertEqual([], workspace.validate_record(record))


    def test_new_generation_uses_clean_base_and_does_not_copy_product_diff(self) -> None:
        primary = self.make_repo()
        first = self.start(primary, "generation-work")
        delivery = Path(first["worktree"])
        self.enter_requirements(delivery, "generation-work")
        requirements_path, requirements_sha = self.approve_requirements(delivery, "generation-work")
        handoff_path, _ = self.approve_plan(
            delivery,
            "generation-work",
            requirements_path,
            requirements_sha,
        )
        (delivery / "product-only.txt").write_text("old product diff\n", encoding="utf-8")
        (primary / "user-untracked.txt").write_text("primary user bytes\n", encoding="utf-8")

        second = self.start(primary, "generation-work", generation=2)
        generation_two = Path(second["worktree"])
        self.assertEqual("delivery/generation-work-r2", second["branch"])
        self.assertFalse((generation_two / "product-only.txt").exists())
        self.assertEqual(requirements_sha, digest(generation_two / Path(*requirements_path.split("/"))))
        self.assertTrue((generation_two / Path(*handoff_path.split("/"))).is_file())
        self.assertEqual("primary user bytes\n", (primary / "user-untracked.txt").read_text(encoding="utf-8"))
        self.assertEqual(
            "located",
            workspace.locate_workspace(generation_two, root=self.registry, work_id="generation-work")["outcome"],
        )
        record = self.record(primary, "generation-work")
        self.assertEqual(2, record["current_generation"])
        self.assertEqual([1, 2], [item["generation"] for item in record["generations"]])
        self.assertEqual([], workspace.validate_record(record))


    def test_new_generation_rejects_unapproved_primary_head_change(self) -> None:
        primary = self.make_repo()
        self.start(primary, "base-drift-work")
        (primary / "app.txt").write_text("new primary commit\n", encoding="utf-8")
        git(primary, "add", "app.txt")
        git(primary, "commit", "-m", "advance primary")
        self.assert_error(
            "GENERATION_BASE_DRIFT",
            lambda: self.start(primary, "base-drift-work", generation=2),
        )
        self.assertFalse((primary.parent / f"{primary.name}.worktrees" / "base-drift-work-r2").exists())
        branch = git(primary, "show-ref", "--verify", "refs/heads/delivery/base-drift-work-r2", check=False)
        self.assertNotEqual(0, branch.returncode)


    def test_public_facade_keeps_cli_and_moves_private_authorities(self) -> None:
        for name in (
            "_delivery_runtime.py",
            "_delivery_git.py",
            "_delivery_record.py",
            "_delivery_authorization.py",
            "_delivery_doctor.py",
        ):
            self.assertTrue(SCRIPT.with_name(name).is_file(), name)
        parser = workspace._parser()
        subparsers = next(
            action for action in parser._actions if action.__class__.__name__ == "_SubParsersAction"
        )
        self.assertEqual(
            {"probe", "start", "locate", "authorize", "doctor", "transition"},
            set(subparsers.choices),
        )
        self.assertEqual("_delivery_git", workspace.probe_repository.__module__)
        self.assertEqual("_delivery_record", workspace.validate_record.__module__)
        self.assertEqual("_delivery_authorization", workspace.authorize_stage.__module__)
        self.assertEqual("_delivery_doctor", workspace.doctor_workspace.__module__)
        self.assertEqual("delivery_workspace", workspace.start_workspace.__module__)

    def test_authorize_stage_is_read_only_and_fail_closed(self) -> None:
        primary = self.make_repo("authorize-unit")
        delivery = Path(self.start(primary, "authorize-unit-work")["worktree"])
        self.transition(
            delivery,
            "authorize-unit-work",
            "requirements",
            "active",
            "requirements_started",
        )
        sentinel = self.root / "authorization-sentinel.bin"
        sentinel.write_bytes(b"must not change")
        before = {
            "primary": primary_snapshot(primary),
            "delivery": primary_snapshot(delivery),
            "registry": file_bytes(self.registry),
            "sentinel": digest(sentinel),
        }

        allowed = workspace.authorize_stage(
            delivery,
            "requirements",
            root=self.registry,
            work_id="authorize-unit-work",
        )
        wrong_phase = workspace.authorize_stage(
            delivery,
            "planning",
            root=self.registry,
            work_id="authorize-unit-work",
        )
        wrong_worktree = workspace.authorize_stage(
            primary,
            "requirements",
            root=self.registry,
            work_id="authorize-unit-work",
        )

        self.assertEqual("authorized", allowed["outcome"])
        self.assertEqual("delivery-run/v1", allowed["record"]["schema"])
        self.assertEqual("wrong_phase", wrong_phase["reason"])
        self.assertEqual("wrong_worktree", wrong_worktree["reason"])
        self.assertEqual(
            before,
            {
                "primary": primary_snapshot(primary),
                "delivery": primary_snapshot(delivery),
                "registry": file_bytes(self.registry),
                "sentinel": digest(sentinel),
            },
        )


class UnifiedEntryAuthorizationTests(DeliveryFixture):
    BDD_BINDINGS = {
        "BDD-001": "test_each_exact_active_phase_is_authorized",
        "BDD-002": "test_missing_wrong_phase_worktree_and_status_route_back_without_mutation",
        "BDD-003": "test_requirements_entry_is_routed_before_stage_writes",
        "BDD-004": "test_planning_entry_is_routed_and_plan_only_stays_read_only",
        "BDD-005": "test_implementation_requires_delivery_before_run_or_product_writes",
        "BDD-006": "test_ambiguous_runs_and_invalid_phase_fail_closed",
        "BDD-007": "test_delivery_owns_gated_automatic_flow_and_return_paths",
        "BDD-008": "test_read_only_and_governance_exceptions_do_not_gain_write_authority",
        "BDD-009": "test_legacy_bug_security_and_performance_contracts_remain_covered",
    }

    def _attempt_stage_writes(
        self,
        repo: Path,
        phase: str,
        *,
        work_id: str | None,
        repository_target: Path,
        host_target: Path,
    ) -> dict[str, object]:
        """Model the child contract: authorization is the first mutating branch."""

        authorization = workspace.authorize_stage(
            repo,
            phase,
            root=self.registry,
            work_id=work_id,
        )
        if authorization["outcome"] != "authorized":
            return authorization
        repository_target.parent.mkdir(parents=True, exist_ok=True)
        repository_target.write_bytes(f"{phase} repository artifact\n".encode("utf-8"))
        host_target.parent.mkdir(parents=True, exist_ok=True)
        host_target.write_bytes(f"{phase} host artifact\n".encode("utf-8"))
        return authorization

    def test_each_exact_active_phase_is_authorized(self) -> None:
        for expected_phase in ("requirements", "planning", "implementation"):
            with self.subTest(expected_phase=expected_phase):
                primary = self.make_repo(f"phase-{expected_phase}")
                work_id = f"phase-{expected_phase}-work"
                delivery = Path(self.start(primary, work_id)["worktree"])
                self.transition(
                    delivery,
                    work_id,
                    "requirements",
                    "active",
                    "requirements_started",
                )
                if expected_phase in {"planning", "implementation"}:
                    requirements_path, requirements_sha = self.approve_requirements(
                        delivery,
                        work_id,
                    )
                if expected_phase == "implementation":
                    self.approve_plan(
                        delivery,
                        work_id,
                        requirements_path,
                        requirements_sha,
                    )

                result = workspace.authorize_stage(
                    delivery,
                    expected_phase,
                    root=self.registry,
                    work_id=work_id,
                )
                self.assertEqual("delivery-stage-authorization/v1", result["schema"])
                self.assertEqual("authorized", result["outcome"])
                self.assertEqual(expected_phase, result["expected_phase"])
                self.assertEqual(expected_phase, result["record"]["phase"])
                self.assertEqual("active", result["record"]["status"])
                self.assertEqual(1, result["record"]["generation"])
                self.assertEqual(delivery.resolve(), Path(result["record"]["worktree"]).resolve())

    def test_missing_wrong_phase_worktree_and_status_route_back_without_mutation(self) -> None:
        primary = self.make_repo("routing-required")
        missing_before = primary_snapshot(primary)
        missing = workspace.authorize_stage(primary, "requirements", root=self.registry)
        self.assertEqual("routing_required", missing["outcome"])
        self.assertEqual("no_active_delivery", missing["reason"])
        self.assertEqual(missing_before, primary_snapshot(primary))
        self.assertFalse(self.registry.exists())

        delivery = Path(self.start(primary, "routing-required-work")["worktree"])
        self.transition(
            delivery,
            "routing-required-work",
            "requirements",
            "active",
            "requirements_started",
        )
        sentinel = self.root / "external-state.bin"
        sentinel.write_bytes(b"unchanged")
        before = {
            "primary": primary_snapshot(primary),
            "delivery": primary_snapshot(delivery),
            "registry": file_bytes(self.registry),
            "sentinel": digest(sentinel),
        }
        wrong_phase = workspace.authorize_stage(
            delivery,
            "planning",
            root=self.registry,
            work_id="routing-required-work",
        )
        wrong_worktree = workspace.authorize_stage(
            primary,
            "requirements",
            root=self.registry,
            work_id="routing-required-work",
        )
        self.assertEqual(before["registry"], file_bytes(self.registry))
        self.transition(
            delivery,
            "routing-required-work",
            "requirements",
            "awaiting_user",
            "requirements_candidate",
        )
        awaiting_before = file_bytes(self.registry)
        inactive = workspace.authorize_stage(
            delivery,
            "requirements",
            root=self.registry,
            work_id="routing-required-work",
        )

        self.assertEqual("wrong_phase", wrong_phase["reason"])
        self.assertEqual("wrong_worktree", wrong_worktree["reason"])
        self.assertEqual("inactive_status", inactive["reason"])
        self.assertEqual(awaiting_before, file_bytes(self.registry))
        self.assertEqual(digest(sentinel), before["sentinel"])
        self.assertEqual(before["primary"], primary_snapshot(primary))
        self.assertEqual(before["delivery"], primary_snapshot(delivery))

    def test_ambiguous_runs_and_invalid_phase_fail_closed(self) -> None:
        primary = self.make_repo("authorization-ambiguous")
        self.start(primary, "authorization-one")
        self.start(primary, "authorization-two")
        error = self.assert_error(
            "AMBIGUOUS_WORK",
            lambda: workspace.authorize_stage(primary, "requirements", root=self.registry),
        )
        self.assertEqual({"work_ids": ["authorization-one", "authorization-two"]}, error.details)
        self.assert_error(
            "INVALID_PHASE",
            lambda: workspace.authorize_stage(
                primary,
                "review",
                root=self.registry,
                work_id="authorization-one",
            ),
        )

    def test_explicit_work_id_cannot_alias_a_different_record_across_phases(self) -> None:
        for expected_phase in ("requirements", "planning", "implementation"):
            with self.subTest(expected_phase=expected_phase):
                primary = self.make_repo(f"identity-{expected_phase}")
                real_work_id = f"identity-{expected_phase}-real"
                alias_work_id = f"identity-{expected_phase}-alias"
                delivery = Path(self.start(primary, real_work_id)["worktree"])
                self.transition(
                    delivery,
                    real_work_id,
                    "requirements",
                    "active",
                    "requirements_started",
                )
                if expected_phase in {"planning", "implementation"}:
                    requirements_path, requirements_sha = self.approve_requirements(
                        delivery,
                        real_work_id,
                    )
                if expected_phase == "implementation":
                    self.approve_plan(
                        delivery,
                        real_work_id,
                        requirements_path,
                        requirements_sha,
                    )

                real = workspace.authorize_stage(
                    delivery,
                    expected_phase,
                    root=self.registry,
                    work_id=real_work_id,
                )
                real_record_path = Path(real["record"]["record_path"])
                alias_record_path = real_record_path.parent.parent / alias_work_id / "run.json"
                alias_record_path.parent.mkdir(parents=True)
                alias_record_path.write_bytes(real_record_path.read_bytes())

                repository_target = delivery / f"docs/work/{alias_work_id}/forbidden.txt"
                host_target = self.root / f"{alias_work_id}-forbidden.json"
                sentinel = self.root / f"{alias_work_id}-sentinel.bin"
                sentinel.write_bytes(b"identity mismatch must not write")
                before = {
                    "primary": primary_snapshot(primary),
                    "delivery": primary_snapshot(delivery),
                    "registry": file_bytes(self.registry),
                    "sentinel": digest(sentinel),
                }

                error = self.assert_error(
                    "INVALID_RECORD",
                    lambda: self._attempt_stage_writes(
                        delivery,
                        expected_phase,
                        work_id=alias_work_id,
                        repository_target=repository_target,
                        host_target=host_target,
                    ),
                )

                self.assertIn("work_id", str(error))
                self.assertFalse(repository_target.exists())
                self.assertFalse(host_target.exists())
                self.assertEqual(
                    before,
                    {
                        "primary": primary_snapshot(primary),
                        "delivery": primary_snapshot(delivery),
                        "registry": file_bytes(self.registry),
                        "sentinel": digest(sentinel),
                    },
                )

    def test_public_authorize_cli_returns_the_same_contract(self) -> None:
        primary = self.make_repo("authorization-cli")
        delivery = Path(self.start(primary, "authorization-cli-work")["worktree"])
        self.transition(
            delivery,
            "authorization-cli-work",
            "requirements",
            "active",
            "requirements_started",
        )
        completed = run(
            [
                sys.executable,
                "-X",
                "utf8",
                "-B",
                str(SCRIPT),
                "authorize",
                "--repo",
                str(delivery),
                "--phase",
                "requirements",
                "--work-id",
                "authorization-cli-work",
                "--registry-root",
                str(self.registry),
            ],
        )
        result = json.loads(completed.stdout)
        self.assertEqual("delivery-stage-authorization/v1", result["schema"])
        self.assertEqual("authorized", result["outcome"])

    def test_requirements_entry_is_routed_before_stage_writes(self) -> None:
        skill_root = SCRIPT.parents[2] / "requirements-discovery"
        skill = (skill_root / "SKILL.md").read_text(encoding="utf-8")
        interface = (skill_root / "agents/openai.yaml").read_text(encoding="utf-8")
        self.assertLess(
            skill.index("## 0. 驗證 routed context"),
            skill.index("## 1. 查明可取得事實"),
        )
        for fragment in (
            "authorize --repo . --phase requirements",
            "requirements/active",
            "維持零寫入",
        ):
            self.assertIn(fragment, skill)
        self.assertIn("$delivery-orchestrator", interface)
        self.assertIn("$requirements-discovery", interface)
        completed = run(
            [
                sys.executable,
                "-X",
                "utf8",
                "-B",
                str(skill_root / "scripts/validate_contracts.py"),
            ]
        )
        self.assertIn(b"contracts: PASS", completed.stdout)

        primary = self.make_repo("requirements-entry")
        sentinel = self.root / "requirements-external.bin"
        sentinel.write_bytes(b"unchanged")
        rejected_repo_target = primary / "docs" / "work" / "candidate-requirements.md"
        rejected_host_target = self.root / "host" / "requirements-candidate.json"
        before = primary_snapshot(primary)
        rejected = self._attempt_stage_writes(
            primary,
            "requirements",
            work_id=None,
            repository_target=rejected_repo_target,
            host_target=rejected_host_target,
        )
        self.assertEqual("routing_required", rejected["outcome"])
        self.assertEqual(before, primary_snapshot(primary))
        self.assertFalse(rejected_repo_target.exists())
        self.assertFalse(rejected_host_target.exists())
        self.assertEqual(hashlib.sha256(b"unchanged").hexdigest(), digest(sentinel))

        work_id = "requirements-entry-work"
        delivery = Path(self.start(primary, work_id)["worktree"])
        self.transition(
            delivery,
            work_id,
            "requirements",
            "active",
            "requirements_started",
        )
        accepted_repo_target = delivery / "docs" / "work" / work_id / "candidate.md"
        accepted_host_target = self.root / "host" / "requirements-authorized.json"
        accepted = self._attempt_stage_writes(
            delivery,
            "requirements",
            work_id=work_id,
            repository_target=accepted_repo_target,
            host_target=accepted_host_target,
        )
        self.assertEqual("authorized", accepted["outcome"])
        self.assertTrue(accepted_repo_target.is_file())
        self.assertTrue(accepted_host_target.is_file())

    def test_planning_entry_is_routed_and_plan_only_stays_read_only(self) -> None:
        skill_root = SCRIPT.parents[2] / "technical-planning"
        skill = (skill_root / "SKILL.md").read_text(encoding="utf-8")
        interface = (skill_root / "agents/openai.yaml").read_text(encoding="utf-8")
        self.assertLess(
            skill.index("## 0. 驗證 routed context"),
            skill.index("## 1. 鎖定來源與證據"),
        )
        for fragment in (
            "authorize --repo . --phase planning",
            "planning/active",
            "維持零 Plan／Knowledge Candidate 寫入",
            "Plan-only 解說、研究、審查、治理驗證與隔離測試",
        ):
            self.assertIn(fragment, skill)
        self.assertIn("$delivery-orchestrator", interface)
        self.assertIn("$technical-planning", interface)
        completed = run(
            [
                sys.executable,
                "-X",
                "utf8",
                "-B",
                str(skill_root / "scripts/validate_contracts.py"),
            ]
        )
        self.assertIn(b"contracts: PASS", completed.stdout)

        primary = self.make_repo("planning-entry")
        work_id = "planning-entry-work"
        delivery = Path(self.start(primary, work_id)["worktree"])
        self.transition(
            delivery,
            work_id,
            "requirements",
            "active",
            "requirements_started",
        )
        plan_target = delivery / "docs" / "work" / work_id / "plan" / "plan.md"
        candidate_target = self.root / "host" / "planning-candidate.json"
        sentinel = self.root / "planning-external.bin"
        sentinel.write_bytes(b"unchanged")
        before = {
            "delivery": primary_snapshot(delivery),
            "registry": file_bytes(self.registry),
            "sentinel": digest(sentinel),
        }
        rejected = self._attempt_stage_writes(
            delivery,
            "planning",
            work_id=work_id,
            repository_target=plan_target,
            host_target=candidate_target,
        )
        self.assertEqual("routing_required", rejected["outcome"])
        self.assertEqual("wrong_phase", rejected["reason"])
        self.assertEqual(before["delivery"], primary_snapshot(delivery))
        self.assertEqual(before["registry"], file_bytes(self.registry))
        self.assertEqual(before["sentinel"], digest(sentinel))
        self.assertFalse(plan_target.exists())
        self.assertFalse(candidate_target.exists())

        requirements_path, requirements_sha = self.approve_requirements(delivery, work_id)
        accepted = self._attempt_stage_writes(
            delivery,
            "planning",
            work_id=work_id,
            repository_target=plan_target,
            host_target=candidate_target,
        )
        self.assertEqual("authorized", accepted["outcome"])
        self.assertTrue(plan_target.is_file())
        self.assertTrue(candidate_target.is_file())
        self.assertTrue(requirements_path)
        self.assertTrue(requirements_sha)

    def test_implementation_requires_delivery_before_run_or_product_writes(self) -> None:
        skill_root = SCRIPT.parents[2] / "implementation-execution"
        skill = (skill_root / "SKILL.md").read_text(encoding="utf-8")
        preflight = (skill_root / "references/preflight-and-ledger.md").read_text(
            encoding="utf-8"
        )
        gate = (skill_root / "references/orchestrated-delivery.md").read_text(
            encoding="utf-8"
        )
        interface = (skill_root / "agents/openai.yaml").read_text(encoding="utf-8")
        self.assertLess(
            skill.index("## 0. 取得階段授權"),
            skill.index("## 1. Preflight"),
        )
        for fragment in (
            "authorize --repo . --phase implementation",
            "implementation/active",
            "execution run、binding、Ledger、evidence、fixture、產品 diff 或外部狀態前",
        ):
            self.assertIn(fragment, skill)
        self.assertIn("沒有 valid Delivery authorization 時不建立 run", preflight)
        self.assertIn("歷史 standalone Ledger 與 Ready artifacts 只保留唯讀", gate)
        self.assertIn("不恢復 standalone mutation path", gate)
        self.assertNotIn("Standalone execution維持manifest-only dirty規則", gate)
        self.assertIn("$delivery-orchestrator", interface)
        self.assertIn("$implementation-execution", interface)
        completed = run(
            [
                sys.executable,
                "-X",
                "utf8",
                "-B",
                str(skill_root / "scripts/validate_contracts.py"),
            ]
        )
        self.assertIn(b"contracts: PASS", completed.stdout)

        ready_only = self.make_repo("implementation-ready-only")
        ready_path = ready_only / "docs" / "work" / "ready-only" / "plan" / "handoff.json"
        ready_path.parent.mkdir(parents=True)
        ready_path.write_text('{"approval":{"status":"Ready"}}\n', encoding="utf-8")
        historical_ledger = self.root / "historical-standalone" / "run.json"
        historical_ledger.parent.mkdir(parents=True)
        historical_ledger.write_bytes(b"historical standalone ledger\n")
        historical_sha = digest(historical_ledger)
        product_target = ready_only / "product-change.txt"
        new_ledger_target = self.root / "host" / "new-implementation-run" / "run.json"
        before = primary_snapshot(ready_only)
        rejected = self._attempt_stage_writes(
            ready_only,
            "implementation",
            work_id=None,
            repository_target=product_target,
            host_target=new_ledger_target,
        )
        self.assertEqual("routing_required", rejected["outcome"])
        self.assertEqual(before, primary_snapshot(ready_only))
        self.assertFalse(product_target.exists())
        self.assertFalse(new_ledger_target.exists())
        self.assertEqual(historical_sha, digest(historical_ledger))

        primary = self.make_repo("implementation-entry")
        work_id = "implementation-entry-work"
        delivery = Path(self.start(primary, work_id)["worktree"])
        self.transition(
            delivery,
            work_id,
            "requirements",
            "active",
            "requirements_started",
        )
        requirements_path, requirements_sha = self.approve_requirements(delivery, work_id)
        self.approve_plan(delivery, work_id, requirements_path, requirements_sha)
        authorized_product = delivery / "authorized-product-change.txt"
        authorized_ledger = self.root / "host" / "authorized-implementation" / "run.json"
        accepted = self._attempt_stage_writes(
            delivery,
            "implementation",
            work_id=work_id,
            repository_target=authorized_product,
            host_target=authorized_ledger,
        )
        self.assertEqual("authorized", accepted["outcome"])
        self.assertTrue(authorized_product.is_file())
        self.assertTrue(authorized_ledger.is_file())

    def test_delivery_owns_gated_automatic_flow_and_return_paths(self) -> None:
        primary = self.make_repo("unified-flow")
        work_id = "unified-flow-work"
        delivery = Path(self.start(primary, work_id)["worktree"])
        self.transition(
            delivery,
            work_id,
            "requirements",
            "active",
            "requirements_started",
        )
        self.assertEqual(
            "authorized",
            workspace.authorize_stage(
                delivery,
                "requirements",
                root=self.registry,
                work_id=work_id,
            )["outcome"],
        )
        self.transition(
            delivery,
            work_id,
            "requirements",
            "awaiting_user",
            "requirements_candidate",
        )
        self.assertEqual(
            "routing_required",
            workspace.authorize_stage(
                delivery,
                "requirements",
                root=self.registry,
                work_id=work_id,
            )["outcome"],
        )
        requirements_path, requirements_sha = self.approve_requirements(
            delivery,
            work_id,
        )
        self.assertEqual(
            "authorized",
            workspace.authorize_stage(
                delivery,
                "planning",
                root=self.registry,
                work_id=work_id,
            )["outcome"],
        )
        self.approve_plan(delivery, work_id, requirements_path, requirements_sha)
        implementation = workspace.authorize_stage(
            delivery,
            "implementation",
            root=self.registry,
            work_id=work_id,
        )
        self.assertEqual("authorized", implementation["outcome"])
        self.assertEqual("implementation", implementation["record"]["phase"])

        routing = (SCRIPT.parents[1] / "references/stage-routing.md").read_text(
            encoding="utf-8"
        )
        for fragment in (
            "Requirements Ready 的人工 Gate 通過後自動 dispatch Planning",
            "Plan Ready 的人工 Gate 通過後自動 dispatch Implementation",
            "Delivery transition 仍由 Orchestrator 單獨持有",
            "`affecting-current-work`",
            "`knowledge/awaiting_user`",
        ):
            self.assertIn(fragment, routing)

    def test_read_only_and_governance_exceptions_do_not_gain_write_authority(self) -> None:
        primary = self.make_repo("read-only-exceptions")
        before = primary_snapshot(primary)
        result = workspace.authorize_stage(
            primary,
            "requirements",
            root=self.registry,
        )
        self.assertEqual("routing_required", result["outcome"])
        self.assertEqual("no_active_delivery", result["reason"])
        self.assertEqual(before, primary_snapshot(primary))
        self.assertFalse(self.registry.exists())

        routing = (SCRIPT.parents[1] / "references/stage-routing.md").read_text(
            encoding="utf-8"
        )
        for exception in (
            "純解說",
            "診斷",
            "唯讀審查",
            "plan-only",
            "治理驗證",
            "Project Knowledge 明示治理流程",
            "隔離測試",
        ):
            self.assertIn(exception, routing)

    def test_legacy_bug_security_and_performance_contracts_remain_covered(self) -> None:
        behavior = (SCRIPT.parents[1] / "references/behavior-evaluation.md").read_text(
            encoding="utf-8"
        )
        skill = (SCRIPT.parents[1] / "SKILL.md").read_text(encoding="utf-8")
        for fragment in (
            "EVAL-DEL-008",
            "EVAL-DEL-009",
            "EVAL-DEL-010",
            "歷史 standalone Ledger 只讀且 bytes 不變",
        ):
            self.assertIn(fragment, behavior)
        for fragment in (
            "缺 `work_kind` 的舊 record 等同 standard work",
            "嚴禁 stash、reset、clean、stage、commit、push、merge、deploy、delete 或 cleanup",
        ):
            self.assertIn(fragment, skill)
        runner = SCRIPT.with_name("test_delivery_workspace.py").read_text(encoding="utf-8")
        self.assertIn("class DeliveryPerformanceTests", runner)
        self.assertIn("DeliveryPerformanceTests,", runner)
        self.assertIn(
            "test_50k_repository_probe_transition_and_authorize_stay_under_two_seconds",
            runner,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
