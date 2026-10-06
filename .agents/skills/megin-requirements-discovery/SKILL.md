---
name: megin-requirements-discovery
description: Explore and clarify a repository change before implementation. Use for requirements, scope, product behavior, feature requests, 新功能需求、需求整理、範圍釐清; do not use for an already-approved implementation, pure explanation, or a bug diagnosis.
---


# Megin requirements discovery

Read [../megin/references/language-policy.md](../megin/references/language-policy.md), [../megin/references/repository-workflow.md](../megin/references/repository-workflow.md), and [../megin/references/requirements-discovery-protocol.md](../megin/references/requirements-discovery-protocol.md). Discover requirements in exactly one selected Git repository.

First pass is read-only. Read Repo-local instructions, current source, meaningful tests, documentation, and relevant `docs/` knowledge. Cite exact paths and observations for current behavior; distinguish source evidence, user statements, and assumptions. Ask focused questions where a product decision remains unresolved. Do not inspect siblings or infer that a similarly named Repo is in scope.

Record the user problem, desired outcome, current behavior, scope, exclusions, decisions, risks, and observable scenarios in `docs/work/<Work ID>/requirements.md`. Identify compatibility, accessibility, security, migration, and failure cases where applicable. Keep unknowns visible and block planning when they change behavior or acceptance. Handoff: source-backed requirements and open decisions for the selected Repo.
