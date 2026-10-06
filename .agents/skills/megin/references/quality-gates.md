# Single-Repo quality evidence and gates

New work uses `megin-repo-quality-contract/v1` and `megin-repo-quality-evidence/v1`. The approved contract is the only source for behavior, paths, commands, selected base, and delivery obligations. `workflow.md` is the status surface. The structural helper is read-only and does not prove test relevance, reviewer independence, or the correctness of a human decision.

## Contract

The JSON contract records:

- `schema`, `work_id`, and `plan_version`;
- `base_branch`, full `base_commit`, and `feature_branch`;
- optional `remote_name` and `remote_url`, present together only when a remote was explicitly selected;
- `allowed_paths`, the approved check list, and exact `process_records`;
- `quality_ref`, `delivery_ref`, and the approved `skills_sha256`.

Each check has a unique `id`, `kind` (`test` or `command`), exact command, and exact Repo-relative `cwd`. Every source and raw output cited by evidence must be a declared process record under this Work ID's `evidence/` directory. Plans, tests, fixtures, and project docs stay in the product snapshot unless their exact path is declared as a process record.

## Snapshot and check commands

Run commands from the approved Repo root:

```text
python .agents/skills/megin/scripts/quality_gate.py snapshot --repo <Repo> --work-id <Work ID>
python .agents/skills/megin/scripts/quality_gate.py check --repo <Repo> --work-id <Work ID> --gate review
python .agents/skills/megin/scripts/quality_gate.py check --repo <Repo> --work-id <Work ID> --gate acceptance
python .agents/skills/megin/scripts/quality_gate.py check --repo <Repo> --work-id <Work ID> --gate delivery
python .agents/skills/megin/scripts/quality_gate.py check --repo <Repo> --work-id <Work ID> --gate completion
```

The snapshot hashes tracked and non-ignored untracked product files while excluding only `workflow.md` and the exact declared process records. Review, verification, and acceptance bind the same product SHA-256. A product, approved-plan, or Skills change invalidates downstream evidence.

Evidence records the current snapshot, distinct writer and reviewer contexts, supporting sources, each approved command's exact command/working-directory/output/exit-code claims, and test counts. Review also binds `APPROVED` to the same snapshot. Acceptance binds the Work ID, acceptance version, user's `ACCEPTED` response, and that snapshot. Do not claim passed evidence without raw output and valid line locators.

## Gate behavior

- `review`: require the selected feature branch, unchanged local base, approved changed paths, current writer and check evidence, and a clean unstaged product index. Review can record failures, but does not stage product paths.
- `acceptance`: additionally require every approved check to pass, meaningful nonzero test counts with no failures or skips, and an independent `APPROVED` review for the current snapshot. Product paths remain unstaged.
- `delivery`: require the accepted snapshot and human acceptance, no unstaged or untracked product paths, and staged bytes equal to the accepted snapshot. If the contract names a remote, also verify its URL and query the exact base ref with `git ls-remote --exit-code`; the reported SHA must still equal the approved `base_commit`. With no selected remote, delivery is entirely local.
- `completion`: validate the predeclared delivery record and passing delivery-gate receipt, accepted snapshot, feature commit tree and parent, `--no-ff` merge's two exact parents and tree, local base pointer, and optional remote base. Any mismatch leaves the workflow incomplete.

Completion receipt format:

```json
{
  "schema": "megin-repo-delivery-result/v1",
  "work_id": "work-YYYYMMDD-example",
  "plan_version": "plan-1",
  "accepted_snapshot": "<product SHA-256>",
  "delivery_gate": {
    "stdout": "<exact JSON stdout>",
    "exit_code": 0,
    "sha256": "<SHA-256 of UTF-8 stdout>"
  },
  "feature_commit": "<full Git SHA>",
  "merge_commit": "<full Git SHA>"
}
```

The receipt file itself is a declared process record, so it can be updated after acceptance without changing the accepted product snapshot. Run the completion gate after saving it, set `status: complete` only on a passing result, then release the lock through `repo_workspace.py`.

The helper retains compatibility with the Megin source repository's legacy `megin-quality-contract/v1` and `megin-quality-evidence/v1` maintainer fixtures. That compatibility does not change the public single-Repo workflow contract.
