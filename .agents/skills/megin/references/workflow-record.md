# Megin workflow record

Use one directory per work item: `docs/work/<work-id>/`. The required control record is
`workflow.md`; requirements, plan, behavior features, implementation evidence, review, verification,
acceptance, and knowledge notes live beside it. This is a human-readable record, not a hidden runtime
database and not a compatibility layer for historical delivery-run records.

## Required header

```markdown
# Megin workflow: <short title>

- schema: megin-skills-workflow/v1
- work_id: work-YYYYMMDD-<lowercase-slug>
- repository: <repository root>
- base_commit: <full SHA>
- branch: <current branch or `pending-approval`>
- route: read_only | small | large | bug
- phase: requirements | planning | approval | implementation | review | verification | acceptance | delivery
- status: active | awaiting_user | awaiting_review | blocked | complete
- plan_version: <version or pending>
- last_updated: YYYY-MM-DD
```

Use a stable lowercase Work ID. Do not reuse an old Work ID or an old approval. Keep the base
commit and branch visible so a later resume can detect drift.

## Sections

Keep these sections in every record and update them in place while appending dated events:

```markdown
## Intent and boundaries
Goal, audience, in-scope behavior and paths, out-of-scope behavior, assumptions, and risks.

## Acceptance
Stable scenario IDs, observable expected results, automatic commands, and user-visible manual steps.

## Plan and approval
Plan version, allowed paths, interfaces, dependencies, test commands, knowledge scope,
delivery destination, approval wording, approving response, and approval date.

## Task ledger
| Task | Dependency | Owner | Status | Evidence |
| --- | --- | --- | --- | --- |

## Evidence
Paths to raw command output, review reports, snapshots, feature files, and source references.
Record command, exit status, timestamp, and a digest when the project contract requires it.

## Blockers and next action
One concrete blocker with evidence, or the earliest next action and its owner.

## Delivery
Acceptance version, knowledge result, staged paths, commit identity, and final status.

## Event log
Append `YYYY-MM-DD HH:MM — phase — action — result — next action` entries. Never rewrite an
old approval or verdict; supersede it with a new plan/review version and explain why.
```

## State transitions

`requirements → planning → approval → implementation → review → verification → acceptance → delivery`

`read_only` and `bug` diagnosis may finish without entering implementation. A failed review or
verification returns to the affected implementation task and requires a fresh review and fresh
verification. A changed scope or acceptance criterion creates a new plan version and approval.
Knowledge promotion happens only after acceptance and only for the approved source-backed scope.
