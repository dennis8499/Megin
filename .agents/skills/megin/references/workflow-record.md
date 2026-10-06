# Repo-local workflow record

Every new Work ID belongs to exactly one Git repository. Store its status record, requirements, approved plan, and evidence beneath `<Repo>/docs/work/<Work ID>/`. Keep `workflow.md` as the status surface and append dated progress to its ledger. Preserve completed and historical records without rewriting them.

```markdown
# Megin workflow: <short title>

- schema: megin-repo-workflow/v1
- work_id: work-YYYYMMDD-<lowercase-slug>
- repository: .
- base_branch: <local base branch>
- base_commit: <full Git SHA>
- feature_branch: feature/<work-id>
- remote_name: <name or none>
- remote_url: <approved URL or none>
- route: read_only | small | large | bug
- phase: requirements | planning | approval | implementation | review | verification | acceptance | delivery
- status: active | awaiting_user | awaiting_review | blocked | needs_revision | complete
- plan_version: plan-1
- requirements_revision: req-1
- requirements_ref: docs/work/<work-id>/requirements.md
- quality_ref: docs/work/<work-id>/evidence/quality.json
- delivery_ref: docs/work/<work-id>/evidence/delivery.json
- last_updated: YYYY-MM-DD

## Progress ledger

- YYYY-MM-DD HH:MM | phase | action | result | next action
```

Use lowercase stable Work IDs; never reuse an old ID or approval. `repository` is `.` when the selected repository is the current checkout. `remote_name` and `remote_url` are both `none` when no remote was explicitly selected. When a remote is selected, freeze its exact name and URL with the approved base SHA in the plan and quality contract.

The approved plan is `plan-<version>/plan.md`; its machine-readable contract is `plan-<version>/quality-contract.json`. List every quality, review, acceptance, and delivery evidence file in the contract's `process_records` before the snapshot is captured. `quality_ref` and `delivery_ref` must point to those declared Repo-relative files under this Work ID's `evidence/` directory.

Requirements state the user-visible problem, source-backed current behavior, scope, exclusions, decisions, and scenarios. The plan binds those scenarios to implementation paths, exact commands and working directories, knowledge updates, review, verification, human acceptance, and local delivery. Record raw evidence rather than writer summaries alone.

The workflow phases are `requirements`, `planning`, `approval`, `implementation`, `review`, `verification`, `acceptance`, and `delivery`. A pending user decision uses `awaiting_user`; an independent reviewer handoff uses `awaiting_review`. Failures return to implementation or mark the work blocked with evidence. Do not set `complete` until the completion gate passes.
