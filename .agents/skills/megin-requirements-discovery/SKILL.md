---
name: megin-requirements-discovery
description: Explore and clarify a repository change before implementation. Use for requirements, scope, product behavior, feature requests, 新功能需求、需求整理、範圍釐清; do not use for an already-approved implementation, pure explanation, or a bug diagnosis.
---

# Megin requirements discovery

Read [../megin/references/language-policy.md](../megin/references/language-policy.md),
[../megin/references/branch-policy.md](../megin/references/branch-policy.md), and
[../megin/references/requirements-discovery-protocol.md](../megin/references/requirements-discovery-protocol.md)
before creating or updating a work document. Work read-only. Inspect repository instructions, relevant code, tests,
project knowledge, current branch, and existing Megin records before asking questions. Resolve facts from evidence
and apply the protocol's research trigger, capability coverage, question dependency, and completion rules.

When the protocol identifies a major unknown that could change the product choice, core behavior, important risk,
interface, or acceptance, ask exactly one prerequisite-ready highest-impact question in Traditional Chinese and wait
for the user's answer. Keep the Work ID at `phase: requirements` and `status: awaiting_user`, record sources,
capabilities, decisions, blockers, and the unanswered question, and do not claim that requirements are complete or
hand off to planning. On resume, re-check the remaining unknowns and absorb every answer already supplied. When the
information is sufficient, do not ask a formal extra question merely to satisfy a template.

Create or update the current Work ID's `requirements.md` and `workflow.md` using
[requirements-template.md](../megin/references/requirements-template.md). Keep `requirements.md` as the sole
requirements master, use `SRC-*`, `CAP-*`, `Q-*`, and `SCN-*` identifiers, and record the current requirements
revision in `workflow.md`. Give every externally observable behavior a stable scenario ID and concrete
Given/When/Then result. Mark existing coverage instead of inventing a red test. Record the current branch and the
intended base branch, but do not create a feature branch or modify product files during requirements; feature branch
creation happens only after the plan is explicitly approved.

For a suspected defect, route to `megin-bug-diagnosis` first. For an explanation, review, or plan-only
request, report evidence without creating a change candidate. Finish this phase only when the user
can review a bounded candidate and all discoverable facts have source paths or locators. A `ready_for_planning` field
is only a summary and never replaces the completion check.

Handoff: `phase: planning`, with the exact requirements revision recorded. A changed goal, scope, or
acceptance criterion creates a new revision and requires planning again.
