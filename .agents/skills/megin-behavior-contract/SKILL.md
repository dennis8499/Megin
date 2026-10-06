---
name: megin-behavior-contract
description: Define executable behavior scenarios shared by Megin planning, tests, review, and human acceptance. Use for Gherkin, BDD, acceptance criteria, 行為契約、驗收情境; do not invent behavior outside the approved requirements.
---


# Megin behavior contract

Read [language-policy.md](../megin/references/language-policy.md), [repository-workflow.md](../megin/references/repository-workflow.md), and [branch-policy.md](../megin/references/branch-policy.md) before creating or updating feature files.

Write observable Given/When/Then scenarios for one selected Repo. Keep Gherkin keywords, Work IDs, paths, and control identifiers in English; write scenario descriptions in the user's language. Derive every scenario from approved requirements. Include relevant normal, boundary, failure, retry, and recovery behavior. Do not invent behavior or turn implementation details into user outcomes.

Store feature files and their step definitions within the approved Repo paths. Map each scenario to an assertion and an approved quality command. Preserve existing project conventions and avoid duplicating coverage without a reason. Handoff: reviewed scenarios with traceability to requirements, implementation paths, test commands, and human acceptance operations.
