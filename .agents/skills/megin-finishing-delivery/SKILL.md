---
name: megin-finishing-delivery
description: Deliver independently reviewed, verified and human-accepted Megin changes as local feature commits. Use for a Megin Work ID's final delivery or partial-delivery recovery, leaving feature branches for the user's merge decision.
---

# Megin finishing delivery

Read [repository-workflow.md](../megin/references/repository-workflow.md) for root/resume and stage contracts,
then [language-policy.md](../megin/references/language-policy.md) for human-readable output.

1. Require independent `APPROVED` review, fresh checks and explicit human acceptance of exact
   Work ID/version/snapshot. Set `delivery / active`; run `unified_workflow.py deliver` with
   the same root/Work ID/writer. It validates evidence, rechecks every remote master SHA,
   stages accepted paths, saves the gate and commits each Repo in dependency order.
2. Verify each feature commit has pinned master as its direct parent and combined committed
   content matches acceptance. New work leaves local master untouched and creates no merge
   commit. Save completion, mark complete and release locks only after the completion gate passes.
3. On partial failure retain accepted commits and locks. Resume `deliver` for missing commits,
   including recovery after commit-before-record crashes; preserve delivered commits. Remote/base
   or snapshot drift requires renewed approval/review/verification/acceptance.

Finish with each Repo on its feature branch and saved passing completion evidence. Push,
merge, MR creation, deployment, branch deletion and worktree cleanup are separate user-directed
work. For requested historical v2 receipt export, read
[delivery-receipts.md](../megin/references/delivery-receipts.md) and use
`delivery_receipt.py --repo|--group-root`; legacy work retains its original package/rules.
