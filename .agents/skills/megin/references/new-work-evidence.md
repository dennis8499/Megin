# New-work evidence (Repo v3 / Group v5; legacy v2/v4)

New native work uses `megin-repo-workflow/v3`,
`megin-repo-quality-contract/v3` and `megin-repo-quality-evidence/v3`.
Native Group work uses workflow, quality contract and evidence v5. Read
[workspace-workflow.md](workspace-workflow.md) for roots, architecture evidence,
mandatory remote master, common-dir locks and feature-only delivery.
Existing v1/v2 native and v1–v4 Group work retain
their original schema, installed fingerprint, snapshot and approval. Never
restart a Work ID to erase failed reviews or bypass an upgrade lock.

## Discovery and approval

Requirements first settles problem, audience, outcome and observable acceptance.
Then `phase: architecture` performs complete source reconciliation and produces
a hashed `architecture_ref` using `megin-architecture/v1`. Architecture binds the
requirements digest, discovery digest and each Repo's frozen source snapshot;
its components cite inventoried paths and it records flows, entrypoints,
dependencies, tests and impact. Both discovery and architecture cover every
valid Group Repo. Only the plan's implementation set gets branches. Missing or
stale architecture blocks new v3/v5 approval and writer claim.

Before product writes, run `functional_inventory.scan(root,
exclude_paths=quality_policy.SCAN_EXCLUSIONS)` using the bundled modules.
The exclusions are process records, locks and installed Skills. They are
visible scanner exclusions, not silently claimed as explored product code.
Store stdout/JSON under this Work ID's declared `evidence/` paths. A Group
discovery covers every real direct-child Git repository, including unaffected
Repos; its implementation contract can select a smaller approved set.

For v3/v5 selected Repos, frozen discovery must describe the pinned remote master
source, not a lagging local branch. Use the workspace baseline helper to fetch
objects and explore regular source in an external scratch directory without
changing product branches. Preserve source_commit and baseline_exclusions when
present. Claim/gates compare inventory bytes and entrypoints with that commit.
An unchanged Group Repo can retain current-source discovery. Missing quality
summaries with retained review attempts block writes instead of resetting history.

`megin-discovery/v1` contains `work_id`, `requirements_revision`, nonempty
`problem`, `audience`, `outcome`, `acceptance`; separate arrays `facts`,
`assumptions`, `requirements`, `technical_suggestions`, `decisions`, `blockers`;
and `repositories`. Facts cite current source paths/lines. Requirements have
unique `REQ-*` IDs and observable text. Assumptions and decisions have explicit
`status` (`confirmed` or `nonblocking`) and `reason`. Keep unresolved blocking
questions in `blockers`; they prevent approval and implementation.

Each repository row contains `repo_path` (`.` native), a hashed `scan_ref` and
a `functional_report` following `codebase-functional-exploration/v1`:

- `snapshot_id` matches the frozen scan;
- `functions`: unique `FUNC-*` IDs, `outcome`, `flow`, `dependencies`, `paths`;
- `coverage`: every included file exactly once, its `path`, `sha256`, `status`,
  `reason`, `function_ids`;
- `entrypoints`: every candidate exactly once with `entrypoint_id`, `status`,
  `reason`, `function_ids`;
- `gaps`: explicit unresolved limits. Partial/unread sources prevent a complete
  discovery claim. Nonblocking gaps are retained as objects with `status: nonblocking`
  and a concrete `reason`; unrelated runtime unknowns must not force an invented
  requirement or unrelated repair. Record binary, secret, dependency and other exclusions.

Keep all applicable native/Group contract fields. Require `requirements_revision`,
`requirements_ref`, raw `requirements_sha256`, hashed `discovery_ref`, matching
`discovery_sha256`, `approval_ref`, `max_corrections: 3`, and `review_records`.
The latter is exactly four predeclared paths
`docs/work/<WorkID>/evidence/review-attempt-0.json` through `-3.json`.
All nested evidence references and future outputs must be in `process_records`
before approval. Never broaden that list after approval without a new plan.

`scenario_ids` and `behavior_trace` are mandatory. Every requirement maps to at
least one scenario. Each trace row has `scenario_id`, `requirement_ids`, `given`,
`when`, `then`, `observable`, `assertion`, `check_id`, `implementation_paths`.
Checks freeze exact command and cwd; tests must assert observable results.

Save the actual user approval in a `megin-plan-approval/v1` JSON at
`approval_ref`: `actor_kind: human`, `verdict: APPROVED`, `work_id`,
`plan_version`, `requirements_revision`, literal `response`, raw `plan_sha256`
and `contract_sha256` from `quality_policy.canonical_digest(contract)`, plus
hashed raw `source`. This digest does not include approval bytes, avoiding a
circular hash. Its raw transcript has claim locators for:
`- work_id: ...`, `- plan_version: ...`, `- verdict: APPROVED`,
`- response: <JSON-encoded literal response>`, `- plan_sha256: ...`, and
`- contract_sha256: ...`. Never invent a user response or approve for the user.
Claim validates live discovery before the first write; subsequent lock checks
validate immutable approved records while implementation changes source.

## TDD and review

Quality evidence includes `requirements_revision`, `tdd_cycles` and
`review_history` in addition to writer, checks, review and human acceptance.
Each cycle binds one `scenario_id`, `check_id`, exact `assertion`, `red` and
`green`. Each run records sequence (red < green), command, cwd, exit_code,
executed/failed/skipped counts, `test_path`, unchanged `test_sha256`, and hashed
raw `output` with claim locators. Raw claim lines are `Command: ...`,
`Working directory: ...`, `Exit code: ...`, `Tests: N executed, N failed, N skipped`,
`Test SHA-256: ...`, `Sequence: ...`; red also locates the actual assertion
failure text. `failure_kind: assertion`, a nonzero exit and at least one failed
executed test are required for red. Import/setup/environment failure, zero
tests and skipped tests do not count. Green must pass with nonzero tests and
no skips. Preserve original stdout/stderr alongside this execution metadata.

Invoke a new independent read-only reviewer for **each** round. Give it the
approved records, raw evidence and changed source, not the writer's desired
verdict. The reviewer must not have authored the implementation. If the host
cannot provide a separate context, use `awaiting_review` and stop progression.

Each immutable `megin-review-attempt/v1` file records `work_id`,
`requirements_revision`, `round` (0–3), `previous_sha256` (null for round 0),
unique `context` and matching real `invocation_id`,
`reviewer_kind: independent_readonly`, `snapshot`, `verdict` (`APPROVED` or
`CHANGES_REQUESTED`), hashed raw `source`, and `correction_ref` after round 0.
Raw claim locators bind context, verdict, snapshot, round and previous_sha256
using `- key: value` lines. Corrections explain findings, fixes and rerun tests.
`review_history` lists hashed attempt references in order. The compatibility
`review` object equals the last attempt's context/verdict/snapshot/source.
Use `review_history.py --root ROOT --work-id ID --attempt INPUT.json` to append
with exclusive creation, then save returned JSON at quality_ref. Recover a
partial save from the retained attempt files with the same command and `--recover`; do not recreate round 0.

Initial review is round 0. Failures allow three correction/re-review attempts.
Any approval proceeds to verification and human
acceptance. Failed round 3 leaves work incomplete/blocked with evidence; do
not claim delivery or silently reset the counter. Changes after approval invalidate downstream evidence and need a fresh review
at the next round, preserving prior history and the same total correction cap.
Changed requirements also require renewed plan approval. Never edit old review records. Human acceptance binds the final Work ID and product snapshot.

Delivery exports all discovery, approval, scan, raw TDD and review history
references. SHA-256 and locators prove consistency only: the independent
reviewer still judges semantic coverage, effective assertions and authenticity.
