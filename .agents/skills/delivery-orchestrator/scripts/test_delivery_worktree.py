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
        for name in ("_delivery_runtime.py", "_delivery_git.py", "_delivery_record.py"):
            self.assertTrue(SCRIPT.with_name(name).is_file(), name)
        parser = workspace._parser()
        subparsers = next(
            action for action in parser._actions if action.__class__.__name__ == "_SubParsersAction"
        )
        self.assertEqual({"probe", "start", "locate", "transition"}, set(subparsers.choices))
        self.assertEqual("_delivery_git", workspace.probe_repository.__module__)
        self.assertEqual("_delivery_record", workspace.validate_record.__module__)
        self.assertEqual("delivery_workspace", workspace.start_workspace.__module__)


if __name__ == "__main__":
    unittest.main(verbosity=2)
