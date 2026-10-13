---
name: megin
description: Run an approved development workflow in one Git repository or a local Group, from requirements and architecture exploration through BDD/TDD, independent review, human acceptance and remote-master feature delivery.
---

# Megin

Install all thirteen Skills together. Read [repository-workflow.md](references/repository-workflow.md), [workspace-workflow.md](references/workspace-workflow.md) and [language-policy.md](references/language-policy.md).

## Select and resume

Use `unified_workflow.py detect`, or exactly one of `--repo <Git root>` and `--group-root <non-Git root>`. Repo mode stays in its root. Group mode inventories every real direct-child Git root, excluding links/junctions/nested Repos. Only approved change Repos get branches. Records live in `<selected root>/docs/work/<Work ID>/`.

Resume a matching unfinished Work ID at its earliest incomplete action, preserving approval, locks and review history. Completed/unrelated records cannot authorize new work. Legacy Repo v1/v2 and Group v1–v4 work stays on its original package until complete. Do not upgrade active work or reset attempts.

## Governed workflow

1. **Requirements**: use `$megin-requirements-discovery` to clarify problem, audience, outcome, constraints and observable acceptance; resolve blocking product questions.
2. **Architecture**: use `$megin-architecture-exploration` to trace components, entrypoints, flows, dependencies, tests and impact. Freeze complete discovery and architecture for every discovered Repo.
3. **Planning**: use `$megin-technical-planning` and `$megin-behavior-contract` to bind exact requirements/architecture, BDD assertions, paths, commands/cwd, Skills fingerprint, dependency order and feature-only delivery. Pin each change Repo's live `refs/heads/master` SHA. Local HEAD, tracking refs, main and absent remotes cannot substitute.
4. **Approval**: present exact Work ID/plan version, scope, scenarios, checks, remote identity, base SHAs and delivery. Wait for explicit human approval; preserve the literal response and exact-plan digests.
5. **Implementation**: claim with `unified_workflow.py claim`, then `prepare` once to fetch/recheck master and create each `feature/<Work ID>`. Before every product write run `check` with the same root, Work ID and writer. Follow `$megin-implementation-execution` and `$megin-test-driven-development`. Preserve existing dirty work; resume existing branches without recreating them.
6. **Review**: use `$megin-code-review` in a fresh independent read-only context for every attempt. Give approved records, frozen source and raw evidence without a desired verdict. Initial review is round 0; allow at most three correction/re-review attempts (rounds 1–3), each with a new reviewer. Stop early on approval. Failed round 3 remains incomplete with evidence and locks. Resume never resets attempts. Without an independent context use `awaiting_review` and stop progression; never self-approve.
7. **Verification**: use `$megin-verification-before-completion` to execute all approved checks with raw output, exit codes and nonzero test counts. Changed source/tests/plan/Skills invalidate downstream evidence. Repairs need another independent review within the same cap.
8. **Acceptance**: use `$megin-human-acceptance` to show Work ID, version, snapshot, operations and expected results. Wait for the human's literal acceptance/rejection. Do not stage or commit before acceptance.
9. **Delivery**: use `$megin-finishing-delivery`. Recheck all remote master SHAs, stage accepted paths, save the delivery gate and create one accepted feature commit per Repo in dependency order. Verify committed trees, save completion, then release locks. Leave each Repo on its feature branch for the user's merge decision.

`$megin-bug-diagnosis` supports read-only diagnosis before the same lifecycle. `$megin-project-knowledge` maintains source-backed documentation within approved paths.

## Evidence and stop conditions

Read-only `quality_gate.py` supports `snapshot`, `validate-record`, and `check --gate review|acceptance|delivery|completion` with mutually exclusive `--repo` / `--group-root`. Read [new-work-evidence.md](references/new-work-evidence.md) for REQ → SCN → assertion → code → checks → review → human acceptance, raw red/green, exact-plan approval and append-only review history. Gates establish consistency; the host supplies real reviewers and human decisions.

Stop on missing approval/architecture, unknown behavior, fingerprint/remote drift, wrong branches, scope violations, stale evidence, failed checks, exhausted corrections or another writer's lock. Repo common-dir locks protect both modes and linked worktrees; Group also holds its root lock. Partial delivery preserves accepted commits for resume. Do not push, merge, deploy or delete branches during feature delivery. GitLab Issue/MR integrations remain in GitlabWorkSpace.
