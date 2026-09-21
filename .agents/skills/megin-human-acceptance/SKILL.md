---
name: megin-human-acceptance
description: Guide the Megin human acceptance gate using only approved user-visible scenarios. Use after automated verification, 人工驗收、使用者驗測、驗收確認; do not stage, commit, or promote knowledge before acceptance.
---

# Megin human acceptance

Read [../megin/references/language-policy.md](../megin/references/language-policy.md) before
presenting or recording acceptance. Show user operations and expected results in Traditional
Chinese, preserving Work IDs, versions, paths, commands, and other control values verbatim.

Use only after a fresh review and automated verification pass. Present the Work ID, acceptance
version, workspace/branch, environment, each approved user operation, and its expected observable
result. Do not turn internal tests or reviewer checks into extra manual work.

Wait for a response that identifies the displayed Work ID and acceptance version and confirms the
listed scenarios. Record the response, timestamp, and accepted snapshot in `workflow.md`. If a
scenario fails, record the observed result and return to the affected implementation task for a
new review and verification cycle. Before acceptance, do not update formal knowledge, stage paths,
or create a commit.

Handoff: `phase: delivery` and an exact acceptance record, or a named failed scenario with the next
repair action.
