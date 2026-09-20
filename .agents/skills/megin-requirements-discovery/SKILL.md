---
name: megin-requirements-discovery
description: Explore and clarify a repository change before implementation. Use for requirements, scope, product behavior, feature requests, 新功能需求、需求整理、範圍釐清; do not use for an already-approved implementation, pure explanation, or a bug diagnosis.
---

# Megin requirements discovery

Work read-only. Inspect repository instructions, relevant code, tests, project knowledge, current
branch, and existing Megin records before asking questions. Resolve facts from evidence; ask one
frontier question at a time only for priorities, boundaries, or trade-offs.

Create or update the current Work ID's `requirements.md` and `workflow.md` with the goal, audience,
in/out scope, affected interfaces, constraints, risks, assumptions, knowledge scope, and acceptance
criteria. Give every externally observable behavior a stable scenario ID and concrete Given/When/Then
result. Mark existing coverage instead of inventing a red test.

For a suspected defect, route to `megin-bug-diagnosis` first. For an explanation, review, or plan-only
request, report evidence without creating a change candidate. Finish this phase only when the user
can review a bounded candidate and all discoverable facts have source paths or locators.

Handoff: `phase: planning`, with the exact requirements revision recorded. A changed goal, scope, or
acceptance criterion creates a new revision and requires planning again.
