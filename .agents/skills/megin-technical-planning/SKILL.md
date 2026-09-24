---
name: megin-technical-planning
description: Turn a clarified Megin request into an implementation-ready plan. Use for technical design, task breakdown, interfaces, tests, migration or delivery planning, 技術規劃、拆解任務、實作計畫; do not mutate product files before approval.
---

# Megin technical planning

Read [../megin/references/language-policy.md](../megin/references/language-policy.md),
[../megin/references/group-workspace.md](../megin/references/group-workspace.md),
[../megin/references/branch-policy.md](../megin/references/branch-policy.md), and
[../megin/references/requirements-discovery-protocol.md](../megin/references/requirements-discovery-protocol.md)
before creating or updating a plan. Work read-only after `megin-requirements-discovery` has produced a current
requirements revision. Re-read `requirements.md`, its sources, capability coverage, decisions, blockers, and acceptance
against the protocol's completion conditions. If any major unknown could change the goal, audience, boundary, interface,
important risk, core behavior, or acceptance, return to requirements discovery and keep `phase: requirements` with
`status: awaiting_user`; do not write or present a plan. Never treat a `ready_for_planning` flag, question count, or
document existence as proof of completion.
Read each selected Repo's own code, tests, project knowledge, remote configuration, base branch, and available validation commands. During planning query each exact remote ref with `git ls-remote --exit-code`; do not substitute a local tracking ref. Keep the smallest
safe design; classify the work as small or large by impact and uncertainty rather than line count.
Read [../megin/references/quality-gates.md](../megin/references/quality-gates.md) for the shared
obligation and snapshot contract. Map each observable result to a meaningful assertion, exact
command, and required environment; split independently failing promises. Include failure paths
only when the change makes them relevant. The plan remains the sole source of approved obligations.

Write `plan.md` in the central Group Work ID record. It must bind each selected Repo path, remote
name/URL, exact remote base SHA, `feature/<Work ID>`, Repo-relative allowed paths, and every check's
explicit command and `cwd`, as well as the requirements revision, interfaces, dependency-ordered
work packages, forbidden paths, acceptance scenarios, evidence locations, knowledge scope, and
delivery mode. For one Repo, specify the fast-forward-to-confirmed-base then `--no-ff` local merge;
for several, specify feature commits and per-Repo manual handoff without base merges. Each package has
one writer handoff and one fresh-review handoff. Include migration and failure
handling when the change affects data, permissions, dependencies, compatibility, or operational
behavior.

The plan remains read-only. Once the user explicitly approves the exact Work ID and plan version,
the implementation handoff creates the named feature branch from the recorded base commit before
any product write; direct development on the base branch is not an allowed implementation path.

Present the complete plan as the single approval gate. Wait for an explicit response naming the Work
ID and plan version. Any changed scope, interface, scenario, command, or destination supersedes the
plan and returns the work here.

Handoff: `phase: approval` with a reviewable, complete plan; approval is not implied by producing it.
