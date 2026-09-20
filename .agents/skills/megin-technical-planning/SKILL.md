---
name: megin-technical-planning
description: Turn a clarified Megin request into an implementation-ready plan. Use for technical design, task breakdown, interfaces, tests, migration or delivery planning, 技術規劃、拆解任務、實作計畫; do not mutate product files before approval.
---

# Megin technical planning

Work read-only after `megin-requirements-discovery` has produced a current requirements revision.
Read the target code, tests, project knowledge, and available validation commands. Keep the smallest
safe design; classify the work as small or large by impact and uncertainty rather than line count.

Write `plan.md` beside the Work ID record. It must bind the requirements revision to interfaces,
dependency-ordered work packages, exact allowed paths, forbidden paths, acceptance scenarios,
focused/related/full test commands, evidence locations, knowledge-update scope, workspace/branch
choice, and local delivery destination. Each package has one writer handoff and one fresh-review
handoff. Include migration and failure handling when the change affects data, permissions,
dependencies, compatibility, or operational behavior.

Present the complete plan as the single approval gate. Wait for an explicit response naming the Work
ID and plan version. Any changed scope, interface, scenario, command, or destination supersedes the
plan and returns the work here.

Handoff: `phase: approval` with a reviewable, complete plan; approval is not implied by producing it.
