#!/usr/bin/env python3
"""DeliverySafetyTests isolated contract suite."""

from _delivery_test_support import *  # noqa: F403


class DeliverySafetyTests(DeliveryFixture):
    def test_historical_ready_trust_root_does_not_apply_later_coverage_rules(self) -> None:
        historical = planning_fixture.ready_example()
        historical["sources"].append(
            {
                "source_id": "SRC-002",
                "kind": "project",
                "location": "docs/legacy-source.md",
                "revision": "legacy",
                "sha256": planning_fixture.HASH,
                "plan_refs": ["REQ-002"],
                "wp_refs": ["WP-001"],
            }
        )
        historical["work_packages"][0]["source_refs"].append("SRC-002")
        for contract in historical["contract_index"]:
            if contract["kind"] in {"bdd-scenario", "inner-test"}:
                contract["source_refs"] = ["SRC-002"]
        historical["candidate"]["payload_sha256"] = workspace._ready_payload_sha256(historical)

        with self.assertRaises(workspace.DeliveryError) as raised:
            workspace._validate_ready_contract(historical)
        self.assertEqual("INVALID_HANDOFF", raised.exception.code)
        workspace._validate_historical_ready_contract(historical)

    def test_secret_shaped_logical_refs_are_rejected(self) -> None:
        primary = self.make_repo()
        delivery = Path(self.start(primary, "secret-ref-work")["worktree"])
        self.enter_requirements(delivery, "secret-ref-work")
        relative = "docs/work/secret-ref-work/requirements.md"
        path = delivery / Path(*relative.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# Ready requirements\n", encoding="utf-8", newline="\n")
        self.assert_error(
            "INVALID_EVIDENCE_REF",
            lambda: self.transition(
                delivery,
                "secret-ref-work",
                "planning",
                "active",
                "secret_ref_rejected",
                requirements_path=relative,
                requirements_sha256=digest(path),
                requirements_approval_refs=["conversation:EVAL_SECRET_DO_NOT_PERSIST_123456"],
            ),
        )
        record = self.record(delivery, "secret-ref-work")
        forged = copy.deepcopy(record)
        forged["events"][0]["evidence_refs"] = ["evidence/EVAL_SECRET_DO_NOT_PERSIST_123456"]
        self.assertTrue(any("evidence refs" in error for error in workspace.validate_record(forged)))

    def test_checkout_disables_hooks_filters_and_raw_command_output_persistence(self) -> None:
        primary = self.make_repo()
        filtered = primary / "filtered.txt"
        expected_bytes = b"tracked bytes must survive checkout\n"
        filtered.write_bytes(expected_bytes)
        (primary / ".gitattributes").write_text("filtered.txt filter=evil\n", encoding="utf-8", newline="\n")
        git(primary, "add", ".gitattributes", "filtered.txt")
        git(primary, "commit", "-m", "add filtered fixture")

        fake_secret = "DELIVERY_HOOK_SECRET=never-persist-this"
        sentinel = self.root / "hook-filter-sentinel.txt"
        sentinel.write_text("unchanged\n", encoding="utf-8", newline="\n")
        sentinel_sha = digest(sentinel)
        filter_script = self.root / "evil-filter.sh"
        filter_script.write_text(
            "#!/bin/sh\n"
            "printf 'filter-invoked\\n' >> \"$1\"\n"
            f"printf '%s\\n' '{fake_secret}' >&2\n"
            "cat\n",
            encoding="utf-8",
            newline="\n",
        )
        filter_command = f'sh "{filter_script.as_posix()}" "{sentinel.as_posix()}"'
        git(primary, "config", "filter.evil.process", filter_command)
        git(primary, "config", "filter.evil.clean", filter_command)
        git(primary, "config", "filter.evil.smudge", filter_command)
        git(primary, "config", "filter.evil.required", "true")

        fsmonitor_script = self.root / "evil-fsmonitor.sh"
        fsmonitor_script.write_text(
            "#!/bin/sh\n"
            f"printf 'fsmonitor-invoked\\n' >> '{sentinel.as_posix()}'\n"
            f"printf '%s\\n' '{fake_secret}' >&2\n",
            encoding="utf-8",
            newline="\n",
        )
        os.chmod(
            fsmonitor_script,
            fsmonitor_script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH,
        )
        git(primary, "config", "core.fsmonitor", fsmonitor_script.as_posix())

        hooks = git_path(primary, "hooks")
        hooks.mkdir(parents=True, exist_ok=True)
        hook = hooks / "post-checkout"
        hook.write_text(
            "#!/bin/sh\n"
            f"printf 'hook-invoked\\n' >> '{sentinel.as_posix()}'\n"
            f"printf '%s\\n' '{fake_secret}'\n",
            encoding="utf-8",
            newline="\n",
        )
        os.chmod(hook, hook.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        filtered.write_bytes(expected_bytes)

        result = self.start(primary, "hook-filter-work")
        delivery = Path(result["worktree"])
        self.assertEqual(sentinel_sha, digest(sentinel))
        self.assertEqual(expected_bytes, (delivery / "filtered.txt").read_bytes())

        run_dir = Path(result["record_path"]).parent
        persisted = "\n".join(
            path.read_text(encoding="utf-8", errors="replace")
            for path in sorted(run_dir.rglob("*"))
            if path.is_file()
        )
        self.assertNotIn(fake_secret, persisted)
        evidence = json.loads((run_dir / "evidence" / "worktree-add-r1.json").read_text(encoding="utf-8"))
        self.assertNotIn("stdout", evidence)
        self.assertNotIn("stderr", evidence)
        self.assertIn("stdout_sha256", evidence)
        self.assertIn("stderr_sha256", evidence)
        self.assertEqual(1, evidence["safety_controls"]["filter_driver_count"])

    def test_terminal_snapshot_disables_textconv(self) -> None:
        primary = self.make_repo("textconv")
        (primary / ".gitattributes").write_text(
            "tracked.txt diff=evil\n",
            encoding="utf-8",
            newline="\n",
        )
        (primary / "tracked.txt").write_text("baseline tracked bytes\n", encoding="utf-8", newline="\n")
        git(primary, "add", ".gitattributes", "tracked.txt")
        git(primary, "commit", "-m", "add textconv fixture")

        result = self.start(primary, "textconv-work")
        delivery = Path(result["worktree"])
        sentinel = self.root / "textconv-sentinel.txt"
        script = self.root / "evil-textconv.sh"
        script.write_text(
            "#!/bin/sh\n"
            "printf 'invoked' >> \"$1\"\n"
            "cat \"$2\"\n",
            encoding="utf-8",
            newline="\n",
        )
        os.chmod(script, script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        textconv = f'sh "{script.as_posix()}" "{sentinel.as_posix()}"'
        git(delivery, "config", "diff.evil.textconv", textconv)
        (delivery / "tracked.txt").write_text(
            "changed tracked bytes\n",
            encoding="utf-8",
            newline="\n",
        )

        record = self.record(delivery, "textconv-work")
        generation = record["generations"][-1]
        expected = git(
            delivery,
            "diff",
            "--binary",
            "--full-index",
            "--no-ext-diff",
            "--no-textconv",
            generation["base_sha"],
            "--",
        ).stdout
        snapshot = workspace._current_implementation_snapshot(
            record,
            {"artifacts": [], "sources": []},
        )

        self.assertFalse(sentinel.exists(), "terminal snapshot executed a textconv driver")
        self.assertEqual(hashlib.sha256(expected).hexdigest(), snapshot["tracked_diff_sha256"])

    def test_terminal_snapshot_reads_base_revision_sources_from_git(self) -> None:
        primary = self.make_repo("base-source-snapshot")
        result = self.start(primary, "base-source-snapshot-work")
        delivery = Path(result["worktree"])
        record = self.record(delivery, "base-source-snapshot-work")
        generation = record["generations"][-1]
        base_bytes = git(
            delivery,
            "cat-file",
            "blob",
            f"{generation['base_sha']}:app.txt",
        ).stdout
        base_sha256 = hashlib.sha256(base_bytes).hexdigest()

        (delivery / "app.txt").write_text(
            "implemented change\n",
            encoding="utf-8",
            newline="\n",
        )
        ready = {
            "artifacts": [],
            "sources": [
                {
                    "source_id": "SRC-BASE-001",
                    "location": "app.txt",
                    "revision": generation["base_sha"],
                    "sha256": base_sha256,
                }
            ],
        }

        snapshot = workspace._current_implementation_snapshot(record, ready)

        self.assertEqual(
            [{"ref": "SRC-BASE-001", "sha256": base_sha256}],
            snapshot["source_hashes"],
        )
        self.assertNotEqual(hashlib.sha256(b"").hexdigest(), snapshot["tracked_diff_sha256"])

        wrong = copy.deepcopy(ready)
        wrong["sources"][0]["sha256"] = "0" * 64
        self.assert_error(
            "INVALID_IMPLEMENTATION_REF",
            lambda: workspace._current_implementation_snapshot(record, wrong),
        )

    def test_ready_base_sources_use_raw_git_bytes_during_plan_admission(self) -> None:
        from _delivery_record import _verify_ready_local_sources

        primary = self.make_repo("ready-base-source")
        result = self.start(primary, "ready-base-source-work")
        delivery = Path(result["worktree"])
        record = self.record(delivery, "ready-base-source-work")
        generation = record["generations"][-1]
        base_bytes = git(
            delivery,
            "cat-file",
            "blob",
            f"{generation['base_sha']}:app.txt",
        ).stdout
        base_sha256 = hashlib.sha256(base_bytes).hexdigest()
        handoff = {
            "sources": [
                {
                    "source_id": "SRC-BASE-001",
                    "location": "app.txt",
                    "revision": generation["base_sha"],
                    "sha256": base_sha256,
                }
            ]
        }

        (delivery / "app.txt").write_text(
            "implementation changed this planned target\n",
            encoding="utf-8",
            newline="\n",
        )

        _verify_ready_local_sources(
            record,
            handoff,
            set(),
            verify_current_sources=True,
        )
        _verify_ready_local_sources(
            record,
            handoff,
            set(),
            verify_current_sources=False,
        )

        wrong = copy.deepcopy(handoff)
        wrong["sources"][0]["sha256"] = "0" * 64
        self.assert_error(
            "SOURCE_NOT_MATERIALIZABLE",
            lambda: _verify_ready_local_sources(
                record,
                wrong,
                set(),
                verify_current_sources=True,
            ),
        )

    def test_plan_revision_can_reuse_prior_ready_supporting_artifact(self) -> None:
        primary = self.make_repo("prior-ready-supporting")
        delivery = Path(self.start(primary, "prior-ready-supporting-work")["worktree"])
        self.enter_requirements(delivery, "prior-ready-supporting-work")
        requirements_path, requirements_sha = self.approve_requirements(
            delivery,
            "prior-ready-supporting-work",
        )

        def attach_supporting(
            handoff_path: str,
            payload: str,
            *,
            include_artifact: bool,
        ) -> str:
            del payload
            handoff_file = delivery / Path(*handoff_path.split("/"))
            handoff = json.loads(handoff_file.read_text(encoding="utf-8"))
            supporting_relative = (
                "docs/work/prior-ready-supporting-work/plan/source-evidence.md"
            )
            supporting = delivery / Path(*supporting_relative.split("/"))
            if include_artifact:
                supporting.write_text(
                    "approved supporting evidence\n",
                    encoding="utf-8",
                    newline="\n",
                )
                handoff["artifacts"].insert(
                    -1,
                    {
                        "path": supporting_relative,
                        "role": "supporting",
                        "approval_status": "Ready",
                        "sha256": digest(supporting),
                    },
                )
            handoff["sources"].append(
                {
                    "source_id": "SRC-SUPPORTING-001",
                    "kind": "supporting",
                    "location": supporting_relative,
                    "revision": "candidate-1",
                    "sha256": digest(supporting),
                    "plan_refs": ["REQ-001"],
                    "wp_refs": ["WP-001"],
                }
            )
            for contract in handoff["contract_index"]:
                if contract["contract_id"] in {
                    "REQ-001",
                    "BDD-001",
                    "TEST-001",
                    "WP-001",
                }:
                    contract["source_refs"].append("SRC-SUPPORTING-001")
            handoff["work_packages"][0]["source_refs"].append(
                "SRC-SUPPORTING-001"
            )
            handoff["candidate"]["payload_sha256"] = workspace._ready_payload_sha256(
                handoff
            )
            handoff_file.write_text(
                json.dumps(handoff, ensure_ascii=False, sort_keys=True, indent=2)
                + "\n",
                encoding="utf-8",
                newline="\n",
            )
            return handoff["candidate"]["payload_sha256"]

        self.transition(
            delivery,
            "prior-ready-supporting-work",
            "planning",
            "awaiting_user",
            "plan_1_candidate",
        )
        handoff_1, payload_1, evidence_1 = self.ready_handoff(
            delivery,
            "prior-ready-supporting-work",
            requirements_path,
            requirements_sha,
        )
        payload_1 = attach_supporting(
            handoff_1,
            payload_1,
            include_artifact=True,
        )
        self.transition(
            delivery,
            "prior-ready-supporting-work",
            "implementation",
            "active",
            "plan_1_approved",
            handoff_path=handoff_1,
            candidate_revision="candidate-1",
            payload_sha256=payload_1,
            plan_approval_refs=[evidence_1],
        )

        run_id = "a" * 64
        self.transition(
            delivery,
            "prior-ready-supporting-work",
            "planning",
            "active",
            "implementation_reapproval",
            implementation_run_id=run_id,
            implementation_ledger_ref="implementation:run-a",
            implementation_status="Awaiting upstream reapproval",
        )
        self.transition(
            delivery,
            "prior-ready-supporting-work",
            "planning",
            "awaiting_user",
            "plan_2_candidate",
        )
        handoff_2, payload_2, evidence_2 = self.ready_handoff(
            delivery,
            "prior-ready-supporting-work",
            requirements_path,
            requirements_sha,
            2,
        )
        payload_2 = attach_supporting(
            handoff_2,
            payload_2,
            include_artifact=False,
        )
        self.transition(
            delivery,
            "prior-ready-supporting-work",
            "implementation",
            "active",
            "plan_2_approved",
            handoff_path=handoff_2,
            candidate_revision="candidate-2",
            payload_sha256=payload_2,
            plan_approval_refs=[evidence_2],
        )

        record = self.record(delivery, "prior-ready-supporting-work")
        self.assertEqual(handoff_2, record["plans"]["current_handoff_path"])
        materialized_paths = {
            item["path"]
            for item in workspace._approved_upstream_materialization(record)
        }
        self.assertIn(
            "docs/work/prior-ready-supporting-work/plan/source-evidence.md",
            materialized_paths,
        )
        self.assertIn(handoff_1, materialized_paths)

        blocked_record = copy.deepcopy(record)
        blocked_record["current_generation"] = 2
        blocked_record["generations"].append(
            {
                "generation": 2,
                "canonical_worktree": str(self.root / "blocked-generation"),
                "worktree_key": "b" * 64,
                "branch": "delivery/prior-ready-supporting-work-r2",
                "base_sha": record["generations"][-1]["base_sha"],
                "status": "blocked",
                "created_at": "2026-08-30T00:00:00Z",
            }
        )
        self.assertEqual(
            materialized_paths,
            {
                item["path"]
                for item in workspace._approved_upstream_materialization(
                    blocked_record
                )
            },
        )


    def test_request_and_evidence_records_do_not_persist_raw_secret(self) -> None:
        primary = self.make_repo()
        fake_secret = "DELIVERY_FAKE_SECRET=unique-do-not-store"
        request_sha = hashlib.sha256(fake_secret.encode("utf-8")).hexdigest()
        result = workspace.start_workspace(
            primary,
            "secret-work",
            request_sha,
            root=self.registry,
        )
        run_dir = Path(result["record_path"]).parent
        persisted = "\n".join(
            path.read_text(encoding="utf-8", errors="replace")
            for path in sorted(run_dir.rglob("*"))
            if path.is_file()
        )
        self.assertNotIn(fake_secret, persisted)
        self.assertIn(request_sha, persisted)
        self.assert_error(
            "INVALID_EVENT",
            lambda: workspace.transition_record(
                result["worktree"],
                "secret-work",
                "requirements",
                "active",
                "secret_ref_rejected",
                [fake_secret],
                root=self.registry,
            ),
        )


    def test_dirty_primary_matrix_and_ignored_outputs(self) -> None:
        mutators = {
            "unstaged": lambda repo: (repo / "app.txt").write_text("changed\n", encoding="utf-8"),
            "staged": lambda repo: (
                (repo / "app.txt").write_text("changed\n", encoding="utf-8"),
                git(repo, "add", "app.txt"),
            ),
            "untracked": lambda repo: (repo / "new.txt").write_text("new\n", encoding="utf-8"),
        }
        for index, (label, mutate) in enumerate(mutators.items(), 1):
            with self.subTest(label=label):
                repo = self.make_repo(f"dirty-{index}")
                mutate(repo)
                before = primary_snapshot(repo)
                work_id = f"dirty-work-{index}"
                self.assert_error("DIRTY_PRIMARY", lambda: self.start(repo, work_id))
                self.assertEqual(before, primary_snapshot(repo))
                self.assertFalse((repo.parent / f"{repo.name}.worktrees" / work_id).exists())
                branch = git(repo, "show-ref", "--verify", f"refs/heads/delivery/{work_id}", check=False)
                self.assertNotEqual(0, branch.returncode)

        ignored = self.make_repo("ignored")
        (ignored / ".gitignore").write_text("cache/\n", encoding="utf-8")
        git(ignored, "add", ".gitignore")
        git(ignored, "commit", "-m", "ignore cache")
        (ignored / "cache").mkdir()
        (ignored / "cache" / "result.bin").write_bytes(b"ignored")
        self.assertTrue(workspace.probe_repository(ignored)["strict_clean"])
        self.assertEqual("created", self.start(ignored, "ignored-work")["outcome"])


    def test_dirty_submodule_detached_and_bare_are_rejected(self) -> None:
        source = self.make_repo("sub-source")
        (source / ".gitattributes").write_text("filtered.txt filter=evil\n", encoding="utf-8", newline="\n")
        (source / "filtered.txt").write_text("submodule filter fixture\n", encoding="utf-8", newline="\n")
        git(source, "add", ".gitattributes", "filtered.txt")
        git(source, "commit", "-m", "add submodule filter fixture")
        primary = self.make_repo("with-submodule")
        git(
            primary,
            "-c",
            "protocol.file.allow=always",
            "submodule",
            "add",
            str(source),
            "modules/sub",
        )
        git(primary, "commit", "-am", "add submodule")
        child = primary / "modules" / "sub"
        sentinel = self.root / "submodule-filter-sentinel.txt"
        sentinel.write_text("unchanged\n", encoding="utf-8", newline="\n")
        sentinel_sha = digest(sentinel)
        filter_script = self.root / "submodule-filter.sh"
        filter_script.write_text(
            "#!/bin/sh\n"
            "printf 'submodule-filter-invoked\\n' >> \"$1\"\n"
            "cat\n",
            encoding="utf-8",
            newline="\n",
        )
        filter_command = f'sh "{filter_script.as_posix()}" "{sentinel.as_posix()}"'
        for key in ("process", "clean", "smudge"):
            git(child, "config", f"filter.evil.{key}", filter_command)
        git(child, "config", "filter.evil.required", "true")
        fsmonitor_script = self.root / "submodule-fsmonitor.sh"
        fsmonitor_script.write_text(
            "#!/bin/sh\n"
            f"printf 'submodule-fsmonitor-invoked\\n' >> '{sentinel.as_posix()}'\n",
            encoding="utf-8",
            newline="\n",
        )
        os.chmod(
            fsmonitor_script,
            fsmonitor_script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH,
        )
        git(child, "config", "core.fsmonitor", fsmonitor_script.as_posix())
        self.assertTrue(workspace.probe_repository(primary)["strict_clean"])
        self.assertEqual(sentinel_sha, digest(sentinel))
        clean_submodule = self.start(primary, "clean-submodule-work")
        self.assertEqual("created", clean_submodule["outcome"])
        self.assertEqual(sentinel_sha, digest(sentinel))

        (child / "app.txt").write_text("dirty submodule\n", encoding="utf-8")
        self.assertFalse(workspace.probe_repository(primary)["strict_clean"])
        self.assertEqual(sentinel_sha, digest(sentinel))
        self.assert_error("DIRTY_PRIMARY", lambda: self.start(primary, "submodule-work"))
        self.assertEqual(sentinel_sha, digest(sentinel))

        detached = self.make_repo("detached")
        git(detached, "checkout", "--detach")
        self.assert_error("DETACHED_HEAD", lambda: self.start(detached, "detached-work"))

        bare = self.root / "bare.git"
        run(["git", "init", "--bare", str(bare)])
        self.assert_error("BARE_REPOSITORY", lambda: workspace.probe_repository(bare))


    def test_branch_path_registry_and_permission_collisions(self) -> None:
        unsafe_repo = self.make_repo("unsafe-registry")
        unsafe_root = SCRIPT.parents[4] / ".delivery-registry-must-not-exist"
        self.assertFalse(unsafe_root.exists())
        self.assert_error(
            "UNSAFE_REGISTRY_ROOT",
            lambda: workspace.start_workspace(
                unsafe_repo,
                "unsafe-registry-work",
                REQUEST_SHA,
                root=unsafe_root,
            ),
        )
        self.assertFalse(unsafe_root.exists())

        branch_repo = self.make_repo("branch-collision")
        git(branch_repo, "branch", "delivery/branch-work")
        before = primary_snapshot(branch_repo)
        self.assert_error("BRANCH_COLLISION", lambda: self.start(branch_repo, "branch-work"))
        self.assertEqual(before, primary_snapshot(branch_repo))

        path_repo = self.make_repo("path-collision")
        destination = path_repo.parent / f"{path_repo.name}.worktrees" / "path-work"
        destination.mkdir(parents=True)
        sentinel = destination / "sentinel.txt"
        sentinel.write_text("preserve\n", encoding="utf-8")
        self.assert_error("PATH_COLLISION", lambda: self.start(path_repo, "path-work"))
        self.assertEqual("preserve\n", sentinel.read_text(encoding="utf-8"))

        registry_repo = self.make_repo("registry-collision")
        probe = workspace.probe_repository(registry_repo)
        reservation = workspace.run_directory(self.registry, probe["repo_id"], "registry-work")
        reservation.mkdir(parents=True)
        self.assert_error("INVALID_RECORD", lambda: self.start(registry_repo, "registry-work"))
        self.assertFalse((registry_repo.parent / f"{registry_repo.name}.worktrees" / "registry-work").exists())

        denied_repo = self.make_repo("permission-denied")
        blocked_container = denied_repo.parent / f"{denied_repo.name}.worktrees"
        blocked_container.write_text("not a directory\n", encoding="utf-8")
        self.assert_error("WORKSPACE_CREATE_FAILED", lambda: self.start(denied_repo, "permission-work"))
        blocked = self.record(denied_repo, "permission-work")
        self.assertEqual("blocked", blocked["status"])
        self.assertEqual("blocked", blocked["generations"][-1]["status"])
        self.assertTrue(blocked_container.is_file())


    def test_same_id_concurrent_start_has_one_mutator(self) -> None:
        primary = self.make_repo()
        barrier = threading.Barrier(2)

        def contender() -> tuple[str, str]:
            barrier.wait(timeout=10)
            try:
                return "ok", self.start(primary, "race-work")["outcome"]
            except workspace.DeliveryError as exc:
                return "error", exc.code

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(lambda _: contender(), range(2)))

        self.assertEqual(1, sum(result == ("ok", "created") for result in outcomes), outcomes)
        self.assertTrue(
            all(
                result in {("ok", "created"), ("ok", "existing"), ("error", "INVALID_RECORD"), ("error", "REGISTRY_COLLISION")}
                for result in outcomes
            ),
            outcomes,
        )
        registered = workspace._parse_worktrees(git(primary, "worktree", "list", "--porcelain").stdout)
        delivery_paths = [item for item in registered if str(item.get("branch", "")).endswith("delivery/race-work")]
        self.assertEqual(1, len(delivery_paths), registered)


    def test_record_tampering_and_lock_contention_fail_closed(self) -> None:
        primary = self.make_repo()
        started = self.start(primary, "tamper-work")
        delivery = Path(started["worktree"])
        record = self.record(primary, "tamper-work")
        broken = copy.deepcopy(record)
        broken["events"][0]["evidence_refs"] = ["secret=value"]
        evidence_errors = workspace.validate_record(broken)
        self.assertTrue(evidence_errors)
        self.assertNotIn("secret=value", "\n".join(evidence_errors))
        broken = copy.deepcopy(record)
        broken["generations"][0]["branch"] = "delivery/other-work"
        self.assertTrue(any("branch is not canonical" in error for error in workspace.validate_record(broken)))

        probe = workspace.probe_repository(primary)
        run_dir = workspace.run_directory(self.registry, probe["repo_id"], "tamper-work")
        lock = run_dir / "record.lock"
        lock.write_text("held\n", encoding="utf-8")
        self.assert_error(
            "RECORD_LOCKED",
            lambda: self.transition(delivery, "tamper-work", "requirements", "active", "locked_transition"),
        )
        self.assertEqual(record, self.record(primary, "tamper-work"))
        lock.unlink()

        git(delivery, "checkout", "--detach")
        self.assert_error(
            "WORKSPACE_DRIFT",
            lambda: self.transition(delivery, "tamper-work", "requirements", "active", "detached_transition"),
        )
        self.assertEqual(record, self.record(primary, "tamper-work"))


    def test_runtime_record_rejects_schema_extensions_without_reflecting_values(self) -> None:
        primary = self.make_repo()
        started = self.start(primary, "schema-tamper-work")
        path = Path(started["record_path"])
        original = json.loads(path.read_text(encoding="utf-8"))

        root_extension = copy.deepcopy(original)
        root_extension["unexpected"] = "DELIVERY_RECORD_SECRET=must-not-be-reflected"
        self.assertTrue(workspace.validate_record(root_extension))
        path.write_text(
            json.dumps(root_extension, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        error = self.assert_error("INVALID_RECORD", lambda: workspace.load_record(path))
        self.assertNotIn("DELIVERY_RECORD_SECRET", str(error))
        self.assertNotIn("must-not-be-reflected", str(error))

        nested_extension = copy.deepcopy(original)
        nested_extension["requirements"]["unexpected"] = "nested-secret"
        path.write_text(
            json.dumps(nested_extension, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        error = self.assert_error("INVALID_RECORD", lambda: workspace.load_record(path))
        self.assertNotIn("nested-secret", str(error))

        path.write_text(
            json.dumps(original, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        self.assertEqual(original, workspace.load_record(path))


    def test_git_trust_failure_has_a_precise_non_reflective_error(self) -> None:
        completed = subprocess.CompletedProcess(
            ["git"],
            128,
            stdout=b"",
            stderr=(
                b"fatal: detected dubious ownership in repository at 'SECRET_SENTINEL'\n"
                b"To add an exception for this directory, call:\n"
                b"git config --global --add safe.directory SECRET_SENTINEL\n"
            ),
        )
        error = workspace._git_failure_error(
            completed,
            fallback_code="NOT_A_REPOSITORY",
            fallback_message="not a Git repository",
        )
        self.assertEqual("GIT_TRUST_REQUIRED", error.code)
        self.assertNotIn("SECRET_SENTINEL", str(error))


if __name__ == "__main__":
    unittest.main(verbosity=2)
