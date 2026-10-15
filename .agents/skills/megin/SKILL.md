---
name: megin
description: Start or resume Megin's governed Repo/Group development lifecycle through requirements, architecture, approved BDD/TDD, independent review, human acceptance and local feature commits. Use when the user requests that lifecycle or continues a matching unfinished Megin Work ID.
---

# Megin

Run the requested Megin development lifecycle, or resume a matching unfinished Work ID.
Install all thirteen Skills together. Read [repository-workflow.md](references/repository-workflow.md)
for root selection, resumption and stage-specific references, then
[language-policy.md](references/language-policy.md) before human-readable output.

## Select and resume

Use `unified_workflow.py detect`, or exactly one of `--repo <Git root>` and
`--group-root <non-Git root>`. Repo stays in its root; Group inventories every real
direct-child Git root, excluding links, junctions and nested Repos. Records live at
`<selected root>/docs/work/<Work ID>/`; only approved change Repos get branches.

Resume the earliest incomplete action, retaining approvals, locks, evidence and review
attempts. Completed or unrelated records authorize no new work. Active legacy work keeps
its original package and fingerprint; use the compatibility rules in the shared reference.

## Lifecycle and completion criteria

1. **Requirements — `$megin-requirements-discovery`:** Settle problem, audience, outcome,
   constraints and observable acceptance; resolve blocking product decisions.
2. **Architecture — `$megin-architecture-exploration`:** Reconcile every included file and
   entrypoint with frozen source, flows, dependencies and impact for every discovered Repo.
3. **Planning — `$megin-technical-planning` + `$megin-behavior-contract`:** Bind exact
   requirements/architecture, REQ → SCN → assertions, paths, checks/cwd, Skills fingerprint,
   dependencies and feature-only delivery. Pin each change Repo's live `refs/heads/master`;
   `main`, local HEAD and tracking refs cannot substitute.
4. **Approval:** Present Work ID/version, scope, scenarios, checks, remote identity, base SHAs
   and delivery. Save the human's literal approval bound to exact plan/contract digests.
5. **Implementation — `$megin-implementation-execution` + `$megin-test-driven-development`:**
   `claim`, then `prepare` once; run `check` before every product write with the same root,
   Work ID and writer. Preserve dirty work; resume existing `feature/<Work ID>` branches.
6. **Review — `$megin-code-review`:** Give a fresh independent read-only reviewer approved
   records, frozen source and raw evidence without a desired verdict. Round 0 plus at most
   three correction/re-review attempts each need a new reviewer; approval ends corrections.
   Failed round 3 remains incomplete. Without an independent context, set `awaiting_review`.
7. **Verification — `$megin-verification-before-completion`:** Run every approved check on
   the current snapshot with raw output, exit codes and nonzero test counts. Changed source,
   tests, plan or Skills invalidate downstream evidence; repairs consume the same review cap.
8. **Acceptance — `$megin-human-acceptance`:** Present exact Work ID/version/snapshot,
   operations and expected results; save the human's literal acceptance or rejection.
9. **Delivery — `$megin-finishing-delivery`:** After acceptance, recheck all remote master
   SHAs, stage accepted paths, save the delivery gate and create one feature commit per Repo
   in dependency order. Verify accepted committed trees, save completion, then release locks.

`$megin-bug-diagnosis` provides read-only diagnosis before repair enters this lifecycle.
`$megin-project-knowledge` maintains source-backed documentation within approved paths.
For ambiguous stage selection or interrupted work, read [workflow-examples.md](references/workflow-examples.md).

## Gates and stops

`quality_gate.py snapshot|validate-record|check --gate review|acceptance|delivery|completion`
is read-only; use exactly one root flag. Gates prove consistency, while real independent
reviewers and humans supply review and acceptance decisions.

Missing approval/architecture, unknown required behavior, drift, wrong branches, scope
violations, stale/failed checks, exhausted corrections or another writer's lock stop progression.
Common-dir Repo locks cover linked worktrees; Group also holds its root lock. Partial delivery
retains accepted commits and locks for resume. Stage/commit only after human acceptance;
leave each Repo on its feature branch. Push, merge, MR creation, deployment and branch deletion
are separate user-directed work; GitLab integrations remain in GitlabWorkSpace.
