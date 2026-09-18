---
name: finishing-delivery
description: Finish a verified and human-accepted Megin v3 change by reviewing knowledge, staging approved paths, and creating one local commit.
---

# Finishing Delivery

Use this skill only after `verify` passes and the user records the exact human acceptance response. Before that gate it must not update knowledge, stage paths, or create a commit. v3 creates one local commit after checking source-backed knowledge; push, merge, and draft PR are outside this workflow.

## Preflight

Confirm the current workspace and branch, approved path set, verification snapshot, configured remote, base branch, and publication destination. Inspect status and diff before staging. Stop if the diff contains unapproved files, the branch identity drifted, verification is stale, or the destination is not authorized.

## Delivery sequence

1. In `unstaged` mode, inspect and record the approved diff, changed paths, snapshot, and suggested commit without staging or publishing anything.
2. In `commit` or `draft-pr` mode, stage only the approved product, test, documentation, and authorized knowledge files.
3. In `commit` or `draft-pr` mode, create a focused commit whose message states the resulting behavior or fix. Record commit identity and the staged path list.
4. In `draft-pr` mode, push the approved branch to the approved remote. Do not rewrite history or push another branch as a workaround.
5. In `draft-pr` mode, find an existing pull request for the repository and branch before creating one. Create or reuse a **draft** pull request only when the approved target and available tooling permit it.
6. Record the delivery state, branch, changed paths, suggested commit or commit identity, remote branch, pull request identity/URL, and final local status in the delivery evidence.

The draft pull request should state the problem, resulting behavior, validation commands and outcomes, knowledge changes, pending items, and the work identity. Do not store credentials in the repository or evidence.

## Failure and resume

If push or PR creation fails because of missing remote, authentication, network, or tooling in `draft-pr` mode, preserve the workspace and successful local commit. Report `PUBLISH_PENDING` with the exact failed action and resume only that action later with explicit `--publish`. A `commit` finish is complete after the local commit and never enters publication pending merely because a remote is configured. If a PR already exists, update or reuse it rather than creating a duplicate.

This skill does not merge, deploy, delete branches, remove worktrees, clean files, or close issues. Those actions require separate explicit authorization. A local commit or a pushed branch is not evidence that a draft pull request exists.
