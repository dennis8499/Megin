#!/usr/bin/env python3
"""Compatibility runner for the split delivery-orchestrator test suites."""

from __future__ import annotations

import contextlib
import json
import subprocess
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

import _delivery_git as delivery_git
import _delivery_record as delivery_record
import _delivery_test_support as support
from test_delivery_safety import DeliverySafetyTests
from test_delivery_transitions import (
    DeliveryBugOverlayTests,
    DeliveryTerminalContractTests,
    DeliveryTransitionTests,
)
from test_delivery_worktree import DeliveryWorktreeTests, UnifiedEntryAuthorizationTests


class DeliveryPerformanceTests(support.DeliveryFixture):
    def test_50k_repository_probe_transition_and_authorize_stay_under_two_seconds(self) -> None:
        primary = self.make_repo("performance-50k-project")
        blob = subprocess.run(
            ["git", "-C", str(primary), "hash-object", "-w", "--stdin"],
            input=b"fixture\n",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            shell=False,
        ).stdout.decode("ascii").strip()
        index_entries = b"".join(
            (
                f"100644 {blob}\tfixture/{index // 100:03d}/path-{index:05d}.txt\n"
            ).encode("ascii")
            for index in range(49_999)
        )
        subprocess.run(
            ["git", "-C", str(primary), "update-index", "--add", "--index-info"],
            input=index_entries,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            shell=False,
        )
        support.git(primary, "commit", "-m", "50k performance fixture")
        support.git(primary, "checkout-index", "--all", "--force")
        support.git(primary, "update-index", "--refresh")
        tracked = [
            item
            for item in support.git(primary, "ls-files", "-z").stdout.split(b"\0")
            if item
        ]
        self.assertEqual(50_000, len(tracked))

        probe_started = time.perf_counter()
        probe = support.workspace.probe_repository(primary)
        probe_elapsed = time.perf_counter() - probe_started
        self.assertTrue(probe["strict_clean"])

        work_id = "performance-50k-transition"
        delivery = Path(self.start(primary, work_id)["worktree"])
        transition_started = time.perf_counter()
        transitioned = self.transition(
            delivery,
            work_id,
            "requirements",
            "active",
            "requirements_started",
        )
        transition_elapsed = time.perf_counter() - transition_started
        authorization_started = time.perf_counter()
        authorization = support.workspace.authorize_stage(
            delivery,
            "requirements",
            root=self.registry,
            work_id=work_id,
        )
        authorization_elapsed = time.perf_counter() - authorization_started

        self.assertEqual("requirements", transitioned["phase"])
        self.assertEqual("active", transitioned["status"])
        self.assertEqual("authorized", authorization["outcome"])
        required_measurements = {
            "probe_seconds": probe_elapsed,
            "transition_seconds": transition_elapsed,
        }
        print(
            json.dumps(
                {
                    "authorization_observation_seconds": round(
                        authorization_elapsed, 6
                    ),
                    "file_count": len(tracked),
                    **{
                        name: round(duration, 6)
                        for name, duration in required_measurements.items()
                    },
                },
                sort_keys=True,
            )
        )
        self.assertEqual(
            {},
            {
                name: round(duration, 6)
                for name, duration in required_measurements.items()
                if duration >= 2.0
            },
            json.dumps(
                {
                    **required_measurements,
                    "authorization_observation_seconds": authorization_elapsed,
                },
                sort_keys=True,
            ),
        )

    def test_full_probe_and_ready_transition_stay_within_git_budgets(self) -> None:
        primary = self.make_repo("performance-project")
        commands: list[dict[str, object]] = []
        real_git = delivery_git._git
        lock_active = False

        def recording_git(
            repo: str | Path,
            arguments: list[str],
            *,
            check: bool = True,
            input_bytes: bytes | None = None,
        ) -> object:
            commands.append(
                {
                    "lock": "post" if lock_active else "pre",
                    "arguments": list(arguments),
                }
            )
            return real_git(
                repo,
                arguments,
                check=check,
                input_bytes=input_bytes,
            )

        git_patches = (
            mock.patch.object(delivery_git, "_git", side_effect=recording_git),
            mock.patch.object(delivery_record, "_git", side_effect=recording_git),
            mock.patch.object(support.workspace, "_git", side_effect=recording_git),
        )
        with git_patches[0], git_patches[1], git_patches[2]:
            probe = support.workspace.probe_repository(primary)

        self.assertTrue(probe["strict_clean"])
        full_probe_commands = list(commands)
        self.assertEqual(
            [
                "rev-parse",
                "--is-bare-repository",
                "--show-toplevel",
                "--path-format=absolute",
                "--git-common-dir",
                "HEAD",
            ],
            full_probe_commands[0]["arguments"],
        )
        self.assertEqual(
            1,
            sum(
                item["arguments"][-3:] == ["ls-files", "--stage", "-z"]
                for item in full_probe_commands
            ),
        )
        self.assertFalse(
            any(
                item["arguments"][-2:] == ["ls-files", "-z"]
                for item in full_probe_commands
            )
        )

        delivery = Path(
            self.start(primary, "performance-transition-work")["worktree"]
        )
        commands.clear()
        real_lock = support.workspace._exclusive_lock

        @contextlib.contextmanager
        def recording_lock(path: Path) -> object:
            nonlocal lock_active
            with real_lock(path):
                lock_active = True
                try:
                    yield
                finally:
                    lock_active = False

        with (
            mock.patch.object(delivery_git, "_git", side_effect=recording_git),
            mock.patch.object(delivery_record, "_git", side_effect=recording_git),
            mock.patch.object(support.workspace, "_git", side_effect=recording_git),
            mock.patch.object(
                support.workspace,
                "_exclusive_lock",
                side_effect=recording_lock,
            ),
        ):
            transitioned = self.transition(
                delivery,
                "performance-transition-work",
                "requirements",
                "active",
                "requirements_started",
            )

        self.assertEqual("requirements", transitioned["phase"])
        self.assertEqual("active", transitioned["status"])
        failures: dict[str, object] = {}
        if len(full_probe_commands) > 6:
            failures["full_probe_git_calls"] = len(full_probe_commands)
        if len(commands) > 8:
            failures["ready_transition_git_calls"] = len(commands)
        pre_lock_calls = sum(item["lock"] == "pre" for item in commands)
        if pre_lock_calls != 1:
            failures["pre_lock_git_calls"] = pre_lock_calls
        if not any(
            item["lock"] == "post" and "status" in item["arguments"]
            for item in commands
        ):
            failures["post_lock_status_probe"] = "missing"
        self.assertEqual(
            {},
            failures,
            json.dumps(
                {
                    "failures": failures,
                    "full_probe_commands": full_probe_commands,
                    "ready_transition_commands": commands,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        )


TEST_CASES = (
    DeliverySafetyTests,
    DeliveryTransitionTests,
    DeliveryBugOverlayTests,
    DeliveryTerminalContractTests,
    DeliveryWorktreeTests,
    UnifiedEntryAuthorizationTests,
    DeliveryPerformanceTests,
)


def _test_ids(suite: unittest.TestSuite) -> list[str]:
    result: list[str] = []
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            result.extend(_test_ids(item))
        else:
            result.append(item.id().removeprefix("__main__."))
    return result


def _inventory() -> dict[str, object]:
    loader = unittest.defaultTestLoader
    tests = sorted(
        {
            test_id
            for case in TEST_CASES
            for test_id in _test_ids(loader.loadTestsFromTestCase(case))
        }
    )
    bindings = [
        {"bdd_id": bdd_id, "test": f"{case.__name__}.{method}"}
        for case in TEST_CASES
        for bdd_id, method in getattr(case, "BDD_BINDINGS", {}).items()
    ]
    return {
        "schema": "delivery-test-inventory/v1",
        "discovered": len(tests),
        "tests": tests,
        "bdd_bindings": sorted(bindings, key=lambda item: item["bdd_id"]),
    }


if __name__ == "__main__":
    if sys.argv[1:] == ["--list-tests"]:
        print(json.dumps(_inventory(), ensure_ascii=False, sort_keys=True))
    else:
        unittest.main(verbosity=2)
