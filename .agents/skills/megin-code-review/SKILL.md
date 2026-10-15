---
name: megin-code-review
description: Independently review an approved frozen Megin snapshot against requirements, scope, behavior and evidence. Use for a Megin Work ID's review or re-review; the reviewer must be a fresh read-only context that did not author the changes.
---

# Megin code review

Read [repository-workflow.md](../megin/references/repository-workflow.md) for root/resume and stage contracts,
then [language-policy.md](../megin/references/language-policy.md) for human-readable output.

1. Start in a new independent read-only context after the writer freezes a snapshot.
   Review directly without edits, staging, commits or further delegation. The author cannot
   self-approve; without a separate context, set `awaiting_review` and stop progression.
2. Inspect exact requirements, architecture, approved plan, changed paths, code, tests and docs.
   Trace REQ → SCN → assertion → code → checks → review → acceptance. Check discovery coverage,
   effective assertions, failure cases, remote-master identity and compatibility. Fixed-input
   tests must consume pinned bytes. Cite file/line findings.
3. In Group, apply [group-impact.md](../megin/references/group-impact.md): reconcile actual diff
   with the frozen graph and direct/indirect unchanged consumers. Judge API/event/data/package/
   table/configuration compatibility and exclusion reasons from fixed searches and relationships.
   New interfaces/consumers need renewed planning; missing necessary source keeps review incomplete.
4. Run `quality_gate.py check --gate review` for the selected root/Work ID. Record the real
   context/invocation ID, snapshot, findings and `APPROVED` or `CHANGES_REQUESTED`; append via
   `review_history.py`. Structural success proves consistency, not semantic correctness or independence.

Finish with an immutable attempt: initial round 0, at most three corrections/re-reviews,
each in a new context. Stop early on approval; failed round 3 remains incomplete.
Resume preserves history and the same cap.
