---
name: megin-requirements-discovery
description: Clarify requirements for a Megin Repo or Group Work ID before architecture and planning. Use for Megin product decisions, scope or observable acceptance; ordinary feature requests retain their existing workflow.
---

# Megin requirements discovery

Read [repository-workflow.md](../megin/references/repository-workflow.md) for root/resume and reference selection,
then [language-policy.md](../megin/references/language-policy.md) for human-readable output.
Apply [requirements-discovery-protocol.md](../megin/references/requirements-discovery-protocol.md).

1. Start read-only. Resolve discoverable facts from current behavior, instructions, tests and
   docs; cite locations and distinguish facts, assumptions, requirements and suggestions.
2. Clarify problem, audience, outcome, constraints and observable acceptance before proposing
   implementation. Repo stays in its root; Group inventories every valid direct-child Repo's
   purpose and retains unchanged Repos in the requirements master.
3. Ask the protocol's next prerequisite-ready product question when a decision blocks scope,
   behavior or acceptance; retain `requirements / awaiting_user` until resolved.

Finish with `docs/work/<Work ID>/requirements.md`: REQ IDs, scope, exclusions, decisions
and scenarios, with the protocol's completion conditions met. Hand stable intent to
`$megin-architecture-exploration` for complete source reconciliation. This stage creates
work records, without product writes or branch creation.
