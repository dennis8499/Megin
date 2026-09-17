#!/usr/bin/env python3
"""Behavior scenarios for the repository-local knowledge system."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import unittest
from unittest import mock
from pathlib import Path
from typing import Callable


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

Scenario = Callable[[Path], None]
SCENARIOS: dict[str, tuple[str, Scenario]] = {}
GROUP_SCENARIOS: dict[str, tuple[str, ...]] = {
    "retrieval": ("BDD-002", "BDD-003", "BDD-004", "BDD-005"),
    "governance": (
        "BDD-001",
        "BDD-009",
        "BDD-012",
        "BDD-013",
        "BDD-014",
        "BDD-015",
        "BDD-017",
    ),
    "promotion": ("BDD-006", "BDD-007", "BDD-013"),
    "delivery": ("BDD-008", "BDD-010", "BDD-011", "BDD-016"),
    "performance": ("BDD-018", "BDD-020"),
    "presentation": ("BDD-021", "BDD-022", "BDD-023", "BDD-024", "BDD-025"),
    "maintenance": ("BDD-026", "BDD-027", "BDD-028", "BDD-029", "BDD-030", "BDD-031"),
    "workflow-speed": (
        "BDD-101",
        "BDD-102",
        "BDD-103",
        "BDD-201",
        "BDD-202",
        "BDD-203",
        "BDD-301",
        "BDD-302",
        "BDD-401",
        "BDD-501",
    ),
}
OCCURRENCE_REASON_SENTINEL = "OCCURRENCE_REASON_SENTINEL_BDD_023_742ac129"
SEQUENTIAL_PERFORMANCE_SCENARIOS = frozenset({"BDD-016", "BDD-018", "BDD-020"})
RELEASE_ONLY_SCENARIOS = frozenset({"BDD-016"})
_WINDOWS = os.name == "nt"


def scenario(identifier: str, group: str) -> Callable[[Scenario], Scenario]:
    def register(function: Scenario) -> Scenario:
        SCENARIOS[identifier] = (group, function)
        return function

    return register


def functional_shard_scenarios(index: int, count: int) -> list[str]:
    """Return one deterministic, disjoint shard of all non-performance scenarios."""

    if count < 1 or count > 16 or index < 1 or index > count:
        raise ValueError("functional shard must be INDEX/TOTAL with 1 <= INDEX <= TOTAL <= 16")
    functional = [
        identifier
        for identifier in SCENARIOS
        if identifier not in SEQUENTIAL_PERFORMANCE_SCENARIOS
    ]
    return functional[index - 1 :: count]


def validation_profile_scenarios(
    selected: list[str], profile: str | None
) -> list[str]:
    """Keep hosted/cross-platform obligations in release and legacy runs."""

    if profile not in {None, "local", "release"}:
        raise ValueError("validation profile must be local or release")
    if profile == "local":
        return [
            identifier
            for identifier in selected
            if identifier not in RELEASE_ONLY_SCENARIOS
        ]
    return list(selected)


def _functional_shard(value: str) -> tuple[int, int]:
    matched = re.fullmatch(r"([1-9][0-9]*)/([1-9][0-9]*)", value)
    if matched is None:
        raise argparse.ArgumentTypeError("functional shard must use INDEX/TOTAL")
    index, count = (int(part) for part in matched.groups())
    try:
        functional_shard_scenarios(index, count)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc
    return index, count


@scenario("BDD-101", "workflow-speed")
def full_suite_coverage_executes_each_physical_child_once(fixture_root: Path) -> None:
    del fixture_root
    focused = (
        Path.cwd()
        / ".agents/skills/implementation-execution/scripts/test_validation_evidence.py"
    )
    assert focused.is_file(), "validation evidence focused tests are absent"
    completed = subprocess.run(
        [
            sys.executable,
            "-X",
            "utf8",
            "-B",
            str(focused),
            "CoverageAndBundleTests.test_full_suite_coverage_executes_each_child_once",
        ],
        cwd=Path.cwd(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        shell=False,
    )
    assert completed.returncode == 0, completed.stderr.decode(
        "utf-8", errors="replace"
    )


@scenario("BDD-102", "workflow-speed")
def partial_coverage_and_validation_profiles_remain_separate(
    fixture_root: Path,
) -> None:
    del fixture_root
    schema_path = (
        Path.cwd()
        / ".agents/skills/technical-planning/references/ready-plan.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert "validation" in schema["properties"], (
        "ready-plan/v1 has no additive validation capability"
    )
    commands = (
        (
            ".agents/skills/implementation-execution/scripts/test_validation_evidence.py",
            "CoverageAndBundleTests.test_partial_coverage_runs_only_the_missing_obligation",
        ),
        (
            ".agents/skills/technical-planning/scripts/test_validate_contracts.py",
            "ValidationProfileContractTests",
        ),
    )
    for script, selected in commands:
        completed = subprocess.run(
            [sys.executable, "-X", "utf8", "-B", script, selected],
            cwd=Path.cwd(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            shell=False,
        )
        assert completed.returncode == 0, completed.stderr.decode(
            "utf-8", errors="replace"
        )


@scenario("BDD-103", "workflow-speed")
def validation_bundles_are_atomic_and_fail_closed_on_drift(
    fixture_root: Path,
) -> None:
    del fixture_root
    implementation = (
        Path.cwd()
        / ".agents/skills/implementation-execution/scripts/validation_evidence.py"
    )
    source = implementation.read_text(encoding="utf-8")
    assert "def write_bundle(" in source, "atomic evidence bundle seam is absent"
    runner_source = (
        Path.cwd()
        / ".agents/skills/project-knowledge/scripts/run_full_suite.py"
    ).read_text(encoding="utf-8")
    for option in ("--profile", "--jobs", "--evidence-root"):
        assert option in runner_source, f"full-suite runner lacks {option}"
    completed = subprocess.run(
        [
            sys.executable,
            "-X",
            "utf8",
            "-B",
            ".agents/skills/implementation-execution/scripts/test_validation_evidence.py",
            "CoverageAndBundleTests.test_atomic_bundle_and_reference_fail_closed",
        ],
        cwd=Path.cwd(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        shell=False,
    )
    assert completed.returncode == 0, completed.stderr.decode(
        "utf-8", errors="replace"
    )


def _run_review_pipeline_scenario(selected: str) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-X",
            "utf8",
            "-B",
            ".agents/skills/implementation-execution/scripts/test_validation_evidence.py",
            selected,
        ],
        cwd=Path.cwd(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        shell=False,
    )
    assert completed.returncode == 0, completed.stderr.decode(
        "utf-8", errors="replace"
    )


@scenario("BDD-201", "workflow-speed")
def blocking_review_precheck_stops_expensive_commands(fixture_root: Path) -> None:
    del fixture_root
    _run_review_pipeline_scenario(
        "ReviewPipelineTests.test_blocking_precheck_aggregates_findings_without_running_commands"
    )


@scenario("BDD-202", "workflow-speed")
def final_review_reuses_only_verified_terminal_additions(fixture_root: Path) -> None:
    del fixture_root
    _run_review_pipeline_scenario(
        "ReviewPipelineTests.test_preliminary_executes_and_final_references_terminal_only_additions"
    )


@scenario("BDD-203", "workflow-speed")
def review_input_drift_requires_fresh_execution(fixture_root: Path) -> None:
    del fixture_root
    _run_review_pipeline_scenario(
        "ReviewPipelineTests.test_reuse_requires_fresh_execution_for_every_nonterminal_drift_class"
    )


@scenario("BDD-301", "workflow-speed")
def rendered_review_and_archive_are_deterministic(fixture_root: Path) -> None:
    del fixture_root
    _run_review_pipeline_scenario(
        "EvidenceOperationsTests.test_render_and_archive_are_deterministic_and_fail_closed"
    )


@scenario("BDD-302", "workflow-speed")
def activity_metrics_and_benchmark_use_complete_samples(fixture_root: Path) -> None:
    del fixture_root
    _run_review_pipeline_scenario(
        "EvidenceOperationsTests.test_activity_categories_and_benchmark_threshold"
    )


@scenario("BDD-401", "workflow-speed")
def chinese_workflow_questions_return_owner_contracts(fixture_root: Path) -> None:
    del fixture_root
    completed = subprocess.run(
        [
            sys.executable,
            "-X",
            "utf8",
            "-B",
            ".agents/skills/project-knowledge/scripts/test_query.py",
            "ChineseWorkflowQueryTests",
        ],
        cwd=Path.cwd(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        shell=False,
    )
    assert completed.returncode == 0, completed.stderr.decode(
        "utf-8", errors="replace"
    )


@scenario("BDD-501", "workflow-speed")
def parallel_workers_are_isolated_and_profiled(fixture_root: Path) -> None:
    del fixture_root
    completed = subprocess.run(
        [
            sys.executable,
            "-X",
            "utf8",
            "-B",
            ".agents/skills/delivery-orchestrator/scripts/test_delivery_workspace.py",
            "WorkflowSpeedFixtureTests",
        ],
        cwd=Path.cwd(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        shell=False,
    )
    assert completed.returncode == 0, completed.stderr.decode(
        "utf-8", errors="replace"
    )


@scenario("BDD-026", "maintenance")
def ci_changes_use_a_fast_gate_before_the_cross_platform_matrix(
    fixture_root: Path,
) -> None:
    del fixture_root
    workflow = (Path.cwd() / ".github/workflows/knowledge-portability.yml").read_text(
        encoding="utf-8"
    )
    assert '".agents/skills/**"' in workflow
    assert '"docs/**"' in workflow
    assert '".gitattributes"' in workflow
    assert '"README.md"' in workflow
    assert '"OPERATIONS.md"' in workflow
    assert re.search(r"(?m)^  quick:\s*$", workflow)
    assert re.search(r"(?ms)^  platform:.*?needs: quick", workflow)
    assert "run_quick_checks.py" in workflow
    quick_runner = (
        Path.cwd()
        / ".agents/skills/project-knowledge/scripts/run_quick_checks.py"
    ).read_text(encoding="utf-8")
    assert "QUICK-DOCUMENTATION" in quick_runner
    assert "DocumentationAndCiImprovementTests" in quick_runner


@scenario("BDD-027", "maintenance")
def maintainers_have_one_documented_entrypoint_for_operations(
    fixture_root: Path,
) -> None:
    repo = Path.cwd()
    readme = repo / "README.md"
    operations = repo / "OPERATIONS.md"
    assert readme.is_file()
    assert operations.is_file()
    combined = readme.read_text(encoding="utf-8") + operations.read_text(
        encoding="utf-8"
    )
    for fragment in (
        "delivery_workspace.py probe",
        "run_full_suite.py --scope all",
        "stage-authorization.md",
        ".knowledge-test-tmp/final-metrics.json",
        "human gate",
    ):
        assert fragment in combined
    completed = subprocess.run(
        [
            sys.executable,
            "-X",
            "utf8",
            "-B",
            ".agents/skills/project-knowledge/scripts/test_workflow.py",
            "DocumentationAndCiImprovementTests",
            "--fixture-root",
            str(fixture_root),
        ],
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        shell=False,
    )
    assert completed.returncode == 0, completed.stderr.decode(
        "utf-8", errors="replace"
    )


@scenario("BDD-028", "maintenance")
def delivery_transitions_are_routed_through_explicit_phase_handlers(
    fixture_root: Path,
) -> None:
    del fixture_root
    completed = subprocess.run(
        [
            sys.executable,
            "-X",
            "utf8",
            "-B",
            ".agents/skills/delivery-orchestrator/scripts/test_delivery_workspace.py",
            "DeliveryTransitionArchitectureTests",
        ],
        cwd=Path.cwd(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        shell=False,
    )
    assert completed.returncode == 0, completed.stderr.decode(
        "utf-8", errors="replace"
    )


@scenario("BDD-029", "maintenance")
def unsupported_schema_rules_fail_closed_without_misreading_property_names(
    fixture_root: Path,
) -> None:
    del fixture_root
    completed = subprocess.run(
        [
            sys.executable,
            "-X",
            "utf8",
            "-B",
            ".agents/skills/technical-planning/scripts/test_validate_contracts.py",
            "SchemaSubsetContractTests",
        ],
        cwd=Path.cwd(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        shell=False,
    )
    assert completed.returncode == 0, completed.stderr.decode(
        "utf-8", errors="replace"
    )


@scenario("BDD-030", "maintenance")
def delivery_doctor_explains_resume_blockers_without_writing(
    fixture_root: Path,
) -> None:
    del fixture_root
    completed = subprocess.run(
        [
            sys.executable,
            "-X",
            "utf8",
            "-B",
            ".agents/skills/delivery-orchestrator/scripts/test_delivery_workspace.py",
            "DeliveryDoctorTests",
        ],
        cwd=Path.cwd(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        shell=False,
    )
    assert completed.returncode == 0, completed.stderr.decode(
        "utf-8", errors="replace"
    )


@scenario("BDD-031", "maintenance")
def suite_metrics_and_search_quality_are_independent_and_reproducible(
    fixture_root: Path,
) -> None:
    del fixture_root
    completed = subprocess.run(
        [
            sys.executable,
            "-X",
            "utf8",
            "-B",
            ".agents/skills/project-knowledge/scripts/test_workflow.py",
            "SuiteMetricsTests",
            "SearchQualityBaselineTests",
        ],
        cwd=Path.cwd(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        shell=False,
    )
    assert completed.returncode == 0, completed.stderr.decode(
        "utf-8", errors="replace"
    )


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _write(path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = text.replace("\r\n", "\n").encode("utf-8")
    path.write_bytes(encoded)
    return _sha256(encoded)


def _ready_plan_bundle(repo: Path, work_id: str, plan_text: str) -> list[dict[str, str]]:
    """Build a producer-valid Ready-plan bundle with exact postimage hashes."""

    fixture_path = (
        SCRIPT_DIR.parents[1]
        / "technical-planning"
        / "scripts"
        / "_ready_fixture.py"
    )
    spec = importlib.util.spec_from_file_location("knowledge_test_ready_fixture", fixture_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load Ready-plan fixture: {fixture_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    ready = module.ready_example()
    bundle_root = f"docs/work/{work_id}/plan"
    primary_path = f"{bundle_root}/plan.md"
    supporting_path = f"{bundle_root}/architecture.md"
    occurrence_path = f"{bundle_root}/occurrence_map.yaml"
    handoff_path = f"{bundle_root}/handoff.json"
    supporting_text = "# Architecture\n\nThe bundle is promoted as one atomic revision.\n"
    occurrence_text = (
        "schema: occurrence-map/v1\n"
        "change_mode: bulk_edit\n"
        f"reason: {OCCURRENCE_REASON_SENTINEL}\n"
        "categories:\n"
        "  serialized_keys:\n"
        "    action: manual_review\n"
        "  import_paths:\n"
        "    action: do_not_change\n"
        "exceptions:\n"
        "  - paths: docs/work/**\n"
        "    action: 'manual_review' # explicit exception classification\n"
    )
    requirements_path = f"docs/work/{work_id}/requirements.md"
    requirements_raw = (repo / Path(*requirements_path.split("/"))).read_bytes()
    ready["primary_plan"] = {
        "path": primary_path,
        "sha256": _sha256(plan_text.encode("utf-8")),
    }
    ready["artifacts"] = [
        {
            "path": primary_path,
            "role": "primary",
            "approval_status": "Ready",
            "sha256": _sha256(plan_text.encode("utf-8")),
        },
        {
            "path": supporting_path,
            "role": "supporting",
            "approval_status": "Ready",
            "sha256": _sha256(supporting_text.encode("utf-8")),
        },
        {
            "path": occurrence_path,
            "role": "supporting",
            "approval_status": "Ready",
            "sha256": _sha256(occurrence_text.encode("utf-8")),
        },
        {
            "path": handoff_path,
            "role": "handoff",
            "approval_status": "Ready",
            "sha256": None,
        },
    ]
    ready["sources"][0]["location"] = requirements_path
    ready["sources"][0]["sha256"] = _sha256(requirements_raw)
    ready["candidate"]["payload_sha256"] = module.validator.ready_payload_sha256(ready)
    handoff_text = json.dumps(ready, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    return [
        {"path": primary_path, "postimage": plan_text},
        {"path": supporting_path, "postimage": supporting_text},
        {"path": occurrence_path, "postimage": occurrence_text},
        {"path": handoff_path, "postimage": handoff_text},
    ]


def _prepare_bound_implementation_run(
    run_root: Path,
    implementation_run_id: str,
    additional_command_ids: list[str],
) -> tuple[dict[str, object], list[str]]:
    """Write the Ready handoff bound by the preliminary review fixture's run Ledger."""

    fixture_path = (
        SCRIPT_DIR.parents[1]
        / "technical-planning"
        / "scripts"
        / "_ready_fixture.py"
    )
    spec = importlib.util.spec_from_file_location(
        "knowledge_test_bound_ready_fixture",
        fixture_path,
    )
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load Ready-plan fixture: {fixture_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    ready = module.ready_example()
    known_commands = {item["command_id"] for item in ready["commands"]}
    for command_id in additional_command_ids:
        if command_id in known_commands:
            continue
        template = next(
            item for item in ready["commands"] if item["purpose"] == "related"
        )
        command = json.loads(json.dumps(template))
        command["command_id"] = command_id
        command["command"] = f"tool {command_id.casefold()}"
        ready["commands"].append(command)
        ready["contract_index"].append(
            {
                "contract_id": command_id,
                "kind": "command",
                "source_refs": ["SRC-001"],
                "wp_refs": ["WP-001"],
            }
        )
        ready["work_packages"][0]["contract_refs"].append(command_id)
        ready["work_packages"][0]["command_refs"].append(command_id)
        known_commands.add(command_id)
    ready["candidate"]["payload_sha256"] = module.validator.ready_payload_sha256(ready)

    canonical_worktree = run_root / "canonical-worktree"
    handoff_relative = "docs/plans/example/handoff.json"
    handoff_path = canonical_worktree / Path(*handoff_relative.split("/"))
    _write(
        handoff_path,
        json.dumps(ready, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
    )
    run_record = {
        "schema": "implementation-ledger/v1",
        "run_id": implementation_run_id,
        "binding": {
            "canonical_worktree": str(canonical_worktree),
            "run_id": implementation_run_id,
        },
        "handoff_path": handoff_relative,
    }
    _write(
        run_root / "run.json",
        json.dumps(run_record, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
    )
    required_review_commands = [
        item["command_id"]
        for item in ready["commands"]
        if item["purpose"] in {"bdd-full", "build-full", "test-full"}
    ]
    review_commands = list(
        dict.fromkeys([*additional_command_ids, *required_review_commands])
    )
    return ready, review_commands


def _persist_preliminary_review_fixture(
    *,
    implementation_run_id: str,
    logical_ref: str,
    command_ids: list[str],
    round_number: int = 1,
) -> tuple[dict[str, object], dict[str, str]]:
    """Persist a schema-valid, read-only preliminary review under the patched host temp."""

    import knowledge_outcome

    run_root = (
        Path(knowledge_outcome.tempfile.gettempdir())
        / "implementation-execution"
        / "runs"
        / implementation_run_id
    )
    run_root.mkdir(parents=True, exist_ok=True)
    _, review_command_ids = _prepare_bound_implementation_run(
        run_root,
        implementation_run_id,
        command_ids,
    )
    slug = logical_ref.rsplit(":", 1)[-1]
    report_ref = f"reviews/{slug}/report.json"
    output_refs = {
        command_id: f"reviews/{slug}/outputs/{index:04d}.txt"
        for index, command_id in enumerate(review_command_ids, 1)
    }
    report = {
        "schema": "implementation-review/v1",
        "logical_ref": logical_ref,
        "round": round_number,
        "verdict": "APPROVED",
        "snapshot_before": "a" * 64,
        "snapshot_after": "a" * 64,
        "attestation": {
            "agent_id": "fresh-review-fixture",
            "fresh_session": True,
            "read_only": True,
            "implementation_conversation_received": False,
            "delegation_used": False,
            "write_actions": False,
        },
        "command_outcomes": [
            {
                "command_id": command_id,
                "outcome": "passed",
                "exit_code": 0,
                "failure_count": 0,
                "skipped_count": 0,
                "output_ref": output_refs[command_id],
                "not_run_reason": None,
            }
            for command_id in review_command_ids
        ],
        "raw_output_refs": list(output_refs.values()),
        "requirement_coverage": [
            {
                "source_ref": "SRC-001",
                "obligation_ref": "REQ-001",
                "bdd_refs": ["BDD-001"],
                "test_refs": ["TEST-001"],
                "wp_refs": ["WP-001"],
                "code_evidence": ["src/change.md:1"],
                "result": "covered",
            }
        ],
        "findings": [],
        "summary": "Fresh preliminary review approved the verified product snapshot.",
    }
    persisted = knowledge_outcome.persist_preliminary_review_report(
        implementation_run_id=implementation_run_id,
        report_ref=report_ref,
        report=report,
        raw_outputs={
            relative: f"{command_id}: passed\n"
            for command_id, relative in output_refs.items()
        },
    )
    review = {
        "verdict": "APPROVED",
        "evidence_refs": [logical_ref],
        "report_ref": persisted["report_ref"],
        "report_sha256": persisted["report_sha256"],
    }
    return review, output_refs


def _git(repo: Path, *arguments: str) -> None:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        raise AssertionError(
            f"git {' '.join(arguments)} failed: "
            f"{completed.stderr.decode('utf-8', errors='replace')}"
        )


def _tree_snapshot(repo: Path) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    for path in sorted(repo.rglob("*"), key=lambda item: item.as_posix().encode("utf-8")):
        relative = path.relative_to(repo)
        if (
            ".git" in relative.parts
            or relative.parts[:1] == (".knowledge-test-tmp",)
            or not path.is_file()
        ):
            continue
        snapshot[relative.as_posix()] = _sha256(path.read_bytes())
    return snapshot


def _remove_fixture(root: Path) -> None:
    resolved = root.resolve(strict=False)
    workspace = Path.cwd().resolve()
    approved_root = (workspace / ".knowledge-test-tmp").resolve(strict=False)
    worker_value = os.environ.get("KNOWLEDGE_TEST_WORKER_ROOT")
    if worker_value:
        approved: set[Path] = set()
        worker_root = Path(worker_value).resolve(strict=False)
        try:
            worker_root.relative_to(approved_root)
        except ValueError:
            pass
        else:
            approved.add((worker_root / "fixture").resolve(strict=False))
    else:
        approved = {approved_root}
    if resolved not in approved:
        raise AssertionError(f"fixture root is outside the approved path: {resolved}")
    if not resolved.exists():
        return

    if _WINDOWS:
        def make_writable_and_retry(
            function: Callable[..., object],
            path: str,
            _: object,
        ) -> None:
            os.chmod(path, stat.S_IWRITE)
            function(path)

        os.chmod(resolved, stat.S_IWRITE)
        shutil.rmtree(resolved, onexc=make_writable_and_retry)
    else:
        shutil.rmtree(resolved)
    if resolved.exists():
        raise AssertionError(f"fixture cleanup failed: {resolved}")


def _page_sidecar(
    *,
    page_id: str,
    content_path: str,
    content_sha256: str,
    title: str,
    lifecycle: str,
    claim_id: str,
    source_path: str,
    source_sha256: str,
    excerpt_sha256: str,
) -> dict[str, object]:
    return {
        "schema": "knowledge-page/v1",
        "page_id": page_id,
        "content_path": content_path,
        "content_sha256": content_sha256,
        "title": title,
        "aliases": ["能力權杖"],
        "tags": ["requirements", "security"],
        "lifecycle": lifecycle,
        "claims": [
            {
                "claim_id": claim_id,
                "evidence_class": "observed",
                "lifecycle": lifecycle,
                "content_anchor": "capability-token-boundary",
                "source_refs": [
                    {
                        "path": source_path,
                        "sha256": source_sha256,
                        "locator": {"start_line": 1, "end_line": 1},
                        "excerpt_sha256": excerpt_sha256,
                    }
                ],
                "supersedes": [],
                "contradicts": [],
            }
        ],
        "backlinks": [],
    }


def _build_retrieval_fixture(
    root: Path,
    *,
    stale_advice_lifecycle: str = "current",
) -> Path:
    if stale_advice_lifecycle not in {"current", "stale"}:
        raise ValueError("stale advice lifecycle must be current or stale")
    _remove_fixture(root)
    repo = root / "bdd-004"
    repo.mkdir(parents=True)
    _git(repo, "init", "-q")

    source_text = "Capability tokens define the authorization boundary.\n"
    source_sha = _write(repo / "src/security-boundary.md", source_text)
    excerpt_sha = _sha256(source_text.rstrip("\n").encode("utf-8"))

    current_text = (
        "# Capability Token Boundary\n\n"
        "## capability-token-boundary\n\n"
        "Capability tokens define the authorization boundary.\n"
    )
    current_path = "docs/knowledge/security/capability-token.md"
    current_sha = _write(repo / current_path, current_text)
    current_sidecar = _page_sidecar(
        page_id="page-security-capability-token",
        content_path=current_path,
        content_sha256=current_sha,
        title="Capability Token Boundary",
        lifecycle="current",
        claim_id="claim-security-capability-token",
        source_path="src/security-boundary.md",
        source_sha256=source_sha,
        excerpt_sha256=excerpt_sha,
    )
    _write(
        repo / "docs/knowledge/meta/pages/page-security-capability-token.json",
        json.dumps(current_sidecar, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
    )

    stale_source_text = "Never use capability tokens.\n"
    stale_source_sha = _write(repo / "src/stale-boundary.md", stale_source_text)
    stale_text = "# Stale Capability Token Advice\n\nNever use capability tokens.\n"
    stale_path = "docs/knowledge/incidents/stale-capability-token.md"
    stale_sha = _write(repo / stale_path, stale_text)
    stale_sidecar = _page_sidecar(
        page_id="page-stale-capability-token",
        content_path=stale_path,
        content_sha256=stale_sha,
        title="Stale Capability Token Advice",
        lifecycle=stale_advice_lifecycle,
        claim_id="claim-stale-capability-token",
        source_path="src/stale-boundary.md",
        source_sha256=stale_source_sha,
        excerpt_sha256=_sha256(stale_source_text.rstrip("\n").encode("utf-8")),
    )
    _write(
        repo / "docs/knowledge/meta/pages/page-stale-capability-token.json",
        json.dumps(stale_sidecar, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
    )

    _write(repo / ".gitignore", "ignored/\n")
    _write(repo / "ignored/secret.md", "Capability token password should never be indexed.\n")
    _git(repo, "add", ".")
    return repo


def _build_query_performance_fixture(root: Path) -> Path:
    """Build a stable audit shape that exercises multi-batch sidecar lookup."""

    _remove_fixture(root)
    repo = root / "query-performance"
    repo.mkdir(parents=True)
    _git(repo, "init", "-q")

    phrase = "violet cedar ember quartz"
    source_refs: list[dict[str, object]] = []
    for index in range(65):
        source_path = f"evidence/source-{index:03d}.md"
        source_text = f"{phrase} source {index:03d}.\n"
        source_refs.append(
            {
                "path": source_path,
                "sha256": _write(repo / source_path, source_text),
                "locator": {"start_line": 1, "end_line": 1},
                "excerpt_sha256": _sha256(source_text.rstrip("\n").encode("utf-8")),
            }
        )

    content_path = "docs/knowledge/topics/session.md"
    content_text = (
        "# Session\n\n"
        "## session\n\n"
        f"{phrase} canonical.\n"
    )
    sidecar = _page_sidecar(
        page_id="page-session",
        content_path=content_path,
        content_sha256=_write(repo / content_path, content_text),
        title="Session",
        lifecycle="current",
        claim_id="claim-session",
        source_path=str(source_refs[0]["path"]),
        source_sha256=str(source_refs[0]["sha256"]),
        excerpt_sha256=str(source_refs[0]["excerpt_sha256"]),
    )
    sidecar["aliases"] = []
    sidecar["tags"] = ["implementation"]
    sidecar["claims"][0]["content_anchor"] = "session"
    sidecar["claims"][0]["source_refs"] = source_refs
    _write(
        repo / "docs/knowledge/meta/pages/page-session.json",
        json.dumps(sidecar, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
    )
    _git(repo, "add", ".")
    return repo


def _build_golden_fixture(root: Path) -> tuple[Path, list[tuple[str, str]]]:
    _remove_fixture(root)
    repo = root / "golden"
    repo.mkdir(parents=True)
    _git(repo, "init", "-q")
    cases: list[tuple[str, str]] = []
    for index in range(20):
        title = f"Golden Engineering Topic {index:02d}"
        alias = f"黃金工程主題{index:02d}"
        claim_id = f"claim-golden-topic-{index:02d}"
        content_path = f"docs/knowledge/topics/golden-{index:02d}.md"
        source_path = f"evidence/golden-{index:02d}.md"
        source_text = f"{title} establishes verified boundary number {index:02d}.\n"
        source_sha = _write(repo / source_path, source_text)
        content = (
            f"# {title}\n\n"
            f"## golden-topic-{index:02d}\n\n"
            f"{title} establishes verified boundary number {index:02d}.\n"
        )
        content_sha = _write(repo / content_path, content)
        page = {
            "schema": "knowledge-page/v1",
            "page_id": f"page-golden-topic-{index:02d}",
            "content_path": content_path,
            "content_sha256": content_sha,
            "title": title,
            "aliases": [alias],
            "tags": ["requirements", f"topic-{index:02d}"],
            "lifecycle": "current",
            "claims": [
                {
                    "claim_id": claim_id,
                    "evidence_class": "verified",
                    "lifecycle": "current",
                    "content_anchor": f"golden-topic-{index:02d}",
                    "source_refs": [
                        {
                            "path": source_path,
                            "sha256": source_sha,
                            "locator": {"start_line": 1, "end_line": 1},
                            "excerpt_sha256": _sha256(source_text.rstrip("\n").encode("utf-8")),
                        }
                    ],
                    "supersedes": [],
                    "contradicts": [],
                }
            ],
            "backlinks": [],
        }
        _write(
            repo / f"docs/knowledge/meta/pages/page-golden-topic-{index:02d}.json",
            json.dumps(page, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        )
        query = title if index < 8 else alias if index < 14 else claim_id
        cases.append((query, content_path))

    stale_path = "docs/knowledge/incidents/stale-golden.md"
    stale_text = "# 黃金工程主題08\n\nThis stale page must never rank.\n"
    stale_sha = _write(repo / stale_path, stale_text)
    stale_source = "evidence/stale-golden.md"
    stale_source_text = "Stale source.\n"
    stale_source_sha = _write(repo / stale_source, stale_source_text)
    stale = {
        "schema": "knowledge-page/v1",
        "page_id": "page-stale-golden",
        "content_path": stale_path,
        "content_sha256": stale_sha,
        "title": "黃金工程主題08",
        "aliases": [],
        "tags": ["requirements"],
        "lifecycle": "stale",
        "claims": [
            {
                "claim_id": "claim-stale-golden",
                "evidence_class": "observed",
                "lifecycle": "stale",
                "content_anchor": "stale",
                "source_refs": [
                    {
                        "path": stale_source,
                        "sha256": stale_source_sha,
                        "locator": {"start_line": 1, "end_line": 1},
                        "excerpt_sha256": _sha256(stale_source_text.rstrip("\n").encode("utf-8")),
                    }
                ],
                "supersedes": [],
                "contradicts": [],
            }
        ],
        "backlinks": [],
    }
    _write(
        repo / "docs/knowledge/meta/pages/page-stale-golden.json",
        json.dumps(stale, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
    )
    _write(repo / ".gitignore", "ignored/\n")
    _write(repo / "ignored/golden-secret.md", "Golden Engineering Topic 00 secret.\n")
    _git(repo, "add", ".")
    return repo, cases


def _build_governance_fixture(root: Path) -> Path:
    _remove_fixture(root)
    repo = root / "governance"
    repo.mkdir(parents=True)
    _git(repo, "init", "-q")
    _write(
        repo / "docs/work/work-alpha/requirements.md",
        "# Approved requirements\n\nStatus: Ready\n\nConfirmed by: requirements-owner\n\n"
        "Require auditable citations.\n",
    )
    _write(
        repo / "docs/work/work-alpha/plan/plan.md",
        "# Draft plan\n\nStatus: Candidate\n\nThis is not terminal.\n",
    )
    _write(
        repo / "docs/legacy/status.json",
        json.dumps({"schema": "legacy-status/v1", "status": "Ready"}, indent=2) + "\n",
    )
    _write(
        repo / "docs/legacy/status.md",
        "# Legacy status\n\nStatus: Candidate\n",
    )
    _write(
        repo / "docs/telemetry/status.json",
        json.dumps({"schema": "telemetry/v1", "status": "Ready"}, indent=2) + "\n",
    )
    _git(repo, "add", ".")
    return repo


def _build_contradiction_fixture(root: Path) -> Path:
    _remove_fixture(root)
    repo = root / "contradiction"
    repo.mkdir(parents=True)
    _git(repo, "init", "-q")
    definitions = [
        (
            "alpha",
            "Storage quorum requires three replicas.\n",
            "claim-storage-quorum-three",
            "claim-storage-quorum-two",
        ),
        (
            "beta",
            "Storage quorum requires two replicas.\n",
            "claim-storage-quorum-two",
            "claim-storage-quorum-three",
        ),
    ]
    for name, statement, claim_id, contradiction in definitions:
        source_path = f"evidence/{name}.md"
        source_sha = _write(repo / source_path, statement)
        content_path = f"docs/knowledge/decisions/quorum-{name}.md"
        content = f"# Storage Quorum {name.title()}\n\n## quorum\n\n{statement}"
        content_sha = _write(repo / content_path, content)
        sidecar = {
            "schema": "knowledge-page/v1",
            "page_id": f"page-storage-quorum-{name}",
            "content_path": content_path,
            "content_sha256": content_sha,
            "title": f"Storage Quorum {name.title()}",
            "aliases": ["storage quorum"],
            "tags": ["planning"],
            "lifecycle": "current",
            "claims": [
                {
                    "claim_id": claim_id,
                    "evidence_class": "observed",
                    "lifecycle": "current",
                    "content_anchor": "quorum",
                    "source_refs": [
                        {
                            "path": source_path,
                            "sha256": source_sha,
                            "locator": {"start_line": 1, "end_line": 1},
                            "excerpt_sha256": _sha256(statement.rstrip("\n").encode("utf-8")),
                        }
                    ],
                    "supersedes": [],
                    "contradicts": [contradiction],
                }
            ],
            "backlinks": [],
        }
        _write(
            repo / f"docs/knowledge/meta/pages/page-storage-quorum-{name}.json",
            json.dumps(sidecar, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        )
    _write(
        repo / "docs/knowledge/index.md",
        "# Knowledge Index\n\n"
        "- [Storage Quorum Alpha](docs/knowledge/decisions/quorum-alpha.md) — "
        "`page-storage-quorum-alpha` — `current`\n"
        "- [Storage Quorum Beta](docs/knowledge/decisions/quorum-beta.md) — "
        "`page-storage-quorum-beta` — `current`\n",
    )
    _git(repo, "add", ".")
    return repo


def _build_complete_lint_fixture(root: Path) -> Path:
    """Build one repository containing every required lint failure family."""

    _remove_fixture(root)
    repo = root / "complete-lint"
    repo.mkdir(parents=True)
    _git(repo, "init", "-q")

    shared_source = "Shared evidence remains auditable.\n"
    shared_source_sha = _write(repo / "evidence/shared.md", shared_source)
    shared_excerpt_sha = _sha256(shared_source.rstrip("\n").encode("utf-8"))
    drift_source = "Drift evidence changed after promotion.\n"
    _write(repo / "evidence/drift.md", drift_source)
    drift_excerpt_sha = _sha256(drift_source.rstrip("\n").encode("utf-8"))

    provenance_path = "docs/knowledge/topics/provenance.md"
    provenance_text = (
        "# Provenance Rules\n\n"
        "## provenance\n\n"
        "Every current claim needs verifiable raw evidence.\n"
    )
    provenance_sha = _write(repo / provenance_path, provenance_text)
    provenance_page = {
        "schema": "knowledge-page/v1",
        "page_id": "page-duplicate-lint",
        "content_path": provenance_path,
        "content_sha256": provenance_sha,
        "title": "Provenance Rules",
        "aliases": [],
        "tags": ["governance"],
        "lifecycle": "current",
        "claims": [
            {
                "claim_id": "claim-no-provenance",
                "evidence_class": "observed",
                "lifecycle": "current",
                "content_anchor": "provenance",
                "source_refs": [],
                "supersedes": [],
                "contradicts": [],
            },
            {
                "claim_id": "claim-stale-source",
                "evidence_class": "observed",
                "lifecycle": "current",
                "content_anchor": "provenance",
                "source_refs": [
                    {
                        "path": "evidence/drift.md",
                        "sha256": "0" * 64,
                        "locator": {"start_line": 1, "end_line": 1},
                        "excerpt_sha256": drift_excerpt_sha,
                    }
                ],
                "supersedes": [],
                "contradicts": [],
            },
        ],
        "backlinks": ["docs/knowledge/topics/missing.md"],
    }
    _write(
        repo / "docs/knowledge/meta/pages/page-provenance.json",
        json.dumps(provenance_page, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
    )

    state_path = "docs/knowledge/topics/state.md"
    state_text = "# Lifecycle State\n\n## lifecycle\n\nStates are closed vocabulary.\n"
    state_sha = _write(repo / state_path, state_text)
    state_page = {
        "schema": "knowledge-page/v1",
        "page_id": "page-duplicate-lint",
        "content_path": state_path,
        "content_sha256": state_sha,
        "title": "Lifecycle State",
        "aliases": [],
        "tags": ["governance"],
        "lifecycle": "invalid-state",
        "claims": [
            {
                "claim_id": "claim-illegal-state",
                "evidence_class": "observed",
                "lifecycle": "invalid-state",
                "content_anchor": "lifecycle",
                "source_refs": [
                    {
                        "path": "evidence/shared.md",
                        "sha256": shared_source_sha,
                        "locator": {"start_line": 1, "end_line": 1},
                        "excerpt_sha256": shared_excerpt_sha,
                    }
                ],
                "supersedes": [],
                "contradicts": ["claim-absent"],
            }
        ],
        "backlinks": [],
    }
    _write(
        repo / "docs/knowledge/meta/pages/page-state.json",
        json.dumps(state_page, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
    )

    _write(
        repo / "docs/knowledge/topics/orphan.md",
        "# Orphan\n\nNo sidecar references this page.\n",
    )
    _write(repo / "docs/knowledge/index.md", "# Incorrect index\n")
    receipt = {
        "schema": "knowledge-promotion/v1",
        "promotion_id": "promotion-fixture-ready",
        "stage": "implementation",
        "work_id": "work-fixture-ready",
        "candidate_ref": "knowledge:candidates/promotion-fixture-ready/candidate.json",
        "payload_sha256": "a" * 64,
        "decision": "change",
        "approval": {"actor": "fixture", "evidence": "fixture:approved"},
        "lint": {"required_outcome": "passed"},
        "status": "Ready",
    }
    _write(
        repo / "docs/knowledge/meta/promotions/promotion-fixture-ready.json",
        json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
    )
    _write(repo / "docs/knowledge/log.md", "# Knowledge Promotion Log\n\n- stale entry\n")
    _git(repo, "add", ".")
    return repo


def _build_promotion_fixture(root: Path) -> Path:
    _remove_fixture(root)
    repo = root / "promotion-security"
    repo.mkdir(parents=True)
    _git(repo, "init", "-q")
    _write(repo / ".gitignore", "docs/knowledge/ignored/\n")
    _write(repo / "evidence/terminal.md", "Status: Complete\n")
    _git(repo, "add", ".")
    return repo


def _candidate_draft(path: str, content: str) -> dict[str, object]:
    return {
        "schema": "knowledge-candidate-draft/v1",
        "stage": "implementation",
        "work_id": "work-security-fixture",
        "decision": "change",
        "source_snapshot": [],
        "operations": [
            {
                "kind": "create",
                "path": path,
                "postimage": content,
            }
        ],
    }


def _exercise_promotion_security_and_recovery(fixture_root: Path) -> dict[str, object]:
    import knowledge_query
    from knowledge_promotion import (
        SimulatedCrash,
        apply_candidate,
        recover_repository,
        seal_candidate_draft,
    )
    from knowledge_query import KnowledgeError

    repo = _build_promotion_fixture(fixture_root)
    registry = fixture_root / "registry"
    baseline = _tree_snapshot(repo)
    error_codes: list[str] = []

    def expect_seal_error(
        draft: dict[str, object],
        expected: str,
        *,
        known_secret_values: tuple[str, ...] = (),
        redirected: bool = False,
    ) -> None:
        redirect_patch: contextlib.AbstractContextManager[object]
        if redirected:
            redirect_patch = mock.patch("knowledge_promotion._redirected", return_value=True)
        else:
            redirect_patch = contextlib.nullcontext()
        with redirect_patch:
            try:
                seal_candidate_draft(
                    str(repo),
                    draft=draft,
                    approval_actor="test-reviewer",
                    approval_evidence="fixture:seal-rejected",
                    known_secret_values=known_secret_values,
                )
            except KnowledgeError as exc:
                assert exc.code == expected, (expected, exc.code, str(exc))
                error_codes.append(exc.code)
            else:
                raise AssertionError(f"expected {expected}")

    real_subprocess_run = subprocess.run
    with (
        mock.patch("knowledge_governance.default_registry_root", return_value=registry),
        mock.patch("knowledge_query.subprocess.run", wraps=real_subprocess_run) as git_spy,
    ):
        expect_seal_error(
            _candidate_draft("docs/knowledge/../escape.md", "unsafe\n"),
            "UNSAFE_PATH",
        )
        expect_seal_error(
            _candidate_draft("docs/work/unapproved.md", "unapproved\n"),
            "TARGET_NOT_ALLOWED",
        )
        expect_seal_error(
            _candidate_draft("docs/knowledge/ignored/value.md", "ignored\n"),
            "TARGET_IGNORED",
        )
        secret_value = "fixture-known-secret-value-123456"
        expect_seal_error(
            _candidate_draft(
                "docs/knowledge/bootstrap/catalog.md",
                f"deployment value: {secret_value}\n",
            ),
            "SECRET_DETECTED",
            known_secret_values=(secret_value,),
        )

        redirect_parent = repo / "docs" / "knowledge" / "redirect"
        redirect_target = fixture_root / "redirect-target"
        redirect_target.mkdir(parents=True, exist_ok=True)
        actual_redirect = False
        redirect_parent.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.symlink(redirect_target, redirect_parent, target_is_directory=True)
            actual_redirect = True
        except (OSError, NotImplementedError):
            pass
        expect_seal_error(
            _candidate_draft("docs/knowledge/redirect/value.md", "redirected\n"),
            "TARGET_REDIRECTED",
            redirected=not actual_redirect,
        )

        fault_codes: list[str] = []
        for fault in (
            "before-replace-0",
            "after-replace-0",
            "before-lint",
            "after-lint",
        ):
            sealed = seal_candidate_draft(
                str(repo),
                draft=_candidate_draft(
                    "docs/knowledge/bootstrap/catalog.md",
                    f"# Fault boundary\n\n{fault}\n",
                ),
                approval_actor="test-reviewer",
                approval_evidence=f"fixture:{fault}",
            )
            before_apply = _tree_snapshot(repo)
            try:
                apply_candidate(
                    str(repo),
                    candidate_ref=sealed["candidate_ref"],
                    review_sha256=sealed["review_sha256"],
                    approval_actor="test-reviewer",
                    approval_evidence=f"fixture:{fault}",
                    fault_at=fault,
                )
            except KnowledgeError as exc:
                assert exc.code == "PROMOTION_FAILED", (fault, exc.code)
                assert exc.recoverable is True
                fault_codes.append(fault)
            else:
                raise AssertionError(f"fault boundary unexpectedly succeeded: {fault}")
            assert _tree_snapshot(repo) == before_apply
            assert not list(repo.glob("docs/knowledge/meta/promotions/*.json"))

        crash_sealed = seal_candidate_draft(
            str(repo),
            draft=_candidate_draft(
                "docs/knowledge/bootstrap/catalog.md",
                "# Interrupted promotion\n",
            ),
            approval_actor="test-reviewer",
            approval_evidence="fixture:crash",
        )
        try:
            apply_candidate(
                str(repo),
                candidate_ref=crash_sealed["candidate_ref"],
                review_sha256=crash_sealed["review_sha256"],
                approval_actor="test-reviewer",
                approval_evidence="fixture:crash",
                fault_at="crash-after-replace-0",
            )
        except SimulatedCrash:
            pass
        else:
            raise AssertionError("simulated crash did not interrupt promotion")
        assert (repo / "docs/knowledge/bootstrap/catalog.md").is_file()
        assert not list(repo.glob("docs/knowledge/meta/promotions/*.json"))
        try:
            apply_candidate(
                str(repo),
                candidate_ref=crash_sealed["candidate_ref"],
                review_sha256=crash_sealed["review_sha256"],
                approval_actor="test-reviewer",
                approval_evidence="fixture:retry-before-recover",
            )
        except KnowledgeError as exc:
            assert exc.code == "RECOVERY_REQUIRED"
            assert exc.exit_code == 5
            assert exc.recoverable is True
        else:
            raise AssertionError("unresolved journal did not block a retry")
        with mock.patch("knowledge_promotion._pid_is_alive", return_value=False):
            recovery = recover_repository(str(repo))
        assert recovery["outcome"] == "recovered"
        assert recovery["promotion_ids"] == [crash_sealed["promotion_id"]]
        assert _tree_snapshot(repo) == baseline
        assert not list(repo.glob("docs/knowledge/meta/promotions/*.json"))

    forbidden = {"add", "commit", "push", "merge", "reset", "checkout", "clean", "rm"}
    git_commands = [
        list(call.args[0])
        for call in git_spy.call_args_list
        if call.args and call.args[0] and Path(str(call.args[0][0])).name.casefold().startswith("git")
    ]
    assert git_commands
    assert all(not forbidden.intersection(command[1:]) for command in git_commands), git_commands
    return {
        "safety_codes": sorted(error_codes),
        "faults": fault_codes,
        "git_commands": len(git_commands),
        "recovery": recovery["outcome"],
    }


def _exercise_requirements_co_promotion(
    fixture_root: Path,
    *,
    include_bug_assessment: bool = False,
) -> dict[str, object]:
    import knowledge_governance
    from knowledge_promotion import apply_candidate, review_candidate, seal_candidate_draft
    from knowledge_query import KnowledgeError
    from knowledge_workflow import build_stage_candidate_draft, validate_stage_promotion

    _remove_fixture(fixture_root)
    repo = fixture_root / "requirements-promotion"
    repo.mkdir(parents=True)
    _git(repo, "init", "-q")
    _write(repo / "README.md", "# Fixture\n")
    _git(repo, "add", ".")
    registry = fixture_root / "registry"
    work_id = "work-stage-gate"
    artifact_path = f"docs/work/{work_id}/requirements.md"
    claim_text = "Requirements must retain auditable source citations."
    artifact_text = (
        "# Requirements\n\n"
        "Status: Ready\n\n"
        f"{claim_text}\n"
    )
    approval = "conversation:requirements-approved"
    bug_assessment: dict[str, str] | None = None
    expected_review_targets: set[str] = set()
    expected_assessment_bytes: dict[str, bytes] = {}
    if include_bug_assessment:
        bug_id = "bug-requirements-composite"
        assessment_json_path = f"docs/bugs/{bug_id}/assessment-1.json"
        assessment_markdown_path = f"docs/bugs/{bug_id}/assessment-1.md"
        assessment_markdown = "# BUG assessment\n\nVerdict: likely\n"
        hypotheses = [
            {
                "hypothesis_id": f"H-{index:03d}",
                "rank": index,
                "statement": f"controlled cause {index}",
                "variable": f"variable-{index}",
                "prediction": f"prediction-{index}",
                "falsifier": f"falsifier-{index}",
                "outcome": "testing" if index == 1 else "untested",
                "evidence_refs": [],
            }
            for index in range(1, 4)
        ]
        markdown_sha256 = _sha256(assessment_markdown.encode("utf-8"))
        assessment_json = json.dumps(
            {
                "schema": "bug-assessment/v1",
                "bug_id": bug_id,
                "revision": 1,
                "markdown": {
                    "path": assessment_markdown_path,
                    "sha256": markdown_sha256,
                },
                "source": {
                    "relation": "intake",
                    "work_id": None,
                    "reported_by": "user",
                    "evidence_refs": ["conversation:bug-report"],
                },
                "observed_behavior": "The public command returns an incorrect result.",
                "expected_behavior": "The public command returns the specified result.",
                "impact": "The primary workflow cannot complete.",
                "verdict": "likely",
                "severity": "medium",
                "reproduction": {
                    "status": "not-reproduced",
                    "symptom_oracle": "expected and actual outputs differ",
                    "steps": ["run the public command with the reported fixture"],
                    "sample": "one controlled attempt",
                    "command_refs": ["host-temp:commands/repro-1"],
                    "evidence_refs": ["host-temp:outputs/repro-1"],
                },
                "root_cause": {
                    "status": "hypothesized",
                    "confidence": "low",
                    "summary": "Evidence supports one boundary hypothesis without proving causality.",
                    "evidence_refs": ["host-temp:traces/boundary-1"],
                },
                "hypotheses": hypotheses,
                "active_hypothesis_id": "H-001",
                "risk": {
                    "security_privacy_or_data_risk": False,
                    "redacted_summary": None,
                    "secure_evidence_refs": [],
                    "human_reviewer": None,
                },
                "disposition": "delivery",
                "evidence_refs": ["host-temp:assessment/index"],
                "next_action": "Test H-001 while holding other variables constant.",
                "created_at": "2026-09-05T00:00:00+08:00",
            },
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        ) + "\n"
        assessment_sha256 = _sha256(assessment_json.encode("utf-8"))
        bug_assessment = {
            "path": assessment_json_path,
            "sha256": assessment_sha256,
            "content": assessment_json,
            "markdown_path": assessment_markdown_path,
            "markdown_sha256": markdown_sha256,
            "markdown_content": assessment_markdown,
        }
        expected_review_targets = {
            assessment_json_path,
            assessment_markdown_path,
        }
        expected_assessment_bytes = {
            assessment_json_path: assessment_json.encode("utf-8"),
            assessment_markdown_path: assessment_markdown.encode("utf-8"),
        }
        assert all(
            not (repo / Path(*relative.split("/"))).exists()
            for relative in expected_review_targets
        )
    with mock.patch("knowledge_governance.default_registry_root", return_value=registry):
        draft = build_stage_candidate_draft(
            str(repo),
            stage="requirements",
            work_id=work_id,
            artifact_path=artifact_path,
            artifact_text=artifact_text,
            title="Auditable Requirements",
            claim_text=claim_text,
            bug_assessment=bug_assessment,
        )
        sealed = seal_candidate_draft(
            str(repo),
            draft=draft,
            approval_actor="requirements-owner",
            approval_evidence=approval,
        )
        preapproval_absent = all(
            not (repo / Path(*relative.split("/"))).exists()
            for relative in {artifact_path, *expected_review_targets}
        )
        assert preapproval_absent
        expected_paths = {
            artifact_path,
            f"docs/knowledge/topics/{work_id}-requirements.md",
            f"docs/knowledge/meta/pages/page-{work_id}-requirements.json",
            "docs/knowledge/index.md",
        }
        expected_paths.update(
            {
                "docs/knowledge/log.md",
                f"docs/knowledge/meta/promotions/{sealed['promotion_id']}.json",
            }
        )
        expected_paths.update(expected_review_targets)
        assert set(sealed["affected_paths"]) == expected_paths
        summary = review_candidate(str(repo), candidate_ref=sealed["candidate_ref"])
        serialized_summary = json.dumps(summary, ensure_ascii=False, sort_keys=True)
        assert "The public command returns an incorrect result." not in serialized_summary
        assert "controlled cause 1" not in serialized_summary
        assert summary["summary"]["purpose"] == (
            "Review the Requirements artifact, optional BUG assessment, and "
            "proposed knowledge changes before approval."
        )
        assert summary["summary"]["change"]["operation_count"] == len(expected_paths)
        bug_projection = summary["risk_and_compatibility"]["material"]["bug_assessment"]
        if include_bug_assessment:
            assert bug_projection == {
                "verdict": "likely",
                "severity": "medium",
                "source_relation": "intake",
                "reproduction_status": "not-reproduced",
                "root_cause_status": "hypothesized",
                "disposition": "delivery",
                "security_privacy_or_data_risk": False,
                "classification_risk": "uncertain-diagnosis",
            }
        else:
            assert bug_projection is None
        assert {
            item["target_path"]
            for item in summary["review_bundle"]["manifest"]
            if item["role"] == "postimage"
        } == expected_paths
        assessment_entries = [
            item
            for item in summary["review_bundle"]["manifest"]
            if item["role"] == "postimage"
            and item["target_path"] in expected_review_targets
        ]
        assert {item["target_path"] for item in assessment_entries} == expected_review_targets
        for item in assessment_entries:
            assert Path(str(item["direct_path"])).read_bytes() == expected_assessment_bytes[
                str(item["target_path"])
            ]
        collision_code: str | None = None
        collision_zero_mutation = True
        if include_bug_assessment:
            collision_path = repo / Path(*assessment_markdown_path.split("/"))
            _write(collision_path, "occupied after review\n")
            collision_snapshot = _tree_snapshot(repo)
            try:
                apply_candidate(
                    str(repo),
                    candidate_ref=sealed["candidate_ref"],
                    review_sha256=sealed["review_sha256"],
                    approval_actor="requirements-owner",
                    approval_evidence=approval,
                )
            except KnowledgeError as exc:
                collision_code = exc.code
            else:
                raise AssertionError("BUG assessment collision must fail closed")
            collision_zero_mutation = _tree_snapshot(repo) == collision_snapshot
            assert collision_code == "PREIMAGE_DRIFT"
            assert collision_zero_mutation
            collision_path.unlink()
            assert all(
                not (repo / Path(*relative.split("/"))).exists()
                for relative in {artifact_path, *expected_review_targets}
            )
        applied = apply_candidate(
            str(repo),
            candidate_ref=sealed["candidate_ref"],
            review_sha256=sealed["review_sha256"],
            approval_actor="requirements-owner",
            approval_evidence=approval,
        )
        promotion = applied["promotion"]
        gate = validate_stage_promotion(
            str(repo),
            work_id=work_id,
            stage="requirements",
            receipt_path=applied["receipt_path"],
            receipt_sha256=applied["receipt_sha256"],
            approval_evidence=approval,
        )
        final_lint = knowledge_governance.lint_repository(str(repo))

    assert (repo / Path(*artifact_path.split("/"))).read_text(encoding="utf-8") == artifact_text
    assert promotion["schema"] == "knowledge-promotion/v1"
    assert promotion["stage"] == "requirements"
    assert promotion["work_id"] == work_id
    assert promotion["status"] == "Ready"
    assert promotion["lint"]["required_outcome"] == "passed"
    assert promotion["formal_paths"] == sorted(
        {artifact_path, *expected_review_targets},
        key=lambda value: value.encode("utf-8"),
    )
    assessment_materialized = all(
        (repo / Path(*relative.split("/"))).read_bytes() == raw
        for relative, raw in expected_assessment_bytes.items()
    )
    assert assessment_materialized
    assert final_lint["outcome"] == "passed", final_lint["diagnostics"]
    assert (repo / "docs/knowledge/log.md").is_file()
    assert gate["schema"] == "knowledge-stage-gate/v1"
    assert gate["next_phase"] == "planning"
    assert gate["approval_evidence"] == approval
    return {
        "affected_paths": sorted(expected_paths),
        "next_phase": gate["next_phase"],
        "lint": final_lint["outcome"],
        "receipt_path": applied["receipt_path"],
        "review_targets": sorted(expected_review_targets),
        "preapproval_absent": preapproval_absent,
        "collision_code": collision_code,
        "collision_zero_mutation": collision_zero_mutation,
        "assessment_materialized": assessment_materialized,
        "formal_paths": promotion["formal_paths"],
        "gate_purpose": summary["summary"]["purpose"],
        "gate_change": summary["summary"]["change"],
        "bug_assessment_summary": bug_projection,
        "summary_rendered": serialized_summary,
    }


def _exercise_planning_co_promotion(fixture_root: Path) -> dict[str, object]:
    import knowledge_governance
    from knowledge_promotion import apply_candidate, review_candidate, seal_candidate_draft
    from knowledge_query import KnowledgeError
    from knowledge_workflow import build_stage_candidate_draft, validate_stage_promotion

    _remove_fixture(fixture_root)
    repo = fixture_root / "planning-promotion"
    repo.mkdir(parents=True)
    _git(repo, "init", "-q")
    _write(repo / "README.md", "# Fixture\n")
    _git(repo, "add", ".")
    registry = fixture_root / "registry"
    work_id = "work-stage-plan"
    with mock.patch("knowledge_governance.default_registry_root", return_value=registry):
        requirements_claim = "Requirements define the auditable planning boundary."
        requirements_draft = build_stage_candidate_draft(
            str(repo),
            stage="requirements",
            work_id=work_id,
            artifact_path=f"docs/work/{work_id}/requirements.md",
            artifact_text=(
                "# Requirements\n\nStatus: Ready\n\n"
                f"{requirements_claim}\n"
            ),
            title="Planning Boundary Requirements",
            claim_text=requirements_claim,
        )
        requirements_sealed = seal_candidate_draft(
            str(repo),
            draft=requirements_draft,
            approval_actor="requirements-owner",
            approval_evidence="conversation:requirements-approved",
        )
        apply_candidate(
            str(repo),
            candidate_ref=requirements_sealed["candidate_ref"],
            review_sha256=requirements_sealed["review_sha256"],
            approval_actor="requirements-owner",
            approval_evidence="conversation:requirements-approved",
        )

        plan_claim = "The approved plan uses an optimistic promotion transaction."
        plan_path = f"docs/work/{work_id}/plan/plan.md"
        plan_text = f"# Plan\n\nStatus: Ready\n\n{plan_claim}\n"
        artifact_bundle = _ready_plan_bundle(repo, work_id, plan_text)
        for missing_name in ("architecture.md", "occurrence_map.yaml", "handoff.json"):
            incomplete = [
                item for item in artifact_bundle if not item["path"].endswith(f"/{missing_name}")
            ]
            before_rejection = _tree_snapshot(repo)
            try:
                build_stage_candidate_draft(
                    str(repo),
                    stage="planning",
                    work_id=work_id,
                    artifact_path=plan_path,
                    artifact_text=plan_text,
                    title="Optimistic Promotion Plan",
                    claim_text=plan_claim,
                    artifact_bundle=incomplete,
                )
            except KnowledgeError as exc:
                assert exc.code == "READY_PLAN_BUNDLE_INCOMPLETE", (missing_name, exc.code)
            else:
                raise AssertionError(f"planning bundle without {missing_name} was accepted")
            assert _tree_snapshot(repo) == before_rejection
        plan_draft = build_stage_candidate_draft(
            str(repo),
            stage="planning",
            work_id=work_id,
            artifact_path=plan_path,
            artifact_text=plan_text,
            title="Optimistic Promotion Plan",
            claim_text=plan_claim,
            artifact_bundle=artifact_bundle,
        )
        observed_mutation = json.loads(json.dumps(plan_draft))
        sidecar_operation = next(
            operation
            for operation in observed_mutation["operations"]
            if operation["path"].startswith("docs/knowledge/meta/pages/")
        )
        sidecar = json.loads(sidecar_operation["postimage"])
        sidecar["claims"][0]["evidence_class"] = "observed"
        sidecar_operation["postimage"] = (
            json.dumps(sidecar, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        )
        before_rejection = _tree_snapshot(repo)
        try:
            seal_candidate_draft(
                str(repo),
                draft=observed_mutation,
                approval_actor="plan-owner",
                approval_evidence="conversation:plan-approved",
            )
        except KnowledgeError as exc:
            assert exc.code == "EVIDENCE_CLASS_MISMATCH"
        else:
            raise AssertionError("planning claim mislabeled observed was accepted")
        assert _tree_snapshot(repo) == before_rejection

        sealed = seal_candidate_draft(
            str(repo),
            draft=plan_draft,
            approval_actor="plan-owner",
            approval_evidence="conversation:plan-approved",
        )
        summary = review_candidate(str(repo), candidate_ref=sealed["candidate_ref"])
        serialized_summary = json.dumps(summary, ensure_ascii=False, sort_keys=True)
        assert OCCURRENCE_REASON_SENTINEL not in serialized_summary
        assert summary["summary"]["purpose"] == (
            "Review the complete Ready-plan bundle, occurrence classification, "
            "and proposed knowledge changes before approval."
        )
        assert summary["summary"]["change"]["operation_count"] == len(
            sealed["affected_paths"]
        )
        occurrence_projection = summary["risk_and_compatibility"]["material"]["occurrence"]
        assert occurrence_projection == {
            "change_mode": "bulk_edit",
            "manual_review_required": True,
            "manual_review_item_count": 2,
            "classification_risk": "manual-review-required",
        }
        applied = apply_candidate(
            str(repo),
            candidate_ref=sealed["candidate_ref"],
            review_sha256=sealed["review_sha256"],
            approval_actor="plan-owner",
            approval_evidence="conversation:plan-approved",
        )
        supporting_path = next(
            item["path"] for item in artifact_bundle if item["path"].endswith("/architecture.md")
        )
        supporting_target = repo / Path(*supporting_path.split("/"))
        supporting_postimage = next(
            item["postimage"] for item in artifact_bundle if item["path"] == supporting_path
        )
        supporting_target.write_text("drifted supporting plan\n", encoding="utf-8", newline="\n")
        try:
            validate_stage_promotion(
                str(repo),
                work_id=work_id,
                stage="planning",
                receipt_path=applied["receipt_path"],
                receipt_sha256=applied["receipt_sha256"],
                approval_evidence="conversation:plan-approved",
            )
        except KnowledgeError as exc:
            assert exc.code == "MISSING_KNOWLEDGE_GATE"
        else:
            raise AssertionError("drifted supporting Ready-plan artifact passed the stage gate")
        supporting_target.write_text(supporting_postimage, encoding="utf-8", newline="\n")
        gate = validate_stage_promotion(
            str(repo),
            work_id=work_id,
            stage="planning",
            receipt_path=applied["receipt_path"],
            receipt_sha256=applied["receipt_sha256"],
            approval_evidence="conversation:plan-approved",
        )
        final_lint = knowledge_governance.lint_repository(str(repo))

    plan_sidecar_path = repo / f"docs/knowledge/meta/pages/page-{work_id}-planning.json"
    plan_sidecar = json.loads(plan_sidecar_path.read_text(encoding="utf-8"))
    evidence_classes = {claim["evidence_class"] for claim in plan_sidecar["claims"]}
    log_lines = [
        line
        for line in (repo / "docs/knowledge/log.md").read_text(encoding="utf-8").splitlines()
        if line.startswith("- `promotion-")
    ]
    assert evidence_classes == {"planned"}
    assert len(log_lines) == 2
    assert final_lint["outcome"] == "passed", final_lint["diagnostics"]
    return {
        "next_phase": gate["next_phase"],
        "formal_paths": gate["formal_paths"],
        "evidence_classes": sorted(evidence_classes),
        "promotion_count": len(log_lines),
        "lint": final_lint["outcome"],
        "gate_purpose": summary["summary"]["purpose"],
        "gate_change": summary["summary"]["change"],
        "occurrence_summary": occurrence_projection,
        "summary_rendered": serialized_summary,
    }


def _exercise_implementation_knowledge_gate(fixture_root: Path) -> dict[str, object]:
    import knowledge_governance
    from knowledge_delivery import (
        advance_knowledge_gate,
        build_knowledge_snapshot,
        compute_product_snapshot,
        new_required_knowledge_gate,
    )
    from knowledge_outcome import (
        build_implementation_candidate_draft,
        write_implementation_outcome,
    )
    from knowledge_promotion import apply_candidate, review_candidate, seal_candidate_draft
    from knowledge_query import KnowledgeError

    _remove_fixture(fixture_root)
    repo = fixture_root / "implementation-gate"
    repo.mkdir(parents=True)
    _git(repo, "init", "-q")
    _write(repo / "src/change.md", "Implementation now preserves promotion atomicity.\n")
    _git(repo, "add", ".")
    registry = fixture_root / "registry"
    work_id = "work-implementation-gate"
    implementation_run_id = "b" * 64
    host_temp = fixture_root / "host-temp"
    with mock.patch("knowledge_outcome.tempfile.gettempdir", return_value=str(host_temp)):
        preliminary_review, output_refs = _persist_preliminary_review_fixture(
            implementation_run_id=implementation_run_id,
            logical_ref="review:fresh-review:implementation-gate-r1",
            command_ids=["CMD-FULL-001"],
        )
        outcome = write_implementation_outcome(
            str(repo),
            work_id=work_id,
            implementation_run_id=implementation_run_id,
            work_kind="standard",
            result="complete",
            summary="Implementation preserves promotion atomicity.",
            changes=[
                {
                    "path": "src/change.md",
                    "summary": "Added the reviewed atomic promotion behavior.",
                }
            ],
            verification=[
                {
                    "command_id": "CMD-FULL-001",
                    "outcome": "passed",
                    "evidence_refs": [output_refs["CMD-FULL-001"]],
                }
            ],
            review=preliminary_review,
            known_deviations=[],
            knowledge_decision="change",
            bug_verification_ref=None,
            created_at="2026-08-31T12:00:00+08:00",
        )
    with (
        mock.patch("knowledge_governance.default_registry_root", return_value=registry),
        mock.patch("knowledge_outcome.tempfile.gettempdir", return_value=str(host_temp)),
    ):
        draft = build_implementation_candidate_draft(str(repo), outcome=outcome)
        sealed = seal_candidate_draft(
            str(repo),
            draft=draft,
            approval_actor="knowledge-owner",
            approval_evidence="conversation:implementation-knowledge-approved",
        )
        first_summary = review_candidate(str(repo), candidate_ref=sealed["candidate_ref"])
        resumed_summary = review_candidate(str(repo), candidate_ref=sealed["candidate_ref"])
        assert first_summary == resumed_summary
        outcome_projection = first_summary["risk_and_compatibility"]["material"][
            "implementation_outcome"
        ]
        assert outcome_projection == {
            "work_kind": "standard",
            "result": "complete",
            "knowledge_decision": "change",
            "changed_path_count": 1,
            "known_deviation_count": 0,
            "residual_risk_count": 0,
            "follow_up_count": 0,
        }
        assert first_summary["summary"]["purpose"] == (
            "Review the implementation Outcome and proposed observed knowledge "
            "changes before approval."
        )
        outcome_targets = {outcome["path"], outcome["markdown_path"]}
        outcome_entries = [
            item
            for item in first_summary["review_bundle"]["manifest"]
            if item["role"] == "supporting"
        ]
        assert {item["target_path"] for item in outcome_entries} == outcome_targets
        for item in outcome_entries:
            assert Path(str(item["direct_path"])).read_bytes() == (
                repo / Path(*str(item["target_path"]).split("/"))
            ).read_bytes()
        knowledge_snapshot = build_knowledge_snapshot(str(repo), sealed=sealed)
        direct_knowledge = repo / "docs/knowledge/glossary.md"
        _write(direct_knowledge, "# Unreviewed but lint-valid glossary\n")
        drifted_snapshot = build_knowledge_snapshot(str(repo), sealed=sealed)
        assert drifted_snapshot["snapshot_id"] != knowledge_snapshot["snapshot_id"]
        direct_knowledge.unlink()
        product_before = compute_product_snapshot(str(repo))
        record = {
            "work_id": work_id,
            "phase": "implementation",
            "status": "active",
            "knowledge_gate": new_required_knowledge_gate(
                enabled_at="2026-08-31T12:00:01+08:00"
            ),
        }
        try:
            advance_knowledge_gate(record, action="complete")
        except KnowledgeError as exc:
            assert exc.code == "KNOWLEDGE_GATE_REQUIRED"
        else:
            raise AssertionError("required knowledge gate allowed direct Complete")
        unbound_sealed = {
            key: value
            for key, value in sealed.items()
            if key not in {"review_ref", "review_sha256"}
        }
        try:
            advance_knowledge_gate(
                record,
                action="review-approved",
                repo_value=str(repo),
                outcome=outcome,
                sealed=unbound_sealed,
                knowledge_snapshot_before=knowledge_snapshot,
                knowledge_snapshot_after=knowledge_snapshot,
            )
        except KnowledgeError as exc:
            assert exc.code == "REVIEW_BINDING_MISSING"
        else:
            raise AssertionError("knowledge/awaiting_user accepted an unbound review")
        awaiting = advance_knowledge_gate(
            record,
            action="review-approved",
            repo_value=str(repo),
            outcome=outcome,
            sealed=sealed,
            knowledge_snapshot_before=knowledge_snapshot,
            knowledge_snapshot_after=knowledge_snapshot,
        )
        assert awaiting["phase"] == "knowledge"
        assert awaiting["status"] == "awaiting_user"
        try:
            apply_candidate(
                str(repo),
                candidate_ref=sealed["candidate_ref"],
                approval_actor="knowledge-owner",
                approval_evidence="conversation:implementation-knowledge-approved",
            )
        except KnowledgeError as exc:
            assert exc.code == "REVIEW_BINDING_MISSING"
        else:
            raise AssertionError("knowledge apply accepted approval without review digest")
        applied = apply_candidate(
            str(repo),
            candidate_ref=sealed["candidate_ref"],
            review_sha256=sealed["review_sha256"],
            approval_actor="knowledge-owner",
            approval_evidence="conversation:implementation-knowledge-approved",
        )
        _write(direct_knowledge, "# Unreviewed but lint-valid glossary\n")
        try:
            advance_knowledge_gate(
                awaiting,
                action="promotion-applied",
                repo_value=str(repo),
                applied=applied,
                approval_evidence="conversation:implementation-knowledge-approved",
            )
        except KnowledgeError as exc:
            assert exc.code == "KNOWLEDGE_SNAPSHOT_DRIFT"
        else:
            raise AssertionError("Candidate-external knowledge bypassed the completion snapshot")
        direct_knowledge.unlink()
        completed = advance_knowledge_gate(
            awaiting,
            action="promotion-applied",
            repo_value=str(repo),
            applied=applied,
            approval_evidence="conversation:implementation-knowledge-approved",
        )
        product_after = compute_product_snapshot(str(repo))
        final_lint = knowledge_governance.lint_repository(str(repo))

    assert completed["phase"] == "complete"
    assert completed["status"] == "complete"
    assert product_before == product_after
    assert completed["knowledge_gate"]["current_promotion_id"] == applied["promotion"]["promotion_id"]
    assert final_lint["outcome"] == "passed", final_lint["diagnostics"]
    return {
        "awaiting_phase": awaiting["phase"],
        "awaiting_status": awaiting["status"],
        "completed_phase": completed["phase"],
        "product_snapshot_stable": product_before == product_after,
        "external_knowledge_rejected": True,
        "outcome_paths": sorted([outcome["path"], outcome["markdown_path"]]),
        "outcome_review_targets": sorted(outcome_targets),
        "review_resumable": first_summary == resumed_summary,
        "review_sha256": sealed["review_sha256"],
        "outcome_summary": outcome_projection,
        "gate_purpose": first_summary["summary"]["purpose"],
        "gate_change": first_summary["summary"]["change"],
        "lint": final_lint["outcome"],
    }


def _exercise_human_gate_compatibility(fixture_root: Path) -> dict[str, object]:
    import knowledge_governance
    import knowledge_promotion
    from knowledge_cli import main
    from knowledge_promotion import apply_candidate, review_candidate, seal_candidate_draft
    from knowledge_query import KnowledgeError

    repo = _build_promotion_fixture(fixture_root)
    registry = fixture_root / "compatibility-registry"
    collision_target = "docs/knowledge/topics/cross-role-collision.md"
    collision_content = "# Existing review source\n"
    with mock.patch.object(
        knowledge_governance,
        "default_registry_root",
        return_value=registry,
    ):
        sealed = seal_candidate_draft(
            str(repo),
            draft=_candidate_draft(
                "docs/knowledge/bootstrap/catalog.md",
                "# Compatibility baseline\n",
            ),
            approval_actor="compatibility-owner",
            approval_evidence="fixture:compatibility-approved",
        )
        candidate_path = (
            registry
            / "repos"
            / sealed["repo_id"]
            / Path(*sealed["candidate_ref"].removeprefix("knowledge:").split("/"))
        )
        review_path = candidate_path.with_name("review.json")
        review_raw = review_path.read_bytes()
        _write(repo / collision_target, collision_content)
        collision_repo_before = _tree_snapshot(repo)
        registry_before_collisions = _tree_snapshot(registry)
        cross_role_collision_codes: list[str] = []
        for operation_path, kind in (
            (collision_target, "update"),
            ("docs/knowledge/topics/CROSS-ROLE-COLLISION.md", "create"),
        ):
            try:
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
            except KnowledgeError as exc:
                cross_role_collision_codes.append(exc.code)
            else:
                raise AssertionError(
                    "Candidate sealing accepted an operation/review-file target collision"
                )
        cross_role_collision_zero_mutation = (
            _tree_snapshot(repo) == collision_repo_before
            and _tree_snapshot(registry) == registry_before_collisions
        )
        (repo / collision_target).unlink()
        before = _tree_snapshot(repo)
        original_validator = knowledge_promotion._validated_review_bundle
        review_drift_injected = False

        def validate_then_drift(*args: object, **kwargs: object) -> object:
            nonlocal review_drift_injected
            result = original_validator(*args, **kwargs)
            review_path.write_bytes(review_raw + b" ")
            review_drift_injected = True
            return result

        try:
            with mock.patch(
                "knowledge_promotion._validated_review_bundle",
                side_effect=validate_then_drift,
            ):
                review_candidate(str(repo), candidate_ref=sealed["candidate_ref"])
        except KnowledgeError as exc:
            assert exc.code == "REVIEW_MANIFEST_DRIFT", exc.code
        else:
            raise AssertionError("review projection accepted a link that drifted before return")
        assert review_drift_injected
        assert _tree_snapshot(repo) == before
        review_path.write_bytes(review_raw)

        try:
            apply_candidate(
                str(repo),
                candidate_ref=sealed["candidate_ref"],
                review_sha256=sealed["review_sha256"],
                approval_actor="ambiguous-owner",
                approval_evidence="fixture:compatibility-approved",
            )
        except KnowledgeError as exc:
            assert exc.code == "APPROVAL_BINDING_DRIFT", exc.code
        else:
            raise AssertionError("apply accepted an approval actor outside the reviewed binding")
        assert _tree_snapshot(repo) == before

        candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
        postimage_path = candidate_path.parent / Path(
            *candidate["operations"][0]["postimage_ref"].split("/")
        )
        postimage_raw = postimage_path.read_bytes()
        postimage_path.unlink()
        try:
            review_candidate(str(repo), candidate_ref=sealed["candidate_ref"])
        except KnowledgeError as exc:
            assert exc.code == "POSTIMAGE_MISSING", exc.code
        else:
            raise AssertionError("review accepted a missing linked postimage")
        assert _tree_snapshot(repo) == before
        postimage_path.write_bytes(postimage_raw)

        applied = apply_candidate(
            str(repo),
            candidate_ref=sealed["candidate_ref"],
            review_sha256=sealed["review_sha256"],
            approval_actor="compatibility-owner",
            approval_evidence="fixture:compatibility-approved",
        )
        ready_tree = _tree_snapshot(repo)
        review_path.unlink()
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            lint_exit = main(["lint", "--repo", str(repo)])
        assert lint_exit == 0, stderr.getvalue()
        automatic_lint = json.loads(stdout.getvalue())
        assert set(automatic_lint) == {
            "schema",
            "outcome",
            "diagnostics",
            "eligible_claim_ids",
            "repo_id",
            "repair_candidate_ref",
            "repair_candidate_payload_sha256",
        }
        assert automatic_lint["schema"] == "knowledge-lint/v1"
        assert automatic_lint["outcome"] == "passed"
        assert _tree_snapshot(repo) == ready_tree

        legacy = seal_candidate_draft(
            str(repo),
            draft=_candidate_draft(
                "docs/knowledge/bootstrap/pending-legacy.md",
                "# Pending legacy Candidate\n",
            ),
            approval_actor="legacy-owner",
            approval_evidence="fixture:legacy-pending",
        )
        legacy_candidate_path = (
            registry
            / "repos"
            / legacy["repo_id"]
            / Path(*legacy["candidate_ref"].removeprefix("knowledge:").split("/"))
        )
        legacy_candidate_path.with_name("review.json").unlink()
        legacy_before = _tree_snapshot(repo)
        try:
            apply_candidate(
                str(repo),
                candidate_ref=legacy["candidate_ref"],
                review_sha256=legacy["review_sha256"],
                approval_actor="legacy-owner",
                approval_evidence="fixture:legacy-pending",
            )
        except KnowledgeError as exc:
            assert exc.code == "LEGACY_RESEAL_REQUIRED", exc.code
        else:
            raise AssertionError("pending legacy Candidate applied without a review bundle")
        assert _tree_snapshot(repo) == legacy_before == ready_tree

        return {
            "apply_lint": applied["post_apply_lint"]["outcome"],
            "automatic_schema": automatic_lint["schema"],
            "historical_ready_preserved": _tree_snapshot(repo) == ready_tree,
            "legacy_reseal_required": True,
            "review_drift_rejected": review_drift_injected,
            "cross_role_collision_codes": cross_role_collision_codes,
            "cross_role_collision_zero_mutation": cross_role_collision_zero_mutation,
        }


def _bug_verification_fixture(result: str) -> tuple[dict[str, object], dict[str, object]]:
    implementation_scripts = (
        Path.cwd() / ".agents" / "skills" / "implementation-execution" / "scripts"
    ).resolve()
    if str(implementation_scripts) not in sys.path:
        sys.path.insert(0, str(implementation_scripts))
    from test_validate_contracts import _bug_verification_example

    return _bug_verification_example(result)


def _exercise_bug_knowledge_mapping(
    fixture_root: Path,
    *,
    result: str,
) -> dict[str, object]:
    import knowledge_governance
    from knowledge_outcome import (
        build_bug_candidate_draft,
        write_bug_implementation_outcome,
    )
    from knowledge_promotion import apply_candidate, review_candidate, seal_candidate_draft
    from knowledge_query import KnowledgeError

    ready, verification = _bug_verification_fixture(result)
    _remove_fixture(fixture_root)
    repo = fixture_root / f"bug-{result}"
    repo.mkdir(parents=True)
    _git(repo, "init", "-q")
    _write(repo / "src/bug-fix.md", "The root-cause seam now has regression coverage.\n")
    _git(repo, "add", ".")
    registry = fixture_root / "registry"
    implementation_run_id = "c" * 64
    host_temp = fixture_root / "host-temp"
    with (
        mock.patch("knowledge_governance.default_registry_root", return_value=registry),
        mock.patch("knowledge_outcome.tempfile.gettempdir", return_value=str(host_temp)),
    ):
        preliminary_review, output_refs = _persist_preliminary_review_fixture(
            implementation_run_id=implementation_run_id,
            logical_ref="review:fresh-review:bug-outcome-r1",
            command_ids=[item["command_id"] for item in verification["full_verification"]],
        )
        for item in verification["full_verification"]:
            item["output_ref"] = output_refs[item["command_id"]]
        verification["implementation_review_ref"] = preliminary_review["report_ref"]
        outcome = write_bug_implementation_outcome(
            str(repo),
            ready=ready,
            verification=verification,
            implementation_run_id=implementation_run_id,
            changes=[
                {
                    "path": "src/bug-fix.md",
                    "summary": "Added the approved regression seam.",
                }
            ],
            review=preliminary_review,
            created_at="2026-08-31T13:00:00+08:00",
        )
        draft = build_bug_candidate_draft(str(repo), outcome=outcome)
        sealed = seal_candidate_draft(
            str(repo),
            draft=draft,
            approval_actor="bug-owner",
            approval_evidence=f"conversation:bug-{result}-approved",
        )
        summary = review_candidate(str(repo), candidate_ref=sealed["candidate_ref"])
        outcome_projection = summary["risk_and_compatibility"]["material"][
            "implementation_outcome"
        ]
        assert outcome_projection["work_kind"] == "bug"
        assert outcome_projection["result"] == result
        assert outcome_projection["knowledge_decision"] == "change"
        assert summary["summary"]["purpose"] == (
            "Review the BUG Outcome and proposed incident knowledge changes before "
            "approval."
        )
        applied = apply_candidate(
            str(repo),
            candidate_ref=sealed["candidate_ref"],
            review_sha256=sealed["review_sha256"],
            approval_actor="bug-owner",
            approval_evidence=f"conversation:bug-{result}-approved",
        )
        final_lint = knowledge_governance.lint_repository(str(repo))

    bug_id = verification["bug_id"]
    page_path = repo / f"docs/knowledge/incidents/{bug_id}.md"
    sidecar_path = repo / f"docs/knowledge/meta/pages/page-{bug_id}.json"
    page_text = page_path.read_text(encoding="utf-8")
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    assert applied["promotion"]["stage"] == "bug"
    assert applied["promotion"]["work_id"] == verification["work_id"]
    assert final_lint["outcome"] == "passed", final_lint["diagnostics"]

    overclaim_rejected = None
    if result == "partial":
        unsafe = json.loads(json.dumps(verification))
        unsafe["summary"] = "BUG is verified fixed."
        before = _tree_snapshot(repo)
        try:
            write_bug_implementation_outcome(
                str(repo),
                ready=ready,
                verification=unsafe,
                implementation_run_id=implementation_run_id,
                changes=[
                    {
                        "path": "src/bug-fix.md",
                        "summary": "Unsafe retry must be rejected before writing.",
                    }
                ],
                review=preliminary_review,
                created_at="2026-08-31T13:01:00+08:00",
            )
        except KnowledgeError as exc:
            overclaim_rejected = exc.code
        else:
            raise AssertionError("partial BUG overclaim was accepted")
        assert _tree_snapshot(repo) == before

    return {
        "result": result,
        "page_text": page_text,
        "evidence_classes": sorted(
            {claim["evidence_class"] for claim in sidecar["claims"]}
        ),
        "lifecycle": sidecar["lifecycle"],
        "source_refs": sum(
            (claim["source_refs"] for claim in sidecar["claims"]),
            [],
        ),
        "lint": final_lint["outcome"],
        "overclaim_rejected": overclaim_rejected,
        "outcome_summary": outcome_projection,
    }


def _evaluate_golden(repo: Path, cases: list[tuple[str, str]]) -> dict[str, int]:
    from knowledge_cli import main

    expected_ineligible = {
        "docs/knowledge/incidents/stale-golden.md",
        "ignored/golden-secret.md",
    }
    top_five_hits = 0
    citation_count = 0
    valid_citations = 0
    ineligible_hits = 0
    for query, expected_path in cases:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            exit_code = main(
                [
                    "query",
                    "--repo",
                    str(repo),
                    "--stage",
                    "requirements",
                    "--query",
                    query,
                ]
            )
        assert exit_code == 0, (query, stderr.getvalue())
        context = json.loads(stdout.getvalue())
        paths = [result["path"] for result in context["results"]]
        top_five_hits += int(expected_path in paths)
        ineligible_hits += sum(path in expected_ineligible for path in paths)
        for result in context["results"]:
            assert result["lifecycle"] == "current"
            for source in result["source_refs"]:
                citation_count += 1
                raw = (repo / Path(*source["path"].split("/"))).read_bytes()
                lines = raw.decode("utf-8").replace("\r\n", "\n").splitlines()
                locator = source["locator"]
                excerpt = "\n".join(
                    lines[locator["start_line"] - 1 : locator["end_line"]]
                ).encode("utf-8")
                if (
                    _sha256(raw) == source["sha256"]
                    and _sha256(excerpt) == source["excerpt_sha256"]
                ):
                    valid_citations += 1
    return {
        "queries": len(cases),
        "top_five_hits": top_five_hits,
        "citation_count": citation_count,
        "valid_citations": valid_citations,
        "ineligible_hits": ineligible_hits,
    }


@scenario("BDD-018", "performance")
def audit_query_preserves_results_with_a_bounded_child_process_budget(
    fixture_root: Path,
) -> None:
    import knowledge_query
    from knowledge_cli import main

    repo = _build_query_performance_fixture(fixture_root)
    before = _tree_snapshot(repo)
    commands: list[list[str]] = []
    real_run = knowledge_query._run

    def recording_run(command: list[str], **kwargs: object) -> object:
        commands.append(list(command))
        return real_run(command, **kwargs)

    stdout = io.StringIO()
    stderr = io.StringIO()
    knowledge_query._MATCH_CACHE.clear()
    with mock.patch("knowledge_query._run", side_effect=recording_run):
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            exit_code = main(
                [
                    "query",
                    "--repo",
                    str(repo),
                    "--stage",
                    "implementation",
                    "--query",
                    "violet cedar ember quartz",
                ]
            )

    assert exit_code == 0, stderr.getvalue()
    assert stderr.getvalue() == ""
    context = json.loads(stdout.getvalue())
    assert context["schema"] == "knowledge-context/v1"
    assert context["stage"] == "implementation"
    assert context["query"] == "violet cedar ember quartz"
    assert context["diagnostics"] == [
        "eligible:67",
        "canonical:1",
        "raw:65",
        "contested:0",
    ]
    assert [
        (result["authority"], result["path"], result["start_line"])
        for result in context["results"]
    ] == [
        ("canonical", "docs/knowledge/topics/session.md", 5),
        ("raw", "evidence/source-000.md", 1),
        ("raw", "evidence/source-001.md", 1),
        ("raw", "evidence/source-002.md", 1),
        ("raw", "evidence/source-003.md", 1),
    ]
    for result in context["results"]:
        assert result["lifecycle"] == "current"
        assert result["source_refs"]
        for source in result["source_refs"]:
            raw = (repo / Path(*source["path"].split("/"))).read_bytes()
            lines = raw.decode("utf-8").replace("\r\n", "\n").splitlines()
            locator = source["locator"]
            excerpt = "\n".join(
                lines[locator["start_line"] - 1 : locator["end_line"]]
            ).encode("utf-8")
            assert _sha256(raw) == source["sha256"]
            assert _sha256(excerpt) == source["excerpt_sha256"]
    assert _tree_snapshot(repo) == before
    assert len(commands) <= 10, json.dumps(
        {
            "child_process_count": len(commands),
            "commands": commands,
        },
        ensure_ascii=False,
        sort_keys=True,
    )


@scenario("BDD-020", "performance")
def benchmark_reports_fresh_cold_and_compatible_warm_samples(
    fixture_root: Path,
) -> None:
    import knowledge_benchmark

    with (
        mock.patch.object(knowledge_benchmark, "FILE_COUNT", 250),
        mock.patch.object(knowledge_benchmark, "PAGE_COUNT", 20),
        mock.patch.object(
            knowledge_benchmark,
            "EXPECTED_FUNCTIONAL_SHA256",
            "6310a73a73d1beb175615d927b429bce350694a95a131a1c68356a69d9f6ba32",
        ),
    ):
        report = knowledge_benchmark.run_benchmark(
            fixture_root,
            file_count=250,
            page_count=20,
        )

    durations = report["durations_seconds"]
    assert report["schema"] == "knowledge-portability-report/v1"
    assert report["outcome"] == "passed", report
    assert len(durations["cold_queries"]) == 5
    assert len(durations["queries"]) == 5
    assert durations["fixture_setup"] >= 0.0
    assert all(
        value <= report["max_operation_seconds"]
        for value in [*durations["cold_queries"], *durations["queries"]]
    )
    assert report["cold_queries_sha256"] == report["warm_queries_sha256"]
    assert report["functional_sha256"] == report["expected_functional_sha256"]
    assert not fixture_root.exists()


@scenario("BDD-004", "retrieval")
def ad_hoc_query_is_read_only_and_filters_lifecycle(fixture_root: Path) -> None:
    from knowledge_cli import main

    repo = _build_retrieval_fixture(
        fixture_root,
        stale_advice_lifecycle="stale",
    )
    before = _tree_snapshot(repo)
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        exit_code = main(
            [
                "query",
                "--repo",
                str(repo),
                "--stage",
                "ad-hoc",
                "--query",
                "capability token",
            ]
        )

    assert exit_code == 0, f"expected query success, got {exit_code}: {stdout.getvalue()!r}"
    assert stderr.getvalue() == "", f"unexpected stderr: {stderr.getvalue()}"
    context = json.loads(stdout.getvalue())
    assert context["schema"] == "knowledge-context/v1"
    assert context["stage"] == "ad-hoc"
    assert context["query"] == "capability token"
    assert 1 <= len(context["results"]) <= 5
    assert all(result["lifecycle"] == "current" for result in context["results"])
    result_paths = {result["path"] for result in context["results"]}
    assert "docs/knowledge/incidents/stale-capability-token.md" not in result_paths
    assert "ignored/secret.md" not in result_paths
    assert all(result["source_refs"] for result in context["results"])
    assert _tree_snapshot(repo) == before


@scenario("BDD-002", "retrieval")
def requirements_query_ranks_canonical_stage_context_first(fixture_root: Path) -> None:
    from knowledge_cli import main

    repo = _build_retrieval_fixture(fixture_root)
    before = _tree_snapshot(repo)
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        exit_code = main(
            [
                "query",
                "--repo",
                str(repo),
                "--stage",
                "requirements",
                "--query",
                "capability token",
            ]
        )
    assert exit_code == 0
    assert stderr.getvalue() == ""
    context = json.loads(stdout.getvalue())
    assert context["stage"] == "requirements"
    assert len(context["results"]) <= 5
    assert context["results"][0]["authority"] == "canonical"
    assert "stage:requirements" in context["results"][0]["match_reasons"]
    for result in context["results"]:
        for source in result["source_refs"]:
            raw = (repo / Path(*source["path"].split("/"))).read_bytes()
            assert _sha256(raw) == source["sha256"]
            locator = source["locator"]
            lines = raw.decode("utf-8").replace("\r\n", "\n").splitlines()
            excerpt = "\n".join(
                lines[locator["start_line"] - 1 : locator["end_line"]]
            ).encode("utf-8")
            assert _sha256(excerpt) == source["excerpt_sha256"]
    assert _tree_snapshot(repo) == before


@scenario("BDD-003", "retrieval")
def all_megin_stages_declare_a_read_only_knowledge_preflight(fixture_root: Path) -> None:
    del fixture_root
    workspace = Path.cwd().resolve()
    owners = {
        "requirements": ".agents/skills/requirements-discovery/SKILL.md",
        "planning": ".agents/skills/technical-planning/SKILL.md",
        "implementation": ".agents/skills/implementation-execution/SKILL.md",
        "bug": ".agents/skills/bug-diagnosis/SKILL.md",
    }
    before = {
        relative: _sha256((workspace / relative).read_bytes())
        for relative in owners.values()
    }
    for stage, relative in owners.items():
        text = (workspace / relative).read_text(encoding="utf-8")
        assert "project-knowledge/scripts/knowledge_cli.py query" in text, relative
        assert f"--stage {stage}" in text, relative
        assert "read-only" in text.lower() or "唯讀" in text, relative
        assert "source_refs" in text, relative
    after = {
        relative: _sha256((workspace / relative).read_bytes())
        for relative in owners.values()
    }
    assert after == before


@scenario("BDD-005", "retrieval")
def golden_queries_meet_recall_citation_and_eligibility_gates(fixture_root: Path) -> None:
    repo, cases = _build_golden_fixture(fixture_root)
    before = _tree_snapshot(repo)
    report = _evaluate_golden(repo, cases)
    assert report["queries"] == 20
    assert report["top_five_hits"] >= 18
    assert report["citation_count"] > 0
    assert report["valid_citations"] == report["citation_count"]
    assert report["ineligible_hits"] == 0
    assert _tree_snapshot(repo) == before


@scenario("BDD-001", "governance")
def bootstrap_seals_only_trusted_terminal_artifacts(fixture_root: Path) -> None:
    from knowledge_cli import main

    repo = _build_governance_fixture(fixture_root)
    registry = fixture_root / "registry"
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
        exit_code = main([
            "bootstrap", "--repo", str(repo),
            "--approval-actor", "bootstrap-owner",
            "--approval-evidence", "fixture:bootstrap-approved",
        ])
    assert exit_code == 0, f"expected bootstrap success, got {exit_code}: {stdout.getvalue()!r}"
    assert stderr.getvalue() == ""
    result = json.loads(stdout.getvalue())
    assert result["schema"] == "human-gate-summary/v1"
    classification = result["summary"]["classification"]
    assert classification["terminal"] == [
        "docs/work/work-alpha/requirements.md"
    ]
    assert "docs/work/work-alpha/plan/plan.md" in classification["candidate"]
    assert sorted(classification["conflict"]) == [
        "docs/legacy/status.json",
        "docs/legacy/status.md",
    ]
    candidate_ref = result["identity"]["candidate_ref"]
    assert candidate_ref.startswith("knowledge:candidates/")
    candidate_path = (
        registry
        / "repos"
        / result["identity"]["repo_id"]
        / Path(*candidate_ref.removeprefix("knowledge:").split("/"))
    )
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    assert candidate["schema"] == "knowledge-candidate/v1"
    assert sorted(source["path"] for source in candidate["source_snapshot"]) == [
        "docs/legacy/status.json",
        "docs/legacy/status.md",
        "docs/work/work-alpha/requirements.md",
    ]
    catalog_operation = next(
        item
        for item in candidate["operations"]
        if item["path"] == "docs/knowledge/topics/bootstrap-trusted-artifacts.md"
    )
    postimage_ref = catalog_operation["postimage_ref"]
    postimage = (
        candidate_path.parent / Path(*postimage_ref.split("/"))
    ).read_text(encoding="utf-8")
    assert "docs/work/work-alpha/requirements.md" in postimage
    assert "docs/work/work-alpha/plan/plan.md" not in postimage
    assert "docs/legacy/status" not in postimage
    assert {
        "docs/knowledge/index.md",
        "docs/knowledge/glossary.md",
        "docs/knowledge/log.md",
        f"docs/knowledge/meta/promotions/{candidate['promotion_id']}.json",
    }.issubset({item["path"] for item in candidate["operations"]})
    assert _tree_snapshot(repo) == before


@scenario("BDD-021", "presentation")
def candidate_seal_persists_an_immutable_review_manifest(fixture_root: Path) -> None:
    from knowledge_promotion import seal_candidate_draft

    repo = _build_promotion_fixture(fixture_root)
    registry = fixture_root / "review-registry"
    before = _tree_snapshot(repo)
    draft = {
        "schema": "knowledge-candidate-draft/v1",
        "stage": "implementation",
        "work_id": "work-review-manifest",
        "decision": "change",
        "source_snapshot": [],
        "operations": [
            {
                "kind": "create",
                "path": "docs/knowledge/topics/review-manifest.md",
                "postimage": "# Review manifest\n",
            },
            {
                "kind": "create",
                "path": "docs/knowledge/topics/review-manifest-details.md",
                "postimage": "# Review manifest details\n",
            },
        ],
    }
    with mock.patch(
        "knowledge_governance.default_registry_root",
        return_value=registry,
    ):
        sealed = seal_candidate_draft(
            str(repo),
            draft=draft,
            approval_actor="review-owner",
            approval_evidence="fixture:review-manifest",
        )

    assert sealed.get("review_sha256"), "sealed Candidate has no review digest"
    assert sealed.get("review_ref"), "sealed Candidate has no review ref"
    candidate_path = (
        registry
        / "repos"
        / sealed["repo_id"]
        / Path(*sealed["candidate_ref"].removeprefix("knowledge:").split("/"))
    )
    review_path = candidate_path.with_name("review.json")
    assert review_path.is_file(), "review.json was not published with the Candidate"
    review_raw = review_path.read_bytes()
    assert _sha256(review_raw) == sealed["review_sha256"]
    review = json.loads(review_raw)
    assert review["schema"] == "human-gate-review/v1"
    assert review["identity"]["candidate_ref"] == sealed["candidate_ref"]
    assert review["identity"]["payload_sha256"] == sealed["payload_sha256"]
    manifest = review["review_bundle"]["manifest"]
    expected_stored = {
        "candidate.json",
        *(
            operation["postimage_ref"]
            for operation in json.loads(candidate_path.read_text(encoding="utf-8"))[
                "operations"
            ]
        ),
    }
    assert {item["stored_path"] for item in manifest} == expected_stored
    for item in manifest:
        stored = candidate_path.parent / Path(*item["stored_path"].split("/"))
        assert stored.is_file()
        raw = stored.read_bytes()
        assert len(raw) == item["byte_count"]
        assert _sha256(raw) == item["sha256"]
    assert review["validation"]["outcome"] == "passed"
    assert _tree_snapshot(repo) == before


@scenario("BDD-022", "presentation")
def human_gate_cli_is_summary_only_for_large_payloads(fixture_root: Path) -> None:
    from knowledge_cli import main

    sentinel = "FULL_PAYLOAD_SENTINEL_BDD_022_6fce5df8"
    repo = _build_promotion_fixture(fixture_root)
    registry = fixture_root / "summary-only-registry"
    draft_path = repo / "candidate-draft.json"
    _write(
        draft_path,
        json.dumps(
            {
                "schema": "knowledge-candidate-draft/v1",
                "stage": "implementation",
                "work_id": "work-summary-only",
                "decision": "change",
                "source_snapshot": [],
                "operations": [
                    {
                        "kind": "create",
                        "path": "docs/knowledge/topics/large-review.md",
                        "postimage": "# Large review\n\n" + ("payload line\n" * 12_000) + sentinel,
                    }
                ],
            },
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        + "\n",
    )

    def invoke(arguments: list[str]) -> tuple[int, dict[str, object], str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            mock.patch(
                "knowledge_governance.default_registry_root",
                return_value=registry,
            ),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            exit_code = main(arguments)
        rendered = stdout.getvalue()
        assert exit_code == 0, stderr.getvalue()
        return exit_code, json.loads(rendered), rendered

    _, candidate_summary, candidate_rendered = invoke(
        [
            "candidate",
            "--repo",
            str(repo),
            "--draft",
            str(draft_path),
            "--approval-actor",
            "review-owner",
            "--approval-evidence",
            "fixture:summary-only",
        ]
    )
    candidate_ref = str(candidate_summary["identity"]["candidate_ref"])
    _, review_summary, review_rendered = invoke(
        ["review", "--repo", str(repo), "--candidate-ref", candidate_ref]
    )

    expected_keys = {
        "schema",
        "gate",
        "summary",
        "risk_and_compatibility",
        "validation",
        "review_bundle",
        "identity",
        "prompt",
    }
    for summary, rendered in (
        (candidate_summary, candidate_rendered),
        (review_summary, review_rendered),
    ):
        assert summary["schema"] == "human-gate-summary/v1"
        assert set(summary) == expected_keys
        assert summary["summary"]["purpose"] == (
            "Review the standalone Knowledge Candidate and proposed observed knowledge "
            "changes before approval."
        )
        assert summary["summary"]["change"]["description"] == (
            "Publish the standalone Candidate's proposed observed knowledge revision."
        )
        assert set(summary["risk_and_compatibility"]["material"]) == {
            "bug_assessment",
            "occurrence",
            "implementation_outcome",
        }
        assert sentinel not in rendered
        assert '"postimage":' not in rendered
        assert '"postimages":' not in rendered
        assert summary["prompt"] == "Approve this exact review bundle or request modifications."
        manifest = summary["review_bundle"]["manifest"]
        assert manifest
        for item in manifest:
            direct_path = Path(str(item["direct_path"]))
            assert direct_path.is_absolute()
            assert direct_path.is_file()
        review_path = Path(str(summary["review_bundle"]["direct_path"]))
        assert review_path.is_absolute()
        assert review_path.is_file()
        assert summary["identity"]["review_sha256"] == summary["review_bundle"]["review_sha256"]


@scenario("BDD-023", "presentation")
def composite_human_gates_share_one_file_first_authority(fixture_root: Path) -> None:
    import validate_contracts as knowledge_contracts

    workspace = SCRIPT_DIR.parents[3]
    authority_path = (
        workspace
        / ".agents/skills/project-knowledge/references/human-gate-review.md"
    )
    assert authority_path.is_file(), "shared human Gate authority is missing"
    authority = authority_path.read_text(encoding="utf-8")
    required_categories = (
        "`gate`",
        "`summary`",
        "`risk_and_compatibility`",
        "`validation`",
        "`review_bundle`",
        "`identity`",
        "`prompt`",
    )
    assert all(category in authority for category in required_categories)
    prompt = "Approve this exact review bundle or request modifications."
    assert authority.count(prompt) == 1

    owner_inventory = {
        ".agents/skills/requirements-discovery/references/delivery-protocol.md": (
            "Human Gate bundle inventory",
            "Requirements primary",
            "Knowledge postimages",
            "BUG assessment Markdown and JSON",
        ),
        ".agents/skills/technical-planning/references/delivery-protocol.md": (
            "Human Gate bundle inventory",
            "plan primary",
            "handoff.json",
            "supporting artifacts",
            "occurrence_map.yaml",
            "Knowledge postimages",
        ),
        ".agents/skills/project-knowledge/SKILL.md": (
            "Human Gate bundle inventory",
            "candidate.json",
            "review.json",
            "postimages/",
        ),
        ".agents/skills/bug-diagnosis/SKILL.md": (
            "Human Gate bundle inventory",
            "BUG assessment Markdown and JSON",
            "Requirements Gate",
        ),
        ".agents/skills/delivery-orchestrator/references/stage-routing.md": (
            "Human Gate bundle inventory",
            "Requirements",
            "Plan",
            "Knowledge",
        ),
        ".agents/skills/implementation-execution/references/delivery-protocol.md": (
            "Human Gate bundle inventory",
            "implementation-outcome/v1",
            "Knowledge Candidate",
        ),
    }
    corpus = authority
    for relative, markers in owner_inventory.items():
        text = (workspace / Path(*relative.split("/"))).read_text(encoding="utf-8")
        assert ".agents/skills/project-knowledge/references/human-gate-review.md" in text
        assert all(marker in text for marker in markers), (relative, markers)
        corpus += "\n" + text
    assert corpus.count(prompt) == 1, "owner files must not duplicate the canonical prompt"
    assert "Present all returned" not in corpus
    owner_roots = (
        ".agents/skills/requirements-discovery/",
        ".agents/skills/technical-planning/",
        ".agents/skills/delivery-orchestrator/",
        ".agents/skills/bug-diagnosis/",
        ".agents/skills/implementation-execution/",
        ".agents/skills/project-knowledge/",
    )
    active_gate_paths = tuple(
        sorted(
            path.relative_to(workspace).as_posix()
            for root in owner_roots
            for path in (workspace / Path(*root.split("/"))).rglob("*.md")
            if path.is_file()
            and not path.relative_to(workspace)
            .as_posix()
            .endswith("/scripts/behavior-evaluation-report.md")
        )
    )
    assert active_gate_paths == knowledge_contracts.human_gate_active_instruction_paths()
    assert {
        ".agents/skills/requirements-discovery/references/behavior-evaluation.md",
        ".agents/skills/technical-planning/references/behavior-evaluation.md",
        ".agents/skills/delivery-orchestrator/references/behavior-evaluation.md",
    }.issubset(active_gate_paths)
    for relative in active_gate_paths:
        text = (workspace / Path(*relative.split("/"))).read_text(encoding="utf-8")
        assert not knowledge_contracts.contradictory_human_gate_instruction_lines(text), relative
    mixed_marker_contradictions = (
        "Summary-only Chat: present all returned Candidate files in Chat for approval.",
        "Summary-only Chat: paste the complete payload into Chat for approval.",
        "Summary and direct links: show the entire payload before approval.",
    )
    for instruction in mixed_marker_contradictions:
        assert knowledge_contracts.contradictory_human_gate_instruction_lines(
            instruction
        ), instruction
    allowed_presentation_instructions = (
        "Summary-only Chat: do not paste the complete payload into Chat for approval.",
        "Summary and direct links: never show the entire payload before approval.",
        "不得在 Chat 完整展示 Candidate；只提供摘要與直接連結。",
        "封存新版完整 bundle、以摘要和直接連結呈現並重新核准。",
    )
    for instruction in allowed_presentation_instructions:
        assert not knowledge_contracts.contradictory_human_gate_instruction_lines(
            instruction
        ), instruction
    report = _exercise_planning_co_promotion(fixture_root)
    assert any(path.endswith("/occurrence_map.yaml") for path in report["formal_paths"])
    assert report["occurrence_summary"]["change_mode"] == "bulk_edit"
    assert report["occurrence_summary"]["manual_review_item_count"] == 2
    assert report["occurrence_summary"]["classification_risk"] == (
        "manual-review-required"
    )
    assert OCCURRENCE_REASON_SENTINEL not in report["summary_rendered"]
    bug_report = _exercise_requirements_co_promotion(
        fixture_root,
        include_bug_assessment=True,
    )
    assert len(bug_report["review_targets"]) == 2
    assert any(path.endswith(".md") for path in bug_report["review_targets"])
    assert any(path.endswith(".json") for path in bug_report["review_targets"])
    assert bug_report["preapproval_absent"] is True
    assert bug_report["collision_code"] == "PREIMAGE_DRIFT"
    assert bug_report["collision_zero_mutation"] is True
    assert bug_report["assessment_materialized"] is True
    assert bug_report["bug_assessment_summary"]["verdict"] == "likely"
    assert bug_report["bug_assessment_summary"]["classification_risk"] == (
        "uncertain-diagnosis"
    )
    assert "The public command returns an incorrect result." not in bug_report[
        "summary_rendered"
    ]


@scenario("BDD-024", "presentation")
def knowledge_gate_entrypoints_resume_one_review_before_apply(fixture_root: Path) -> None:
    from knowledge_cli import main

    report = _exercise_implementation_knowledge_gate(fixture_root)
    assert report["awaiting_phase"] == "knowledge"
    assert report["awaiting_status"] == "awaiting_user"
    assert report["review_resumable"] is True
    assert report["review_sha256"]
    assert report["outcome_summary"]["work_kind"] == "standard"
    assert report["outcome_summary"]["result"] == "complete"
    assert report["outcome_review_targets"] == report["outcome_paths"]
    assert report["gate_purpose"] == (
        "Review the implementation Outcome and proposed observed knowledge changes "
        "before approval."
    )
    assert report["gate_change"]["description"] == (
        "Publish an implementation Outcome-derived knowledge revision."
    )

    repo = _build_governance_fixture(fixture_root)
    registry = fixture_root / "entrypoint-review-registry"

    def invoke(arguments: list[str]) -> tuple[dict[str, object], str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            mock.patch(
                "knowledge_governance.default_registry_root",
                return_value=registry,
            ),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            exit_code = main(arguments)
        assert exit_code == 0, stderr.getvalue()
        return json.loads(stdout.getvalue()), stdout.getvalue()

    bootstrap, bootstrap_rendered = invoke(
        [
            "bootstrap",
            "--repo",
            str(repo),
            "--approval-actor",
            "bootstrap-owner",
            "--approval-evidence",
            "fixture:file-first-bootstrap",
        ]
    )
    assert bootstrap["schema"] == "human-gate-summary/v1"
    assert bootstrap["identity"]["stage"] == "bootstrap"
    assert '"postimages":' not in bootstrap_rendered
    assert bootstrap["summary"]["classification"]["conflict"]
    resumed_bootstrap, resumed_bootstrap_rendered = invoke(
        [
            "review",
            "--repo",
            str(repo),
            "--candidate-ref",
            str(bootstrap["identity"]["candidate_ref"]),
        ]
    )
    assert resumed_bootstrap["summary"] == bootstrap["summary"]
    assert resumed_bootstrap["identity"]["review_sha256"] == bootstrap["identity"][
        "review_sha256"
    ]
    assert resumed_bootstrap_rendered == bootstrap_rendered

    repo = _build_retrieval_fixture(fixture_root)
    registry = fixture_root / "entrypoint-review-registry"
    _write(
        repo / "src/stale-boundary.md",
        "Changed stale advice must not be silently trusted.\n",
    )

    repair, repair_rendered = invoke(
        [
            "lint",
            "--repo",
            str(repo),
            "--approval-actor",
            "repair-owner",
            "--approval-evidence",
            "fixture:file-first-repair",
        ]
    )
    assert repair["schema"] == "human-gate-summary/v1"
    assert repair["identity"]["stage"] == "lint-repair"
    assert repair["summary"]["lint"]["diagnostic_count"] > 0
    assert '"postimages":' not in repair_rendered
    automatic_entries = [
        item
        for item in repair["review_bundle"]["manifest"]
        if item["role"] == "automatic"
    ]
    assert len(automatic_entries) == 1
    lint_bytes = Path(str(automatic_entries[0]["direct_path"])).read_bytes()
    assert _sha256(lint_bytes) == automatic_entries[0]["sha256"]
    assert len(lint_bytes) == automatic_entries[0]["byte_count"]
    raw_lint = json.loads(lint_bytes)
    assert raw_lint["schema"] == "knowledge-lint/v1"
    assert raw_lint["repair_candidate_ref"] == repair["identity"]["candidate_ref"]
    assert raw_lint["repair_candidate_payload_sha256"] == repair["identity"]["payload_sha256"]
    resumed_repair, resumed_repair_rendered = invoke(
        [
            "review",
            "--repo",
            str(repo),
            "--candidate-ref",
            str(repair["identity"]["candidate_ref"]),
        ]
    )
    assert resumed_repair["summary"] == repair["summary"]
    assert resumed_repair["identity"]["review_sha256"] == repair["identity"][
        "review_sha256"
    ]
    assert resumed_repair_rendered == repair_rendered


@scenario("BDD-025", "presentation")
def drift_legacy_and_automatic_outputs_preserve_compatibility(fixture_root: Path) -> None:
    report = _exercise_human_gate_compatibility(fixture_root)
    assert report["apply_lint"] == "passed"
    assert report["automatic_schema"] == "knowledge-lint/v1"
    assert report["historical_ready_preserved"] is True
    assert report["legacy_reseal_required"] is True
    assert report["review_drift_rejected"] is True
    assert report["cross_role_collision_codes"] == [
        "REVIEW_TARGET_COLLISION",
        "REVIEW_TARGET_COLLISION",
    ]
    assert report["cross_role_collision_zero_mutation"] is True


@scenario("BDD-009", "governance")
def legacy_machine_human_conflict_is_quarantined_without_precedence(fixture_root: Path) -> None:
    from knowledge_cli import main
    from knowledge_governance import classify_repository

    repo = _build_governance_fixture(fixture_root)
    registry = fixture_root / "registry"
    before = _tree_snapshot(repo)
    stdout = io.StringIO()
    stderr = io.StringIO()
    with (
        mock.patch(
            "knowledge_governance.default_registry_root",
            return_value=registry,
        ),
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
    ):
        exit_code = main([
            "bootstrap", "--repo", str(repo),
            "--approval-actor", "bootstrap-owner",
            "--approval-evidence", "fixture:bootstrap-approved",
        ])
    assert exit_code == 0, stderr.getvalue()
    result = json.loads(stdout.getvalue())
    quarantine_ref = result["identity"]["candidate_ref"]
    assert quarantine_ref, "conflict must produce a separate quarantine Candidate"
    candidate_path = (
        registry
        / "repos"
        / result["identity"]["repo_id"]
        / Path(*quarantine_ref.removeprefix("knowledge:").split("/"))
    )
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    assert sorted(source["path"] for source in candidate["source_snapshot"]) == [
        "docs/legacy/status.json",
        "docs/legacy/status.md",
        "docs/work/work-alpha/requirements.md",
    ]
    sidecar_operation = next(
        operation
        for operation in candidate["operations"]
        if operation["path"].endswith("page-legacy-status-conflict.json")
    )
    sidecar = json.loads(
        (candidate_path.parent / Path(*sidecar_operation["postimage_ref"].split("/"))).read_text(
            encoding="utf-8"
        )
    )
    assert sidecar["lifecycle"] == "contested"
    assert len(sidecar["claims"]) == 2
    assert all(claim["lifecycle"] == "contested" for claim in sidecar["claims"])
    assert all(claim["contradicts"] == [] for claim in sidecar["claims"])

    json_path = repo / "docs/legacy/status.json"
    markdown_path = repo / "docs/legacy/status.md"
    original_json = json_path.read_bytes()
    original_markdown = markdown_path.read_bytes()
    _write(json_path, json.dumps({"schema": "legacy-status/v1", "status": "Candidate"}) + "\n")
    assert classify_repository(repo)["conflict"] == []
    json_path.write_bytes(original_json)
    _write(markdown_path, "# Legacy status\n\nStatus: Ready\n")
    assert classify_repository(repo)["conflict"] == []
    markdown_path.write_bytes(original_markdown)
    assert _tree_snapshot(repo) == before


@scenario("BDD-012", "governance")
def stale_source_drift_is_excluded_and_gets_a_repair_candidate(fixture_root: Path) -> None:
    from knowledge_cli import main
    from knowledge_governance import lint_repository

    repo = _build_retrieval_fixture(fixture_root)
    registry = fixture_root / "registry"
    stale_source = repo / "src/stale-boundary.md"
    stale_source.write_text(
        "Changed stale advice must not be silently trusted.\n",
        encoding="utf-8",
        newline="\n",
    )

    query_stdout = io.StringIO()
    query_stderr = io.StringIO()
    with contextlib.redirect_stdout(query_stdout), contextlib.redirect_stderr(query_stderr):
        query_exit = main(
            [
                "query",
                "--repo",
                str(repo),
                "--stage",
                "requirements",
                "--query",
                "capability token",
            ]
        )
    assert query_exit == 0, query_stderr.getvalue()
    query_result = json.loads(query_stdout.getvalue())
    assert "docs/knowledge/incidents/stale-capability-token.md" not in {
        item["path"] for item in query_result["results"]
    }

    lint_stdout = io.StringIO()
    lint_stderr = io.StringIO()
    with (
        mock.patch("knowledge_governance.default_registry_root", return_value=registry),
        contextlib.redirect_stdout(lint_stdout),
        contextlib.redirect_stderr(lint_stderr),
    ):
        lint_exit = main([
            "lint", "--repo", str(repo),
            "--approval-actor", "repair-owner",
            "--approval-evidence", "fixture:repair-approved",
        ])
    assert lint_exit == 0, f"lint failed: {lint_stderr.getvalue()}"
    lint = json.loads(lint_stdout.getvalue())
    raw_lint = lint_repository(str(repo))
    assert lint["schema"] == "human-gate-summary/v1"
    assert lint["summary"]["lint"]["outcome"] == "failed"
    assert "SOURCE_HASH_DRIFT" in lint["summary"]["lint"]["diagnostic_codes"]
    assert any(
        item["code"] == "SOURCE_HASH_DRIFT"
        and item["path"]
        == "docs/knowledge/meta/pages/page-stale-capability-token.json"
        for item in raw_lint["diagnostics"]
    )
    repair_ref = lint["identity"]["candidate_ref"]
    assert repair_ref, "source drift must produce a repair Candidate"
    candidate_path = (
        registry
        / "repos"
        / lint["identity"]["repo_id"]
        / Path(*repair_ref.removeprefix("knowledge:").split("/"))
    )
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    operation = next(
        item
        for item in candidate["operations"]
        if item["path"].endswith("page-stale-capability-token.json")
    )
    repaired = json.loads(
        (candidate_path.parent / Path(*operation["postimage_ref"].split("/"))).read_text(
            encoding="utf-8"
        )
    )
    assert repaired["lifecycle"] == "stale"
    assert all(claim["lifecycle"] == "stale" for claim in repaired["claims"])


@scenario("BDD-014", "governance")
def valid_contradiction_requires_decision_and_never_uses_recency(fixture_root: Path) -> None:
    from knowledge_cli import main
    from knowledge_governance import lint_repository

    repo = _build_contradiction_fixture(fixture_root)
    registry = fixture_root / "registry"
    older = repo / "docs/knowledge/decisions/quorum-alpha.md"
    newer = repo / "docs/knowledge/decisions/quorum-beta.md"
    os.utime(older, (1_600_000_000, 1_600_000_000))
    os.utime(newer, (1_700_000_000, 1_700_000_000))

    query_stdout = io.StringIO()
    query_stderr = io.StringIO()
    with contextlib.redirect_stdout(query_stdout), contextlib.redirect_stderr(query_stderr):
        query_exit = main(
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
    assert query_exit == 0, query_stderr.getvalue()
    query = json.loads(query_stdout.getvalue())
    assert query["results"] == [], "contradictory claims and their sources must not auto-inject"

    lint_stdout = io.StringIO()
    lint_stderr = io.StringIO()
    with (
        mock.patch("knowledge_governance.default_registry_root", return_value=registry),
        contextlib.redirect_stdout(lint_stdout),
        contextlib.redirect_stderr(lint_stderr),
    ):
        lint_exit = main([
            "lint", "--repo", str(repo),
            "--approval-actor", "repair-owner",
            "--approval-evidence", "fixture:repair-approved",
        ])
    assert lint_exit == 0, lint_stderr.getvalue()
    lint = json.loads(lint_stdout.getvalue())
    raw_lint = lint_repository(str(repo))
    assert lint["schema"] == "human-gate-summary/v1"
    assert lint["summary"]["lint"]["outcome"] == "decision_required"
    assert "CONTRADICTION_DECISION_REQUIRED" in lint["summary"]["lint"]["diagnostic_codes"]
    assert raw_lint["eligible_claim_ids"] == []
    repair_ref = lint["identity"]["candidate_ref"]
    assert repair_ref
    candidate_path = (
        registry
        / "repos"
        / lint["identity"]["repo_id"]
        / Path(*repair_ref.removeprefix("knowledge:").split("/"))
    )
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    sidecar_operations = [
        operation
        for operation in candidate["operations"]
        if operation["path"].startswith("docs/knowledge/meta/pages/")
    ]
    assert len(sidecar_operations) == 2
    assert any(operation["path"] == "docs/knowledge/index.md" for operation in candidate["operations"])
    for operation in sidecar_operations:
        postimage = json.loads(
            (candidate_path.parent / Path(*operation["postimage_ref"].split("/"))).read_text(
                encoding="utf-8"
            )
        )
        assert postimage["lifecycle"] == "contested"
        assert all(claim["lifecycle"] == "contested" for claim in postimage["claims"])


@scenario("BDD-013", "promotion")
def candidate_preimage_drift_has_zero_commits_and_is_retriable(fixture_root: Path) -> None:
    from knowledge_cli import main

    repo = _build_governance_fixture(fixture_root)
    registry = fixture_root / "registry"
    bootstrap_stdout = io.StringIO()
    with (
        mock.patch("knowledge_governance.default_registry_root", return_value=registry),
        contextlib.redirect_stdout(bootstrap_stdout),
    ):
        bootstrap_exit = main([
            "bootstrap", "--repo", str(repo),
            "--approval-actor", "bootstrap-owner",
            "--approval-evidence", "fixture:bootstrap-approved",
        ])
    assert bootstrap_exit == 0
    bootstrap = json.loads(bootstrap_stdout.getvalue())
    candidate_ref = bootstrap["identity"]["candidate_ref"]
    review_sha256 = bootstrap["review_bundle"]["review_sha256"]

    unexpected = repo / "docs/knowledge/glossary.md"
    _write(unexpected, "# Concurrent writer\n")
    before_apply = _tree_snapshot(repo)
    stdout = io.StringIO()
    stderr = io.StringIO()
    with (
        mock.patch("knowledge_governance.default_registry_root", return_value=registry),
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
    ):
        try:
            exit_code = main(
                [
                    "apply",
                    "--repo",
                    str(repo),
                    "--candidate-ref",
                    candidate_ref,
                    "--review-sha256",
                    review_sha256,
                    "--approval-actor",
                    "bootstrap-owner",
                    "--approval-evidence",
                    "fixture:bootstrap-approved",
                ]
            )
        except SystemExit as exc:
            exit_code = int(exc.code)
    assert exit_code == 3, f"expected typed drift exit 3, got {exit_code}"
    assert stdout.getvalue() == ""
    error = json.loads(stderr.getvalue())
    assert error["schema"] == "knowledge-error/v1"
    assert error["code"] == "PREIMAGE_DRIFT"
    assert error["recoverable"] is True
    assert _tree_snapshot(repo) == before_apply
    assert not list(repo.glob("docs/knowledge/meta/promotions/*.json"))


@scenario("BDD-015", "governance")
def complete_lint_reports_every_failure_family_without_writes(fixture_root: Path) -> None:
    from knowledge_cli import main

    repo = _build_complete_lint_fixture(fixture_root)
    registry = fixture_root / "registry"
    before = _tree_snapshot(repo)
    stdout = io.StringIO()
    stderr = io.StringIO()
    with (
        mock.patch("knowledge_governance.default_registry_root", return_value=registry),
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
    ):
        exit_code = main([
            "lint", "--repo", str(repo),
        ])
    assert exit_code == 0, stderr.getvalue()
    assert stderr.getvalue() == ""
    report = json.loads(stdout.getvalue())
    assert report["outcome"] == "failed"
    codes = {item["code"] for item in report["diagnostics"]}
    expected = {
        "SOURCE_REF_MISSING",
        "SOURCE_HASH_DRIFT",
        "BACKLINK_MISSING",
        "ORPHAN_PAGE",
        "PAGE_ID_DUPLICATE",
        "INDEX_DRIFT",
        "PROMOTION_LOG_DRIFT",
        "LIFECYCLE_INVALID",
        "CONTRADICTION_ASYMMETRIC",
    }
    assert expected <= codes, sorted(expected - codes)
    problematic = {
        "claim-no-provenance",
        "claim-stale-source",
        "claim-illegal-state",
    }
    assert problematic.isdisjoint(report["eligible_claim_ids"])
    assert report.get("repair_candidate_ref") is None
    assert _tree_snapshot(repo) == before


@scenario("BDD-017", "promotion")
def promotion_security_faults_and_recovery_fail_closed(fixture_root: Path) -> None:
    report = _exercise_promotion_security_and_recovery(fixture_root)
    assert report["safety_codes"] == [
        "SECRET_DETECTED",
        "TARGET_IGNORED",
        "TARGET_NOT_ALLOWED",
        "TARGET_REDIRECTED",
        "UNSAFE_PATH",
    ]
    assert report["faults"] == [
        "before-replace-0",
        "after-replace-0",
        "before-lint",
        "after-lint",
    ]
    assert report["git_commands"] > 0
    assert report["recovery"] == "recovered"


@scenario("BDD-006", "promotion")
def requirements_and_knowledge_share_one_approval_and_gate(fixture_root: Path) -> None:
    report = _exercise_requirements_co_promotion(fixture_root)
    assert len(report["affected_paths"]) == 6
    assert "docs/knowledge/log.md" in report["affected_paths"]
    assert sum(
        path.startswith("docs/knowledge/meta/promotions/")
        for path in report["affected_paths"]
    ) == 1
    assert report["next_phase"] == "planning"
    assert report["lint"] == "passed"


@scenario("BDD-007", "promotion")
def plan_and_planned_knowledge_share_one_approval_and_gate(fixture_root: Path) -> None:
    report = _exercise_planning_co_promotion(fixture_root)
    assert report["next_phase"] == "implementation"
    assert report["evidence_classes"] == ["planned"]
    assert report["promotion_count"] == 2
    assert report["lint"] == "passed"


@scenario("BDD-008", "delivery")
def reviewed_implementation_waits_for_an_approved_knowledge_promotion(
    fixture_root: Path,
) -> None:
    report = _exercise_implementation_knowledge_gate(fixture_root)
    assert (report["awaiting_phase"], report["awaiting_status"]) == (
        "knowledge",
        "awaiting_user",
    )
    assert report["completed_phase"] == "complete"
    assert report["product_snapshot_stable"] is True
    assert len(report["outcome_paths"]) == 2
    assert report["lint"] == "passed"


@scenario("BDD-010", "delivery")
def verified_bug_becomes_verified_incident_knowledge(fixture_root: Path) -> None:
    report = _exercise_bug_knowledge_mapping(fixture_root, result="verified")
    assert report["evidence_classes"] == ["verified"]
    assert report["lifecycle"] == "current"
    assert report["source_refs"]
    assert "Original symptom before change: present" in report["page_text"]
    assert "Original symptom after change: absent" in report["page_text"]
    assert "BDD-001" in report["page_text"]
    assert "TEST-001" in report["page_text"]
    assert report["lint"] == "passed"


@scenario("BDD-011", "delivery")
def partial_bug_stays_unresolved_and_never_claims_a_fix(fixture_root: Path) -> None:
    report = _exercise_bug_knowledge_mapping(fixture_root, result="partial")
    assert report["evidence_classes"] == ["partial"]
    assert report["lifecycle"] == "current"
    assert report["source_refs"]
    assert "Status: Partial / Unresolved" in report["page_text"]
    assert "Proxy evidence" in report["page_text"]
    assert "Residual risks" in report["page_text"]
    assert "Follow-up" in report["page_text"]
    assert re.search(r"(?i)\b(?:fixed|resolved)\b|已修復|已解決", report["page_text"]) is None
    assert report["overclaim_rejected"] == "BUG_VERIFICATION_INVALID"
    assert report["lint"] == "passed"


@scenario("BDD-016", "delivery")
def cross_platform_results_and_large_repository_operations_are_bounded(
    fixture_root: Path,
) -> None:
    from knowledge_benchmark import run_benchmark

    persisted_report = os.environ.get("KNOWLEDGE_PORTABILITY_REPORT")
    if persisted_report:
        report = json.loads(Path(persisted_report).read_text(encoding="utf-8"))
    else:
        report = run_benchmark(fixture_root)
    assert report["schema"] == "knowledge-portability-report/v1"
    assert report["host"]["os"] in {"windows", "linux"}
    assert report["outcome"] == "passed", json.dumps(
        {
            "durations_seconds": report.get("durations_seconds"),
            "functional_sha256": report.get("functional_sha256"),
            "expected_functional_sha256": report.get("expected_functional_sha256"),
            "file_count": report.get("file_count"),
            "page_count": report.get("page_count"),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    assert report["file_count"] == 50_000
    assert report["page_count"] == 5_000
    assert report["tracked_fixture"] is True
    assert report["total_fixture_files"] == 50_000
    assert report["source_file_count"] == 39_998
    assert report["functional_sha256"] == report["expected_functional_sha256"]
    assert len(report["durations_seconds"]["queries"]) == 5
    assert all(
        duration <= 2.0
        for duration in [
            *report["durations_seconds"]["queries"],
            report["durations_seconds"]["index_candidate"],
        ]
    )


class _ScenarioCase(unittest.TestCase):
    scenario_id = ""
    scenario_function: Scenario
    fixture_root: Path

    def runTest(self) -> None:
        self.scenario_function(self.fixture_root)


def _run(selected: list[str], fixture_root: Path) -> tuple[int, dict[str, object]]:
    suite = unittest.TestSuite()
    for identifier in selected:
        group, function = SCENARIOS[identifier]
        case = _ScenarioCase()
        case.scenario_id = identifier
        case.scenario_function = function
        case.fixture_root = fixture_root
        case._testMethodDoc = f"{identifier} [{group}]"
        suite.addTest(case)

    stream = io.StringIO()
    try:
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    finally:
        _remove_fixture(fixture_root)
    report = {
        "schema": "knowledge-bdd-report/v1",
        "discovered": len(selected),
        "selected": selected,
        "run": result.testsRun,
        "failed": len(result.failures) + len(result.errors),
        "skipped": len(result.skipped),
        "details": stream.getvalue(),
    }
    success = (
        result.wasSuccessful()
        and result.testsRun == len(selected)
        and not result.skipped
        and not fixture_root.exists()
    )
    return (0 if success else 1), report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list-scenarios", action="store_true")
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--group", choices=sorted(GROUP_SCENARIOS))
    target.add_argument("--functional-shard", type=_functional_shard)
    parser.add_argument(
        "--fixture-root",
        type=Path,
        default=(
            Path(os.environ["KNOWLEDGE_TEST_WORKER_ROOT"]) / "fixture"
            if os.environ.get("KNOWLEDGE_TEST_WORKER_ROOT")
            else Path(".knowledge-test-tmp")
        ),
    )
    parser.add_argument("--validation-profile", choices=["local", "release"])
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--exclude-performance", action="store_true")
    selection.add_argument("--performance-only", action="store_true")
    args = parser.parse_args(argv)
    if args.functional_shard is not None:
        if args.exclude_performance or args.performance_only:
            parser.error("functional shard cannot be combined with performance selection")
        selected = functional_shard_scenarios(*args.functional_shard)
    else:
        selected = (
            list(SCENARIOS)
            if args.group is None
            else list(GROUP_SCENARIOS[args.group])
        )
    if args.exclude_performance:
        selected = [
            identifier
            for identifier in selected
            if identifier not in SEQUENTIAL_PERFORMANCE_SCENARIOS
        ]
    elif args.performance_only:
        selected = [
            identifier
            for identifier in selected
            if identifier in SEQUENTIAL_PERFORMANCE_SCENARIOS
        ]
    selected = validation_profile_scenarios(selected, args.validation_profile)
    missing = sorted(set(selected) - set(SCENARIOS))
    if missing:
        parser.error(f"scenario group references unknown IDs: {', '.join(missing)}")
    if args.list_scenarios:
        print(
            json.dumps(
                {
                    "schema": "knowledge-bdd-discovery/v1",
                    "discovered": len(SCENARIOS),
                    "run": 0,
                    "failed": 0,
                    "skipped": 0,
                    "scenarios": [
                        {"id": identifier, "group": SCENARIOS[identifier][0]}
                        for identifier in sorted(SCENARIOS)
                    ],
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    code, report = _run(selected, args.fixture_root.resolve())
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
