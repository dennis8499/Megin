---
name: megin-human-acceptance
description: Guide the Megin human acceptance gate using only approved user-visible scenarios. Use after automated verification, 人工驗收、使用者驗測、驗收確認; do not stage, commit, or promote knowledge before acceptance.
---

# megin-human-acceptance

Read [repository-workflow.md](../megin/references/repository-workflow.md), [workspace-workflow.md](../megin/references/workspace-workflow.md), [new-work-evidence.md](../megin/references/new-work-evidence.md) and [language-policy.md](../megin/references/language-policy.md).

Start after independent APPROVED review and fresh passing automated checks for the same combined snapshot. Present Work ID, plan/acceptance versions, selected Repos, user operations and expected observable results in the user's language. Run the read-only acceptance gate with the selected root and Work ID.

Wait for the human's literal acceptance or rejection. Save actor_kind: human, Work ID, version, response, timestamp, verdict and exact snapshot with raw claim locators. Automated success or a simulated actor cannot accept for the user. Rejection or snapshot change returns to repair/review/verification. Do not stage, commit, merge or promote knowledge before acceptance.
