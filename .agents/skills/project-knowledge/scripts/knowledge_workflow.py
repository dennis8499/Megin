"""SDLC stage Candidate construction and promotion-gate validation."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from knowledge_governance import (
    _ready_plan_contract_errors,
    _trusted_ready_plan_paths,
    lint_repository,
    render_index,
)
from knowledge_query import (
    KnowledgeError,
    _eligible_paths,
    normalized_path,
    sha256_bytes,
)


WORK_ID_RE = re.compile(r"^(?=[a-z0-9-]{3,64}$)[a-z0-9]+(?:-[a-z0-9]+)*$")
STAGE_POLICY = {
    "requirements": {
        "evidence_class": "required",
        "page_directory": "topics",
        "next_phase": "planning",
    },
    "planning": {
        "evidence_class": "planned",
        "page_directory": "decisions",
        "next_phase": "implementation",
    },
}


def _validate_formal_path(stage: str, work_id: str, artifact_path: str) -> str:
    relative = normalized_path(artifact_path)
    root = f"docs/work/{work_id}"
    if stage == "requirements":
        pattern = rf"^{re.escape(root)}/requirements(?:-[2-9][0-9]*)?\.md$"
        if re.fullmatch(pattern, relative) is None:
            raise KnowledgeError(
                "FORMAL_PATH_INVALID",
                "requirements artifact is outside the current Work ID revision path",
                exit_code=2,
            )
    elif stage == "planning":
        pattern = rf"^{re.escape(root)}/plan(?:-[2-9][0-9]*)?/[^/]+\.(?:md|json)$"
        if re.fullmatch(pattern, relative) is None:
            raise KnowledgeError(
                "FORMAL_PATH_INVALID",
                "planning artifact is outside the current Work ID plan bundle",
                exit_code=2,
            )
    else:
        raise KnowledgeError("STAGE_INVALID", "stage has no formal co-promotion policy", exit_code=2)
    return relative


def _current_pages(repo: Path) -> list[dict[str, Any]]:
    eligible = _eligible_paths(repo, ("docs/knowledge/meta/pages",))
    root = repo / "docs" / "knowledge" / "meta" / "pages"
    pages: list[dict[str, Any]] = []
    if not root.is_dir():
        return pages
    for path in sorted(root.glob("*.json"), key=lambda item: item.as_posix().encode("utf-8")):
        relative = path.relative_to(repo).as_posix()
        if relative not in eligible:
            continue
        try:
            page = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise KnowledgeError(
                "PAGE_CONTRACT_INVALID",
                f"cannot construct stage Candidate from {relative}",
                exit_code=3,
            ) from exc
        if not isinstance(page, dict) or page.get("schema") != "knowledge-page/v1":
            raise KnowledgeError(
                "PAGE_CONTRACT_INVALID",
                f"cannot construct stage Candidate from {relative}",
                exit_code=3,
            )
        pages.append(page)
    return pages


def _operation(repo: Path, path: str, postimage: str, *, create_only: bool = False) -> dict[str, str]:
    target = repo / Path(*path.split("/"))
    exists = target.is_file()
    if create_only and exists:
        raise KnowledgeError(
            "FORMAL_ARTIFACT_EXISTS",
            f"formal Candidate target already exists: {path}",
            exit_code=3,
        )
    return {
        "kind": "update" if exists else "create",
        "path": path,
        "postimage": postimage,
    }


def _normalized_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise KnowledgeError(
            "DRAFT_CONTRACT_INVALID",
            f"{label} must be non-empty UTF-8 text",
            exit_code=2,
        )
    return value.replace("\r\n", "\n").replace("\r", "\n")


def _strict_json_object(text: str, label: str) -> dict[str, Any]:
    def no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate key {key!r}")
            result[key] = value
        return result

    try:
        value = json.loads(text, object_pairs_hook=no_duplicates)
    except (json.JSONDecodeError, ValueError) as exc:
        raise KnowledgeError(
            "READY_PLAN_INVALID",
            f"{label} is not strict UTF-8 JSON",
            exit_code=2,
        ) from exc
    if not isinstance(value, dict):
        raise KnowledgeError("READY_PLAN_INVALID", f"{label} is not an object", exit_code=2)
    return value


def _planning_bundle_operations(
    repo: Path,
    *,
    work_id: str,
    primary_path: str,
    primary_text: str,
    artifact_bundle: list[dict[str, str]] | None,
) -> list[dict[str, str]]:
    """Validate an entire owner-approved Ready-plan bundle before sealing it."""

    if not isinstance(artifact_bundle, list) or not artifact_bundle:
        raise KnowledgeError(
            "READY_PLAN_BUNDLE_INCOMPLETE",
            "planning requires the complete Ready-plan artifact bundle",
            exit_code=2,
        )
    postimages: dict[str, str] = {}
    casefolded: set[str] = set()
    for item in artifact_bundle:
        if not isinstance(item, dict) or set(item) != {"path", "postimage"}:
            raise KnowledgeError(
                "READY_PLAN_BUNDLE_INVALID",
                "planning bundle entries require exactly path and postimage",
                exit_code=2,
            )
        relative = _validate_formal_path("planning", work_id, str(item.get("path", "")))
        folded = relative.casefold()
        if relative in postimages or folded in casefolded:
            raise KnowledgeError(
                "READY_PLAN_BUNDLE_INVALID",
                "planning bundle paths must be unique under case-insensitive rules",
                exit_code=2,
            )
        postimages[relative] = _normalized_text(item.get("postimage"), relative)
        casefolded.add(folded)

    if postimages.get(primary_path) != primary_text:
        raise KnowledgeError(
            "READY_PLAN_BUNDLE_INVALID",
            "primary artifact bytes differ from the complete bundle entry",
            exit_code=2,
        )
    bundle_root = primary_path.rsplit("/", 1)[0]
    if any(path.rsplit("/", 1)[0] != bundle_root for path in postimages):
        raise KnowledgeError(
            "READY_PLAN_BUNDLE_INVALID",
            "all planning artifacts must share one revision bundle root",
            exit_code=2,
        )
    handoff_path = f"{bundle_root}/handoff.json"
    if handoff_path not in postimages:
        raise KnowledgeError(
            "READY_PLAN_BUNDLE_INCOMPLETE",
            "planning bundle must contain exactly one handoff.json",
            exit_code=2,
        )
    handoff = _strict_json_object(postimages[handoff_path], handoff_path)
    owner_errors = _ready_plan_contract_errors(handoff)
    if owner_errors:
        raise KnowledgeError(
            "READY_PLAN_INVALID",
            f"Ready-plan owner validation failed ({len(owner_errors)} issue(s)): {owner_errors[0]}",
            exit_code=2,
        )
    approval = handoff.get("approval")
    artifacts = handoff.get("artifacts")
    if (
        not isinstance(approval, dict)
        or approval.get("status") != "Ready"
        or not isinstance(approval.get("actor"), str)
        or not approval.get("actor")
        or not isinstance(approval.get("evidence"), str)
        or not approval.get("evidence")
        or not isinstance(artifacts, list)
    ):
        raise KnowledgeError(
            "READY_PLAN_NOT_READY",
            "planning bundle is not physically bound to a Ready approval",
            exit_code=3,
        )
    artifact_by_path = {
        item.get("path"): item
        for item in artifacts
        if isinstance(item, dict) and isinstance(item.get("path"), str)
    }
    if len(artifact_by_path) != len(artifacts) or set(artifact_by_path) != set(postimages):
        raise KnowledgeError(
            "READY_PLAN_BUNDLE_INCOMPLETE",
            "Ready-plan artifact manifest must exactly equal the sealed bundle paths",
            exit_code=2,
        )
    for relative, postimage in postimages.items():
        artifact = artifact_by_path[relative]
        if relative == handoff_path:
            valid = artifact.get("role") == "handoff" and artifact.get("sha256") is None
        else:
            valid = artifact.get("sha256") == sha256_bytes(postimage.encode("utf-8"))
        if not valid:
            raise KnowledgeError(
                "READY_PLAN_BUNDLE_DRIFT",
                f"Ready-plan manifest does not bind exact postimage bytes: {relative}",
                exit_code=3,
            )
    primary_artifact = artifact_by_path[primary_path]
    expected_primary = {
        "path": primary_path,
        "sha256": sha256_bytes(primary_text.encode("utf-8")),
    }
    if primary_artifact.get("role") != "primary" or handoff.get("primary_plan") != expected_primary:
        raise KnowledgeError(
            "READY_PLAN_BUNDLE_INVALID",
            "artifact_path must identify the bundle's owner-declared primary plan",
            exit_code=2,
        )
    return [
        _operation(repo, relative, postimages[relative], create_only=True)
        for relative in sorted(postimages, key=lambda value: value.encode("utf-8"))
    ]


def build_stage_candidate_draft(
    repo_value: str,
    *,
    stage: str,
    work_id: str,
    artifact_path: str,
    artifact_text: str,
    title: str,
    claim_text: str,
    knowledge_decision: str = "change",
    artifact_bundle: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Build full formal + Wiki postimages for a requirements or planning gate."""

    repo = Path(repo_value).resolve()
    if not repo.is_dir():
        raise KnowledgeError("REPOSITORY_MISSING", "repository root does not exist", exit_code=4)
    if stage not in STAGE_POLICY or WORK_ID_RE.fullmatch(work_id) is None:
        raise KnowledgeError("STAGE_INVALID", "stage or work_id is invalid", exit_code=2)
    if knowledge_decision not in {"change", "no-change"}:
        raise KnowledgeError("DRAFT_CONTRACT_INVALID", "knowledge_decision is invalid", exit_code=2)
    normalized_artifact = _normalized_text(artifact_text, "artifact_text")
    if knowledge_decision == "change" and not all(
        isinstance(value, str) and value.strip() for value in (title, claim_text)
    ):
        raise KnowledgeError("DRAFT_CONTRACT_INVALID", "change metadata must be non-empty", exit_code=2)
    formal_path = _validate_formal_path(stage, work_id, artifact_path)
    if stage == "planning":
        formal_operations = _planning_bundle_operations(
            repo,
            work_id=work_id,
            primary_path=formal_path,
            primary_text=normalized_artifact,
            artifact_bundle=artifact_bundle,
        )
    else:
        if artifact_bundle is not None:
            raise KnowledgeError(
                "DRAFT_CONTRACT_INVALID",
                "requirements accepts one formal artifact, not a planning bundle",
                exit_code=2,
            )
        formal_operations = [
            _operation(repo, formal_path, normalized_artifact, create_only=True),
        ]
    if knowledge_decision == "no-change":
        return {
            "schema": "knowledge-candidate-draft/v1",
            "stage": stage,
            "work_id": work_id,
            "decision": "no-change",
            "source_snapshot": [],
            "operations": formal_operations,
        }
    lines = normalized_artifact.splitlines()
    matching_lines = [index for index, line in enumerate(lines, 1) if line == claim_text]
    if len(matching_lines) != 1:
        raise KnowledgeError(
            "CLAIM_LOCATOR_INVALID",
            "claim_text must occur on exactly one complete artifact line",
            exit_code=2,
        )
    line_number = matching_lines[0]
    artifact_bytes = normalized_artifact.encode("utf-8")
    source_ref = {
        "path": formal_path,
        "sha256": sha256_bytes(artifact_bytes),
        "locator": {"start_line": line_number, "end_line": line_number},
        "excerpt_sha256": sha256_bytes(claim_text.encode("utf-8")),
    }
    suffix = f"{work_id}-{stage}"
    anchor = f"{stage}-claim"
    content_path = (
        f"docs/knowledge/{STAGE_POLICY[stage]['page_directory']}/{suffix}.md"
    )
    content = f"# {title}\n\n## {anchor}\n\n{claim_text}\n"
    content_bytes = content.encode("utf-8")
    sidecar_path = f"docs/knowledge/meta/pages/page-{suffix}.json"
    page = {
        "schema": "knowledge-page/v1",
        "page_id": f"page-{suffix}",
        "content_path": content_path,
        "content_sha256": sha256_bytes(content_bytes),
        "title": title,
        "aliases": [],
        "tags": [stage],
        "lifecycle": "current",
        "claims": [
            {
                "claim_id": f"claim-{suffix}",
                "evidence_class": STAGE_POLICY[stage]["evidence_class"],
                "lifecycle": "current",
                "content_anchor": anchor,
                "source_refs": [source_ref],
                "supersedes": [],
                "contradicts": [],
            }
        ],
        "backlinks": [],
    }
    sidecar_text = json.dumps(page, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    pages = [candidate for candidate in _current_pages(repo) if candidate.get("page_id") != page["page_id"]]
    pages.append(page)
    index_text = render_index(pages).decode("utf-8")
    return {
        "schema": "knowledge-candidate-draft/v1",
        "stage": stage,
        "work_id": work_id,
        "decision": "change",
        "source_snapshot": [],
        "operations": [
            *formal_operations,
            _operation(repo, content_path, content),
            _operation(repo, sidecar_path, sidecar_text),
            _operation(repo, "docs/knowledge/index.md", index_text),
        ],
    }


def validate_stage_promotion(
    repo_value: str,
    *,
    work_id: str,
    stage: str,
    receipt_path: str,
    receipt_sha256: str,
    approval_evidence: str,
) -> dict[str, Any]:
    """Validate the exact Ready receipt required before an SDLC phase advance."""

    repo = Path(repo_value).resolve()
    if stage not in STAGE_POLICY or WORK_ID_RE.fullmatch(work_id) is None:
        raise KnowledgeError("STAGE_INVALID", "stage or work_id is invalid", exit_code=2)
    relative = normalized_path(receipt_path)
    if re.fullmatch(r"docs/knowledge/meta/promotions/promotion-[a-z0-9-]+\.json", relative) is None:
        raise KnowledgeError("PROMOTION_REF_INVALID", "promotion receipt path is invalid", exit_code=2)
    eligible = _eligible_paths(repo)
    if relative not in eligible:
        raise KnowledgeError("PROMOTION_MISSING", "promotion receipt is not Git-eligible", exit_code=3)
    path = repo / Path(*relative.split("/"))
    if path.is_symlink() or not path.is_file():
        raise KnowledgeError("PROMOTION_MISSING", "promotion receipt is missing or redirected", exit_code=3)
    raw = path.read_bytes()
    if sha256_bytes(raw) != receipt_sha256:
        raise KnowledgeError("PROMOTION_DRIFT", "promotion receipt hash drifted", exit_code=3)
    try:
        promotion = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise KnowledgeError("PROMOTION_INVALID", "promotion receipt is not UTF-8 JSON", exit_code=2) from exc
    if (
        not isinstance(promotion, dict)
        or promotion.get("schema") != "knowledge-promotion/v1"
        or promotion.get("status") != "Ready"
        or promotion.get("stage") != stage
        or promotion.get("work_id") != work_id
        or promotion.get("approval", {}).get("evidence") != approval_evidence
        or promotion.get("lint", {}).get("required_outcome") != "passed"
    ):
        raise KnowledgeError(
            "MISSING_KNOWLEDGE_GATE",
            "Ready promotion does not match stage, Work ID, approval, and lint",
            exit_code=3,
        )
    raw_formal_paths = promotion.get("formal_paths")
    if not isinstance(raw_formal_paths, list) or not raw_formal_paths:
        raise KnowledgeError(
            "MISSING_KNOWLEDGE_GATE",
            "Ready promotion does not bind its formal artifact manifest",
            exit_code=3,
        )
    if any(not isinstance(value, str) for value in raw_formal_paths):
        raise KnowledgeError(
            "MISSING_KNOWLEDGE_GATE",
            "Ready promotion formal artifact manifest contains a non-string path",
            exit_code=3,
        )
    try:
        formal_paths = [normalized_path(value) for value in raw_formal_paths]
    except KnowledgeError as exc:
        raise KnowledgeError(
            "MISSING_KNOWLEDGE_GATE",
            "Ready promotion formal artifact manifest is invalid",
            exit_code=3,
        ) from exc
    canonical_formal_paths = sorted(
        set(formal_paths),
        key=lambda value: value.encode("utf-8"),
    )
    if formal_paths != canonical_formal_paths or not set(formal_paths) <= eligible:
        raise KnowledgeError(
            "MISSING_KNOWLEDGE_GATE",
            "Ready promotion formal artifacts are duplicated, reordered, missing, or ineligible",
            exit_code=3,
        )
    for formal_path in formal_paths:
        _validate_formal_path(stage, work_id, formal_path)
    if stage == "requirements":
        if len(formal_paths) != 1:
            raise KnowledgeError(
                "MISSING_KNOWLEDGE_GATE",
                "requirements promotion must bind exactly one current Work ID revision",
                exit_code=3,
            )
    else:
        handoff_paths = [path for path in formal_paths if path.endswith("/handoff.json")]
        if len(handoff_paths) != 1 or _trusted_ready_plan_paths(repo, handoff_paths[0]) != set(
            formal_paths
        ):
            raise KnowledgeError(
                "MISSING_KNOWLEDGE_GATE",
                "planning promotion is not bound to one complete owner-validated Ready-plan bundle",
                exit_code=3,
            )
    lint = lint_repository(str(repo))
    if lint.get("outcome") != "passed":
        raise KnowledgeError(
            "MISSING_KNOWLEDGE_GATE",
            "Ready promotion repository does not pass full knowledge lint",
            exit_code=3,
        )
    return {
        "schema": "knowledge-stage-gate/v1",
        "work_id": work_id,
        "stage": stage,
        "next_phase": STAGE_POLICY[stage]["next_phase"],
        "promotion_id": promotion["promotion_id"],
        "candidate_ref": promotion["candidate_ref"],
        "payload_sha256": promotion["payload_sha256"],
        "receipt_path": relative,
        "receipt_sha256": receipt_sha256,
        "approval_evidence": approval_evidence,
        "formal_paths": formal_paths,
        "status": "Ready",
    }
