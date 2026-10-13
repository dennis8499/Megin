---
name: megin-behavior-contract
description: Define executable behavior scenarios shared by Megin planning, tests, review, and human acceptance. Use for Gherkin, BDD, acceptance criteria, 行為契約、驗收情境; do not invent behavior outside the approved requirements.
---

# megin-behavior-contract

Read [repository-workflow.md](../megin/references/repository-workflow.md), [workspace-workflow.md](../megin/references/workspace-workflow.md), [new-work-evidence.md](../megin/references/new-work-evidence.md) and [language-policy.md](../megin/references/language-policy.md).

Write observable Given/When/Then scenarios derived from the clarified requirements. Keep Gherkin keywords and IDs in English and descriptions in the user's language. Cover relevant normal, boundary, failure, retry and recovery cases without inventing behavior.

Planning freezes scenarios before approval; implementation executes them afterward. Map every REQ to SCNs, observable assertions, approved checks/cwd and implementation paths. In Group mode prefix implementation/test paths with the selected Repo name and cover cross-Repo contracts. Keep feature/step files within approved paths. Handoff scenarios for planning, BDD/TDD, review and human acceptance.
