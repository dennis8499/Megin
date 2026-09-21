---
name: megin-finishing-delivery
description: Finish a verified and human-accepted Megin change with source-backed knowledge review and one local commit. Use for final delivery, commit preparation, 交付收尾、建立本機 commit; do not run before acceptance or publish externally.
---

# Megin finishing delivery

Read [../megin/references/language-policy.md](../megin/references/language-policy.md) and
[../megin/references/branch-policy.md](../megin/references/branch-policy.md) before creating
delivery notes. Write human-readable delivery summaries in Traditional Chinese while preserving
commit IDs, staged paths, commands, and status values exactly.

Use only after `megin-human-acceptance` records the exact Work ID and acceptance version. Confirm
workspace, branch, approved paths, reviewed and verified snapshot, knowledge scope, destination,
and final diff. Confirm the current branch is the recorded feature branch, the base branch still
matches the recorded integration target, and the acceptance response covers this exact snapshot.
Stop on unrelated files, branch drift, stale evidence, or an unauthorized target.

Run `megin-project-knowledge` over the approved source-backed scope. Preserve unsupported or
conflicting claims as pending and leave canonical knowledge unchanged unless the repository's
promotion contract and the approved scope permit the update.

Stage only approved product, test, documentation, and authorized knowledge paths on the feature
branch; create one focused feature commit and record its identity, staged paths, final status,
evidence, and unresolved pending items. Then switch to the recorded base branch and verify it has
not advanced. Use `git merge --no-ff <feature_branch>` to create the local merge commit, verify its
two parents and content equivalence, and record the integration evidence. If the base branch
advanced or merge conflicts occur, preserve the state and return to branch-policy recovery; do not
force the merge. Push, pull requests, deployment, branch deletion, and worktree cleanup require a
separate explicit request and are outside this Skill.

Handoff: `status: complete` only when the knowledge result, feature commit, merge commit, integration
checks, and final status are recorded; otherwise leave the exact pending action in `workflow.md`.
