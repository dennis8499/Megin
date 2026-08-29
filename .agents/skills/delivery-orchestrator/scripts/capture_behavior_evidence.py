#!/usr/bin/env python3
"""Emit one reproducible clean-start hash witness from a disposable Git fixture."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


sys.dont_write_bytecode = True
TEST_SCRIPT = Path(__file__).with_name("test_delivery_workspace.py")
SPEC = importlib.util.spec_from_file_location("delivery_workspace_evidence_fixture", TEST_SCRIPT)
if SPEC is None or SPEC.loader is None:  # pragma: no cover - import infrastructure
    raise RuntimeError(f"cannot import {TEST_SCRIPT}")
fixture = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = fixture
SPEC.loader.exec_module(fixture)


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def normalized_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "head": snapshot["head"].decode("ascii").strip(),
        "symbolic_head": snapshot["symbolic_head"].decode("ascii").strip(),
        "index_sha256": snapshot["index"],
        "status_sha256": sha256(snapshot["status"]),
        "files_sha256": sha256(
            json.dumps(snapshot["files"], sort_keys=True, separators=(",", ":")).encode("utf-8")
        ),
    }


def main() -> int:
    case = fixture.DeliveryWorkspaceTests(methodName="test_clean_start_preserves_primary_and_dirty_resume")
    case.setUp()
    try:
        primary = case.make_repo("hash-witness")
        before = normalized_snapshot(fixture.primary_snapshot(primary))
        result = case.start(primary, "hash-witness-work")
        after = normalized_snapshot(fixture.primary_snapshot(primary))
        delivery = fixture.workspace.probe_repository(result["worktree"])
        record_sha256 = fixture.digest(Path(result["record_path"]))
        evidence = {
            "schema": "delivery-behavior-evidence/v1",
            "fixture": "isolated-host-temp-clean-primary",
            "primary_before": before,
            "primary_after": after,
            "primary_unchanged": before == after,
            "delivery": {
                "branch": delivery["branch"],
                "head": delivery["head_sha"],
                "strict_clean": delivery["strict_clean"],
                "registered_non_primary": not delivery["is_primary"],
            },
            "run_record_sha256": record_sha256,
        }
        print(json.dumps(evidence, ensure_ascii=False, sort_keys=True, indent=2))
        return 0 if before == after and delivery["strict_clean"] and not delivery["is_primary"] else 1
    finally:
        case.tearDown()


if __name__ == "__main__":
    raise SystemExit(main())
