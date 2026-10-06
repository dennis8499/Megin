---
name: megin-implementation-execution
description: Execute an approved Megin work package in the bound checkout with one writer, bounded TDD evidence, and a fresh review handoff. Use for approved implementation, coding, 實作、開發、套用已核准計畫; do not start without an exact plan approval.
---


# Megin implementation execution

Read [../megin/references/repository-workflow.md](../megin/references/repository-workflow.md), [../megin/references/quality-gates.md](../megin/references/quality-gates.md), and the approved plan. Accept work only after explicit approval of its exact version, scope, scenarios, commands, base commit, and delivery steps.

Before the first product write, claim the selected Repo with `repo_workspace.py claim --repo <Repo> --work-id <Work ID> --writer <identity>`. Before every product write, run the matching `check`. Verify the approved feature branch, allowed paths, and Skills fingerprint. Keep one writer, preserve unrelated dirty changes, and do not write outside the selected Repo.

Use the TDD Skill for each behavior. Record focused checks and raw output. Keep changes within approved paths; a scope, base, or Skills change requires replanning. When implementation is complete, run the read-only `review` gate with `--repo <Repo> --work-id <Work ID>` and hand the exact snapshot to a fresh reviewer. Do not stage, commit, merge, or claim completion before verification and user acceptance.
