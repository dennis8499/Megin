---
name: finishing-delivery
description: Finish a verified repository change with an authorized commit, push, and draft pull request while preserving resumability and avoiding merge, deployment, or cleanup.
---

# Finishing Delivery

Use this skill only after `verification-before-completion` passes for the exact work identity and approved publication target. It owns the final Git and draft pull request actions; it does not change product behavior.

## Preflight

Confirm the current worktree and branch, approved path set, verification snapshot, configured remote, base branch, and publication destination. Inspect status and diff before staging. Stop if the diff contains unapproved files, the branch identity drifted, verification is stale, or the destination is not authorized.

## Delivery sequence

1. Stage only the approved product, test, documentation, and authorized knowledge files.
2. Create a focused commit whose message states the resulting behavior or fix. Record commit identity and the staged path list.
3. Push the approved branch to the approved remote. Do not rewrite history or push another branch as a workaround.
4. Find an existing pull request for the repository and branch before creating one. Create or reuse a **draft** pull request only when the approved target and available tooling permit it.
5. Record the commit, remote branch, pull request identity/URL, and final local status in the delivery evidence.

The draft pull request should state the problem, resulting behavior, validation commands and outcomes, knowledge changes, pending items, and the work identity. Do not store credentials in the repository or evidence.

## Failure and resume

If commit, push, or PR creation fails because of missing remote, authentication, network, or tooling, preserve the worktree and any successful commit. Report `PUBLISH_PENDING` with the exact failed action and resume only that action later. If a PR already exists, update or reuse it rather than creating a duplicate.

This skill does not merge, deploy, delete branches, remove worktrees, clean files, or close issues. Those actions require separate explicit authorization. A local commit or a pushed branch is not evidence that a draft pull request exists.
