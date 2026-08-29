#!/usr/bin/env python3
"""Isolated Git fixture tests for delivery_workspace.py."""

from __future__ import annotations

import concurrent.futures
import copy
import hashlib
import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from typing import Any, Sequence


SCRIPT = Path(__file__).with_name("delivery_workspace.py")
SPEC = importlib.util.spec_from_file_location("delivery_workspace", SCRIPT)
if SPEC is None or SPEC.loader is None:  # pragma: no cover - import infrastructure
    raise RuntimeError(f"cannot import {SCRIPT}")
workspace = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = workspace
SPEC.loader.exec_module(workspace)

PLANNING_TEST = SCRIPT.resolve().parents[2] / "technical-planning" / "scripts" / "test_validate_contracts.py"
PLANNING_SPEC = importlib.util.spec_from_file_location("delivery_planning_fixture", PLANNING_TEST)
if PLANNING_SPEC is None or PLANNING_SPEC.loader is None:  # pragma: no cover - import infrastructure
    raise RuntimeError(f"cannot import {PLANNING_TEST}")
planning_fixture = importlib.util.module_from_spec(PLANNING_SPEC)
PLANNING_SPEC.loader.exec_module(planning_fixture)

REQUEST_SHA = hashlib.sha256(b"original delivery request").hexdigest()


def run(command: Sequence[str], *, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    environment = os.environ.copy()
    environment.update(
        {
            "GIT_AUTHOR_NAME": "Delivery Test",
            "GIT_AUTHOR_EMAIL": "delivery@example.invalid",
            "GIT_COMMITTER_NAME": "Delivery Test",
            "GIT_COMMITTER_EMAIL": "delivery@example.invalid",
            "GIT_CONFIG_NOSYSTEM": "1",
        }
    )
    completed = subprocess.run(
        list(command),
        cwd=cwd,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and completed.returncode != 0:
        raise AssertionError(
            f"command failed ({completed.returncode}): {command!r}\n"
            f"stdout={completed.stdout.decode('utf-8', 'replace')}\n"
            f"stderr={completed.stderr.decode('utf-8', 'replace')}"
        )
    return completed


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    return run(["git", "-C", str(repo), *args], check=check)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def file_bytes(root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if not relative.parts or relative.parts[0] == ".git" or not path.is_file():
            continue
        result[relative.as_posix()] = digest(path)
    return result


def git_path(repo: Path, name: str) -> Path:
    raw = git(repo, "rev-parse", "--path-format=absolute", "--git-path", name).stdout.decode().strip()
    return Path(raw)


def primary_snapshot(repo: Path) -> dict[str, Any]:
    status = git(
        repo,
        "--no-optional-locks",
        "status",
        "--porcelain=v2",
        "-z",
        "--untracked-files=all",
        "--ignore-submodules=none",
    ).stdout
    return {
        "head": git(repo, "rev-parse", "HEAD").stdout,
        "symbolic_head": git(repo, "symbolic-ref", "HEAD", check=False).stdout,
        "index": digest(git_path(repo, "index")),
        "status": status,
        "files": file_bytes(repo),
    }


class DeliveryWorkspaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="delivery-orchestrator-test-")
        self.root = Path(self.temporary.name)
        self.registry = self.root / "registry"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def make_repo(self, name: str = "project") -> Path:
        repo = self.root / name
        run(["git", "init", "-b", "main", str(repo)])
        git(repo, "config", "core.autocrlf", "false")
        git(repo, "config", "user.name", "Delivery Test")
        git(repo, "config", "user.email", "delivery@example.invalid")
        (repo / "app.txt").write_text("baseline\n", encoding="utf-8", newline="\n")
        git(repo, "add", "app.txt")
        git(repo, "commit", "-m", "baseline")
        return repo

    def start(self, repo: Path, work_id: str = "work-test-001", generation: int = 1) -> dict[str, Any]:
        return workspace.start_workspace(
            repo,
            work_id,
            REQUEST_SHA,
            root=self.registry,
            generation=generation,
        )

    def assert_error(self, code: str, callback: Any) -> workspace.DeliveryError:
        with self.assertRaises(workspace.DeliveryError) as captured:
            callback()
        self.assertEqual(code, captured.exception.code, str(captured.exception))
        return captured.exception

    def record(self, repo: Path, work_id: str) -> dict[str, Any]:
        probe = workspace.probe_repository(repo)
        path = workspace.run_directory(self.registry, probe["repo_id"], work_id) / "run.json"
        return workspace.load_record(path)

    def transition(
        self,
        repo: Path,
        work_id: str,
        phase: str,
        status: str,
        event: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        return workspace.transition_record(
            repo,
            work_id,
            phase,
            status,
            event,
            [f"evidence/{event}.json"],
            root=self.registry,
            **kwargs,
        )

    def enter_requirements(self, delivery: Path, work_id: str) -> None:
        self.transition(delivery, work_id, "requirements", "active", "requirements_started")
        self.transition(delivery, work_id, "requirements", "awaiting_user", "requirements_candidate")

    def approve_requirements(self, delivery: Path, work_id: str, revision: int = 1) -> tuple[str, str]:
        name = "requirements.md" if revision == 1 else f"requirements-{revision}.md"
        relative = f"docs/work/{work_id}/{name}"
        path = delivery / Path(*relative.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# Requirements {revision}\n\nStatus: Ready\n", encoding="utf-8", newline="\n")
        value = digest(path)
        self.transition(
            delivery,
            work_id,
            "planning",
            "active",
            f"requirements_{revision}_approved",
            requirements_path=relative,
            requirements_sha256=value,
            requirements_approval_refs=[f"conversation:req-{revision}"],
        )
        return relative, value

    def ready_handoff(
        self,
        delivery: Path,
        work_id: str,
        requirements_path: str,
        requirements_sha256: str,
        revision: int = 1,
    ) -> tuple[str, str, str]:
        directory = "plan" if revision == 1 else f"plan-{revision}"
        root = delivery / "docs" / "work" / work_id / directory
        root.mkdir(parents=True, exist_ok=True)
        plan = root / "plan.md"
        plan.write_text(f"# Ready plan {revision}\n", encoding="utf-8", newline="\n")
        relative_handoff = f"docs/work/{work_id}/{directory}/handoff.json"
        evidence = f"conversation:plan-{revision}"
        record = self.record(delivery, work_id)
        handoff: dict[str, Any] = copy.deepcopy(planning_fixture.ready_example())
        handoff["candidate"]["revision"] = f"candidate-{revision}"
        handoff["approval"] = {
            "status": "Ready",
            "actor": "user",
            "confirmed_at": "2026-08-30T00:00:00Z",
            "evidence": evidence,
        }
        handoff["planning_baseline"] = {
            "repo_id": record["repo_id"],
            "head_sha": record["generations"][-1]["base_sha"],
            "status_sha256": "0" * 64,
        }
        plan_relative = f"docs/work/{work_id}/{directory}/plan.md"
        handoff["primary_plan"] = {"path": plan_relative, "sha256": digest(plan)}
        handoff["artifacts"] = [
            {
                "path": plan_relative,
                "role": "primary",
                "approval_status": "Ready",
                "sha256": digest(plan),
            },
            {
                "path": relative_handoff,
                "role": "handoff",
                "approval_status": "Ready",
                "sha256": None,
            },
        ]
        handoff["sources"][0].update(
            {
                "kind": "spec",
                "location": requirements_path,
                "revision": str(revision),
                "sha256": requirements_sha256,
            }
        )
        handoff["revision_impact"]["revision"] = f"candidate-{revision}"
        payload = workspace._ready_payload_sha256(handoff)
        handoff["candidate"]["payload_sha256"] = payload
        (root / "handoff.json").write_text(
            json.dumps(handoff, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        return relative_handoff, payload, evidence

    def approve_plan(
        self,
        delivery: Path,
        work_id: str,
        requirements_path: str,
        requirements_sha256: str,
        revision: int = 1,
    ) -> tuple[str, str]:
        self.transition(delivery, work_id, "planning", "awaiting_user", f"plan_{revision}_candidate")
        handoff, payload, evidence = self.ready_handoff(
            delivery,
            work_id,
            requirements_path,
            requirements_sha256,
            revision,
        )
        self.transition(
            delivery,
            work_id,
            "implementation",
            "active",
            f"plan_{revision}_approved",
            handoff_path=handoff,
            candidate_revision=f"candidate-{revision}",
            payload_sha256=payload,
            plan_approval_refs=[evidence],
        )
        return handoff, payload

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

        new_run_id = "b" * 64
        completed = self.transition(
            delivery,
            "approval-work",
            "complete",
            "complete",
            "delivery_completed",
            implementation_run_id=new_run_id,
            implementation_ledger_ref="implementation:run-b",
            implementation_status="Complete",
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
