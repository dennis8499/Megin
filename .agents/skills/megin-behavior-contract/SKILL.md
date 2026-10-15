---
name: megin-behavior-contract
description: Define executable Given/When/Then scenarios for Megin planning, BDD/TDD, review and human acceptance. Use when a Megin Work ID needs behavior contracts or REQ-to-SCN assertion mapping.
---

# Megin behavior contract

Read [repository-workflow.md](../megin/references/repository-workflow.md) for root/resume and stage contracts,
then [language-policy.md](../megin/references/language-policy.md) for output and Gherkin language.

Derive observable Given/When/Then scenarios from clarified requirements. Cover relevant
normal, boundary, failure, retry and recovery behavior within that scope. Planning freezes
scenarios before approval; implementation executes them afterward.

Finish when every REQ maps to SCNs, observable assertions, approved check commands/cwd
and implementation paths. Group implementation/test paths include the selected Repo name
and cover cross-Repo contracts. Keep feature/step files in approved paths. Hand the same
frozen scenarios to planning, BDD/TDD, review and human acceptance.
