---
name: megin-technical-planning
description: Turn a clarified Megin request into an implementation-ready plan. Use for technical design, task breakdown, interfaces, tests, migration or delivery planning, 技術規劃、拆解任務、實作計畫; do not mutate product files before approval.
---

# Megin technical planning

Read [../megin/references/language-policy.md](../megin/references/language-policy.md),
[../megin/references/branch-policy.md](../megin/references/branch-policy.md), and
[../megin/references/requirements-discovery-protocol.md](../megin/references/requirements-discovery-protocol.md)
before creating or updating a plan. Work read-only after `megin-requirements-discovery` has produced a current
requirements revision. Re-read `requirements.md`, its sources, capability coverage, decisions, blockers, and acceptance
against the protocol's completion conditions. If any major unknown could change the goal, audience, boundary, interface,
important risk, core behavior, or acceptance, return to requirements discovery and keep `phase: requirements` with
`status: awaiting_user`; do not write or present a plan. Never treat a `ready_for_planning` flag, question count, or
document existence as proof of completion.
Read the target code, tests, project knowledge, and available validation commands. Keep the smallest
safe design; classify the work as small or large by impact and uncertainty rather than line count.
Read [../megin/references/quality-gates.md](../megin/references/quality-gates.md) for the shared
obligation and snapshot contract. Map each observable result to a meaningful assertion, exact
command, and required environment; split independently failing promises. Include failure paths
only when the change makes them relevant. The plan remains the sole source of approved obligations.

Write `plan.md` beside the Work ID record. It must bind the requirements revision to interfaces,
dependency-ordered work packages, exact allowed paths, forbidden paths, acceptance scenarios,
focused/related/full test commands, evidence locations, knowledge-update scope, workspace/branch
choice, and local delivery destination. It must also bind `base_branch`, `base_commit`,
`feature_branch`, `merge_strategy: --no-ff`, and the target branch's drift and conflict recovery
rules. Each package has one writer handoff and one fresh-review handoff. Include migration and failure
handling when the change affects data, permissions, dependencies, compatibility, or operational
behavior.

The plan remains read-only. Once the user explicitly approves the exact Work ID and plan version,
the implementation handoff creates the named feature branch from the recorded base commit before
any product write; direct development on the base branch is not an allowed implementation path.

Present the complete plan as the single approval gate. Wait for an explicit response naming the Work
ID and plan version. Any changed scope, interface, scenario, command, or destination supersedes the
plan and returns the work here.

Handoff: `phase: approval` with a reviewable, complete plan; approval is not implied by producing it.
