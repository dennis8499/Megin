---
name: megin-finishing-delivery
description: Submit verified human-accepted Megin changes as local feature commits in one Repo or a Group. Use for final delivery and commit preparation; leave branches for the user's merge decision without publishing.
---

# megin-finishing-delivery

Read [repository-workflow.md](../megin/references/repository-workflow.md), [workspace-workflow.md](../megin/references/workspace-workflow.md), [new-work-evidence.md](../megin/references/new-work-evidence.md) and [language-policy.md](../megin/references/language-policy.md).

Start after independent APPROVED review, fresh passing checks and explicit human acceptance of exact Work ID/version/snapshot. Set `delivery / active`. Run `unified_workflow.py deliver` with the same root/Work ID/writer. It validates evidence before staging, rechecks all remote master SHAs, stages accepted paths, saves the delivery gate and creates one feature commit per Repo in dependency order.

Completion verifies each feature commit directly descends from pinned master and combined committed content matches acceptance. New work requires no local master movement or merge commit. Save completion, mark complete and release locks after the completion gate passes. Leave each Repo on its feature branch. Do not push, merge, create MRs, deploy, delete branches or clean worktrees.

Partial failure retains accepted commits/locks. Resume `deliver` to finish missing commits, including recovery from a crash after Git commit but before its record. Never recreate/reset a delivered commit. Remote/base or snapshot drift needs renewed approval/review/verification/acceptance.

When requested export historical v2 receipts with `delivery_receipt.py --repo|--group-root`; read [delivery-receipts.md](../megin/references/delivery-receipts.md). Legacy work retains its original package/rules.
