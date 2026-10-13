---
name: megin-implementation-execution
description: Execute an approved Megin Repo or Group plan on remote-master feature branches with one writer, TDD evidence and a fresh review handoff. Use for approved implementation and coding; require exact-plan approval.
---

# megin-implementation-execution

For Group follow [group-impact.md](../megin/references/group-impact.md): retain frozen architecture, save separate actual-diff impact confirmation and replay contract searches against implemented bytes and pinned peers before review. Newly affected consumers or uncovered interfaces require renewed planning/approval. Verification-only Repos supply fixed inputs/checks and receive no product changes or branches.

Read [repository-workflow.md](../megin/references/repository-workflow.md), [workspace-workflow.md](../megin/references/workspace-workflow.md), [new-work-evidence.md](../megin/references/new-work-evidence.md) and [language-policy.md](../megin/references/language-policy.md).

Read the approved plan. Set `implementation / active`. Run `unified_workflow.py claim`, then `prepare` once with selected root, Work ID and writer. Preparation preflights every target, fetches/rechecks remote master and creates each feature branch. Preserve existing dirty work. On resume retain branches, locks and evidence; verify instead of recreating.

Before every product write run `unified_workflow.py check` with the same identity. Follow approved paths/dependency order and `$megin-test-driven-development`. Preserve raw command/cwd/output/count evidence. Scope, baseline or Skills changes require replanning.

Run the read-only review gate and hand the frozen combined snapshot, approved records and raw evidence to a fresh independent reviewer. Repairs follow TDD/lock checks. Preserve append-only attempts and the three-correction cap. Stage and commit only during accepted delivery.
