---
name: megin-test-driven-development
description: Execute Megin's outside-in BDD/TDD red-green-refactor loop for approved scenarios. Use for a Megin Work ID's implementation or repair requiring assertion-failing red and passing green evidence.
---

# Megin test-driven development

Read [repository-workflow.md](../megin/references/repository-workflow.md) for root/resume and stage contracts,
then [language-policy.md](../megin/references/language-policy.md) for human-readable output.

Use approved scenarios and project test conventions. Before every write, run
`unified_workflow.py check` with one selected root, Work ID and writer.

For every SCN, preserve an assertion-failing red before implementation, make the smallest
change, then preserve passing green with the same test digest. Import/setup/environment
failures, zero executed tests or skipped tests cannot supply that cycle. Keep exact commands,
cwd, execution sequence, exit codes, counts and raw claim locators. Add relevant boundary/failure
coverage and run approved broader checks. Group paths include Repo prefixes; cwd identifies
the Group or selected Repo.

Finish with one valid raw red/green cycle per BDD scenario and final check output bound to
the current combined snapshot. Repairs require fresh independent review within the retained
correction cap; staging/committing belongs to accepted delivery.
