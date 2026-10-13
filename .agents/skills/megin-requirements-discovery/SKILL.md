---
name: megin-requirements-discovery
description: Clarify Repo or Group requirements before architecture exploration. Use for requirements, scope, product behavior, feature requests, 新功能需求、需求整理、範圍釐清; do not implement an unapproved solution.
---

# megin-requirements-discovery

Read [repository-workflow.md](../megin/references/repository-workflow.md), [workspace-workflow.md](../megin/references/workspace-workflow.md), [new-work-evidence.md](../megin/references/new-work-evidence.md) and [language-policy.md](../megin/references/language-policy.md).

Apply [requirements-discovery-protocol.md](../megin/references/requirements-discovery-protocol.md). First pass is read-only. Clarify problem, audience, outcome, constraints and observable acceptance without prescribing implementation. Read current behavior, instructions, tests and documentation to resolve discoverable facts. Cite locations and distinguish facts, assumptions, requirements and suggestions.

In Group mode inventory every valid direct-child Repo and its purpose, retaining unchanged Repos in the requirements master. Repo mode stays in its selected root. Ask focused product questions when behavior/scope/acceptance remains ambiguous; preserve blockers in `requirements / awaiting_user`.

Write `docs/work/<Work ID>/requirements.md` with REQ IDs, scope, exclusions, decisions and scenarios. Once intent is stable, hand off to `$megin-architecture-exploration` for complete functional/source reconciliation before planning. No branch creation or product writes occur here.
