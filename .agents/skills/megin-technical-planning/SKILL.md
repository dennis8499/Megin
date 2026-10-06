---
name: megin-technical-planning
description: Turn a clarified Megin request into an implementation-ready plan. Use for technical design, task breakdown, interfaces, tests, migration or delivery planning, 技術規劃、拆解任務、實作計畫; do not mutate product files before approval.
---


# Megin technical planning

Read [../megin/references/repository-workflow.md](../megin/references/repository-workflow.md), [../megin/references/branch-policy.md](../megin/references/branch-policy.md), and [../megin/references/quality-gates.md](../megin/references/quality-gates.md). Plan one Git repository only.

Turn approved requirements and BDD scenarios into an executable plan with ordered tasks, Repo-relative allowed paths, interfaces, test assertions, exact commands and working directories, knowledge updates, independent review, user acceptance, and local delivery. Record the current base branch and full SHA. The remote is optional; include exact remote name/URL and base SHA only when the user explicitly selects it.

Compute the installed Skills fingerprint and include it in `megin-repo-quality-contract/v1`. Predeclare every process record, including quality evidence and delivery result, before capturing a snapshot. The plan and contract must agree on Work ID, version, branch, paths, checks, and acceptance. Present risks, assumptions, and user-visible delivery behavior for explicit approval. Do not write product files before approval.
