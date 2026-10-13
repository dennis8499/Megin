---
name: megin-code-review
description: Perform a fresh read-only review of an approved Megin snapshot. Use for code review, quality review, scope review, knowledge integrity, 審查、檢視修改、品質檢查; do not edit, commit, delegate, or approve your own changes.
---

# megin-code-review

Read [repository-workflow.md](../megin/references/repository-workflow.md), [workspace-workflow.md](../megin/references/workspace-workflow.md), [new-work-evidence.md](../megin/references/new-work-evidence.md) and [language-policy.md](../megin/references/language-policy.md).

Start from a new independent read-only context after the writer freezes a snapshot. The reviewer must not have authored the implementation. Do not edit, stage, commit, delegate the review or self-approve.

Inspect exact requirements, architecture, approved plan, changed paths, code, tests and relevant Repo documentation. Trace REQ → SCN → assertion → code → checks → review → acceptance; check discovery coverage, meaningful assertions, failure cases, remote-master branch identity and cross-Repo compatibility. For fixed inputs, verify tests consume their pinned bytes. Cite file/line findings.

For Group read [group-impact.md](../megin/references/group-impact.md). Review actual diff confirmation against the frozen graph, following direct and indirect unchanged consumers. Inspect API/event/data/package/table/configuration compatibility and exclusion reasons; search terms and aliases need source relationships. New interfaces/consumers require renewed planning. Missing necessary source leaves review incomplete. Structure proves evidence consistency; independently judge whether every semantic interface and consumer was correctly classified.

Run `quality_gate.py check --gate review` with the selected `--repo` or `--group-root` and Work ID. A structural pass does not prove semantic correctness or independence. Record real context/invocation ID, APPROVED or CHANGES_REQUESTED, snapshot and findings; append using `review_history.py`.

Initial review is round 0. Allow at most three correction/re-review attempts, each with a new independent context. Stop early on approval or after failed round 3. Preserve immutable attempts on resume. If a real independent context is unavailable, use `awaiting_review` and stop progression.
