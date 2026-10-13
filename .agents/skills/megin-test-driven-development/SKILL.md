---
name: megin-test-driven-development
description: Run Megin's outside-in behavior red-green-refactor loop for an approved task. Use for TDD, BDD, regression coverage, test-first development, 測試驅動、回歸測試; do not expand scope or waive a failing obligation.
---

# megin-test-driven-development

Read [repository-workflow.md](../megin/references/repository-workflow.md), [workspace-workflow.md](../megin/references/workspace-workflow.md), [new-work-evidence.md](../megin/references/new-work-evidence.md) and [language-policy.md](../megin/references/language-policy.md).

Use the approved scenarios and project test conventions. Before every write run `unified_workflow.py check` with exactly one selected root, Work ID and writer.

For each SCN preserve an assertion-failing red before implementation, make the smallest change and preserve passing green with the same test digest. Import/setup/environment failures, zero executed tests and skipped tests do not count. Keep exact commands, cwd, execution sequence, exit codes, counts and raw claim locators. Add meaningful boundary/failure coverage and run approved broader checks. For Group tests, paths are Group-relative and cwd identifies the Group or a selected Repo.

Keep one valid raw red/green cycle per BDD scenario and bind final check output to the current combined snapshot. Repairs require TDD evidence and a fresh independent review within the retained correction cap. Do not stage or commit.
