"""Export immutable single-Repo local delivery evidence without checking live tips."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

sys.dont_write_bytecode = True

import quality_gate as q
from repo_workspace import validate_repo, InvalidWorkspace
from verification_inputs import canonical_digest, no_links


def export_receipt(repo: Path, work_id: str) -> dict:
    repo = validate_repo(repo)
    if q._unified_repo(repo, work_id):
        from unified_workflow import export_receipt as unified_export
        return unified_export(repo, work_id)
    if not q.WORK_ID_PATTERN.fullmatch(work_id):
        raise q.InvalidEvidence("invalid Work ID")
    result = q.check_completion(repo, work_id, historical=True)
    if not result["ok"]:
        raise q.InvalidEvidence("; ".join(result["reasons"]))
    fields, contract, records = q.load_contract(repo, work_id)
    prefix = f"docs/work/{work_id}/"
    record_paths = {e["path"] for e in q.tree_entries(repo, result["feature_commit"], records, work_id)
                    if e["path"].startswith(prefix)}
    evidence = q.read_json(q.evidence_file(repo, work_id, fields["quality_ref"]))
    record_paths.update((fields["quality_ref"], fields["delivery_ref"]))
    for value in [evidence.get("writer", {}), evidence.get("review", {}), evidence.get("acceptance", {})]:
        record_paths.add(value["source"]["path"])
    for value in evidence.get("sources", []):
        record_paths.add(value["path"])
    for check in evidence["checks"]:
        record_paths.add(check["output"]["path"])
    from quality_policy import NEW_CONTRACTS, evidence_paths, read_json
    if contract.get("schema") in NEW_CONTRACTS:
        record_paths.update((evidence_paths(contract) | evidence_paths(evidence)) & records)
        record_paths.add(contract["approval_ref"])
        # Include references inside discovery, approval and every review attempt.
        for relative in list(record_paths):
            if relative.endswith(".json") and relative in records:
                record_paths.update(evidence_paths(read_json(repo / relative)) & records)
    file_digests = []
    for relative in sorted(record_paths):
        path = repo / q.canonical_relative(relative)
        no_links(path)
        if not relative.startswith(prefix):
            raise q.InvalidEvidence("receipt record is outside this Work ID")
        file_digests.append({"path": relative, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    value = {
        "schema": "megin-repo-delivery-receipt/v1", "work_id": work_id,
        "plan_version": fields["plan_version"], "repo_root": str(repo),
        "local_delivery_complete": True, "accepted_snapshot": result["snapshot"],
        "base_commit": contract["base_commit"], "feature_commit": result["feature_commit"],
        "merge_commit": result["merge_commit"],
        "tree_sha": q.line(repo, "rev-parse", result["feature_commit"] + "^{tree}"),
        "contract_ref": prefix + fields["plan_version"] + "/quality-contract.json",
        "quality_ref": fields["quality_ref"], "delivery_ref": fields["delivery_ref"],
        "record_files": file_digests,
    }
    if contract.get("verification_inputs") is not None:
        value["verification_inputs"] = q.fixed_inputs(repo, contract)
    value["receipt_sha256"] = canonical_digest(value)
    return value


def write_receipt(repo: Path, work_id: str, output: Path, receipt: dict) -> None:
    repo = validate_repo(repo)
    _, _, records = q.load_contract(repo, work_id)
    expected = f"docs/work/{work_id}/evidence/receipt.json"
    output = Path(output).absolute()
    if output != repo / expected or expected not in records:
        raise q.InvalidEvidence("receipt output must be the dedicated predeclared evidence/receipt.json")
    no_links(output)
    raw = (json.dumps(receipt, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if output.exists():
        if output.read_bytes() != raw:
            raise q.InvalidEvidence("refusing to overwrite a different existing receipt")
        return
    with tempfile.NamedTemporaryFile(dir=output.parent, prefix=".receipt.", delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        os.link(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--repo", type=Path)
    selection.add_argument("--group-root", type=Path)
    parser.add_argument("--work-id", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        if args.group_root:
            from unified_workflow import export_receipt as unified_export
            receipt = unified_export(args.group_root, args.work_id, group=True)
        else:
            receipt = export_receipt(args.repo, args.work_id)
        if args.output:
            if args.group_root:
                from unified_workflow import load_contract
                root = args.group_root.resolve()
                _, _, _, records = load_contract(root, args.work_id, group=True)
                expected = f'docs/work/{args.work_id}/evidence/receipt.json'
                if expected not in records or args.output.absolute() != root / expected:
                    raise q.InvalidEvidence('receipt output must be the dedicated predeclared evidence/receipt.json')
                no_links(args.output)
                if args.output.exists():
                    if q.read_json(args.output) != receipt:
                        raise q.InvalidEvidence('refusing to overwrite a different existing receipt')
                else:
                    from unified_workflow import save_json
                    save_json(args.output, receipt)
            else:
                write_receipt(args.repo, args.work_id, args.output, receipt)
        else:
            print(json.dumps(receipt, ensure_ascii=False, indent=2))
        return 0
    except (q.InvalidEvidence, InvalidWorkspace, OSError, ValueError, KeyError, TypeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
