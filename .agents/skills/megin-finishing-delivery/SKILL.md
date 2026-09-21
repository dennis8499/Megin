---
name: megin-finishing-delivery
description: Finish a verified and human-accepted Megin change with source-backed knowledge review and one local commit. Use for final delivery, commit preparation, 交付收尾、建立本機 commit; do not run before acceptance or publish externally.
---

# Megin finishing delivery

Read [../megin/references/language-policy.md](../megin/references/language-policy.md) before
creating delivery notes. Write human-readable delivery summaries in Traditional Chinese while
preserving commit IDs, staged paths, commands, and status values exactly.

Use only after `megin-human-acceptance` records the exact Work ID and acceptance version. Confirm
workspace, branch, approved paths, reviewed and verified snapshot, knowledge scope, destination,
and final diff. Stop on unrelated files, branch drift, stale evidence, or an unauthorized target.

Run `megin-project-knowledge` over the approved source-backed scope. Preserve unsupported or
conflicting claims as pending and leave canonical knowledge unchanged unless the repository's
promotion contract and the approved scope permit the update.

Stage only approved product, test, documentation, and authorized knowledge paths; create one focused
local commit and record its identity, staged paths, final status, evidence, and unresolved pending
items. Push, pull requests, merge, deployment, branch deletion, and worktree cleanup require a
separate explicit request and are outside this Skill.

Handoff: `status: complete` only when the knowledge result and local commit are recorded; otherwise
leave the exact pending action in `workflow.md`.
