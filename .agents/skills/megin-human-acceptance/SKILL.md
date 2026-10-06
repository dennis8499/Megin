---
name: megin-human-acceptance
description: Guide the Megin human acceptance gate using only approved user-visible scenarios. Use after automated verification, 人工驗收、使用者驗測、驗收確認; do not stage, commit, or promote knowledge before acceptance.
---


# Megin human acceptance

Read [../megin/references/language-policy.md](../megin/references/language-policy.md) and [../megin/references/repository-workflow.md](../megin/references/repository-workflow.md). Use this stage only after independent review and automated verification pass for the same snapshot.

Present the Work ID, plan and acceptance versions, selected Repo, approved user operations, and expected observable results in the user's language. Run the read-only `acceptance` gate with `quality_gate.py check --repo <Repo> --work-id <Work ID> --gate acceptance`. Automated checks are not the user's acceptance.

Wait for a response that clearly accepts or rejects the displayed scenarios and version. Record the user's words, timestamp, and snapshot in the predeclared evidence. A failure or changed snapshot returns the work to repair, review, and verification. Do not stage, commit, merge, or promote project knowledge before acceptance. Handoff: explicit acceptance of the exact Work ID/version or a named failed scenario.
