---
name: megin-finishing-delivery
description: Finish a verified and human-accepted Megin change with source-backed knowledge review and the approved local delivery or GitLab workspace handoff mode. Use for final delivery, commit preparation, 交付收尾、建立本機 commit、驗收交接; do not run before acceptance or publish externally.
---


# Megin finishing and delivery

Read [../megin/references/repository-workflow.md](../megin/references/repository-workflow.md), [../megin/references/quality-gates.md](../megin/references/quality-gates.md), and [../megin/references/branch-policy.md](../megin/references/branch-policy.md). This stage runs only after fresh independent review, passing verification, and explicit user acceptance.

Confirm the Work ID, approved feature branch, accepted snapshot, allowed paths, and Repo lock. Stage only the accepted product paths. Run the `delivery` gate with `--repo <Repo> --work-id <Work ID>`; when the plan selected a remote, require its exact URL and base SHA to remain unchanged. Save the exact gate stdout, exit code, and SHA-256 in the predeclared delivery record.

Commit the accepted feature snapshot on the approved feature branch. Switch to the approved local base branch and integrate with `git merge --no-ff <feature-branch>`. Record full feature and merge SHAs. Run the `completion` gate; it checks the accepted tree, feature parent, exact two merge parents, merge tree, base pointer, and optional remote. Only after it passes, set `phase: delivery`, `status: complete`, then release the lock with `repo_workspace.py release`. Keep the lock on any failure. Native delivery is local; do not push or create a pull/merge request.
