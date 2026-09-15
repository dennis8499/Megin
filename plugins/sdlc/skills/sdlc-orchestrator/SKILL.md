---
name: sdlc-orchestrator
description: Route repository work through the smallest appropriate SDLC path, bind approval to an immutable scope, coordinate one authorized writer and a fresh read-only reviewer, and resume safely.
---

# SDLC Orchestrator

Use this skill as the entry point whenever a request may change a repository. It owns classification, approval, work identity, phase routing, resume state, and the handoff to the other SDLC skills.

## 1. Explore before mutating

Inspect the repository, current branch, local instructions, existing work records, and available validation tools with read-only commands. Resolve the repository explicitly; do not assume that the target project contains this plugin or a fixed `.agents/skills` path. When the repository provides a validator or CLI, use it as the source of truth.

Do not create a delivery worktree, branch, record, or product diff until the applicable approval gate has passed. Read-only exploration, diagnosis, and review do not create a delivery run.

## 2. Classify the request

Choose exactly one route and record the reason:

- **Read-only**: explanation, evaluation, diagnosis, or review. Gather evidence and report findings without product mutation.
- **Small task**: one clear result in an existing flow, with known acceptance and no cross-module contract, data migration, permission, dependency, or architectural change.
- **Large change**: a new subsystem, architecture or contract change, migration, permission/dependency change, material uncertainty, or anything that cannot be proven small.
- **Bug**: a suspected defect. Diagnose the symptom first; only a `confirmed` or `likely` diagnosis may enter repair, then classify the repair by its impact.
- **Tiny formatting/text edit**: retain the repository's direct handling exception when it is genuinely limited to formatting or wording and has no behavior change.

Classification is based on impact and uncertainty, not line count. If a small task reveals a larger boundary, preserve its evidence, stop the current route, and re-enter the large-change requirements and planning gates for the expanded scope.

## 3. Bind approval to the work

Create a short, reviewable candidate before mutation. It must state the goal, in-scope and out-of-scope files or interfaces, acceptance criteria, implementation steps, test commands, knowledge-update scope, publication target, and the repository/work identity.

- A small task has **one integrated approval** for its design, acceptance, implementation, verification, knowledge review, and the stated Git publication target.
- A large change has **two approvals**: requirements first, then the technical plan. The second gate authorizes implementation of the exact approved plan.
- A bug repair keeps the diagnosis as evidence; requirements still own what to change and the plan owns how to change it.

Approval is valid only for the exact candidate revision and work identity. A changed acceptance criterion, expanded file set, new publication destination, or changed knowledge claim requires a new approval. Never treat a prompt, skill name, or child-agent report as write authorization.

## 4. Coordinate implementation and review

After approval, create or resume an isolated worktree and branch. Keep product files, work records, and evidence tied to the same work identity. Route implementation to the authorized writer and apply `test-driven-development` to each behavior; use repository-specific implementation tooling when it exists.

At most **one authorized writer** may change the worktree at a time. The controller coordinates dependencies and state; the writer edits product and explicitly allowed test files. A writer must not delegate again. If subagents are unavailable, execute sequentially while keeping the same authorization and review boundaries.

For every implementation unit, dispatch a handoff containing the approved acceptance, allowed paths, required interfaces, test commands, dependencies, and report location. Require a fresh read-only `code-review` after the writer reports completion. A reviewer cannot edit, commit, or approve its own changes. If an independent reviewer is unavailable, stop at awaiting review.

## 5. Review knowledge and resume

Treat knowledge changes as deliverables. The reviewer must check that each proposed claim is supported by the approved result, retains source references and content digests, and does not silently overwrite a conflicting canonical claim. Once the independent review passes, automatically promote an authorized knowledge update when the repository contract supports promotion; otherwise preserve a reviewed candidate and its pending action. Product correctness findings block completion; a knowledge-only dispute may leave the product complete with an explicit pending item, according to the repository contract.

Persist phase, approval identity, writer/reviewer reports, command evidence, current snapshot hashes, and the next action. On resume, validate the exact work identity and continue at the earliest incomplete action. Do not repeat completed work or bypass a failed gate. Scope drift, stale evidence, missing context, or repeated no-progress attempts require a blocker or a return to planning.

## 6. Report progress and route completion

Keep updates compact and consistent:

```text
work: <id> / generation: <n>
route: <read-only | small | large | bug>
phase: <requirements | planning | implementation | review | verification | delivery>
approval: <required | approved | stale>
done: <completed units>
current: <active unit or blocker>
next: <one concrete action or decision>
```

Before declaring completion, invoke `verification-before-completion`. After a passing review and verification, invoke `finishing-delivery`. The normal delivery target is commit, push, and a draft pull request when the approved destination and tools permit it. Merge, deployment, and worktree cleanup are outside this skill and require separate authorization.
