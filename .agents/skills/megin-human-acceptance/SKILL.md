---
name: megin-human-acceptance
description: Record the human acceptance decision for an independently reviewed, verified Megin snapshot. Use for a Megin Work ID's user operations and expected outcomes before staging, committing or promoting knowledge.
---

# Megin human acceptance

Read [repository-workflow.md](../megin/references/repository-workflow.md) for root/resume and stage contracts,
then [language-policy.md](../megin/references/language-policy.md) for human-readable output.

Start after independent `APPROVED` review and fresh passing checks on the same combined
snapshot. Present Work ID, plan/acceptance versions, selected Repos, user operations and
expected results. Run the read-only acceptance gate for the selected root/Work ID.

Wait for the human's literal acceptance or rejection. Save `actor_kind: human`, Work ID,
version, response, timestamp, verdict, exact snapshot and raw claim locators. Automated
success or a simulated actor cannot supply the human decision.

Finish only with that recorded decision. Rejection or snapshot change returns to
repair/review/verification. Staging, commits, merges and knowledge promotion wait for acceptance.
