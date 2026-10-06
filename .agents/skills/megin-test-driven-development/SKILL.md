---
name: megin-test-driven-development
description: Run Megin's outside-in behavior red-green-refactor loop for an approved task. Use for TDD, BDD, regression coverage, test-first development, 測試驅動、回歸測試; do not expand scope or waive a failing obligation.
---


# Megin test-driven development

Read [../megin/references/language-policy.md](../megin/references/language-policy.md) and [../megin/references/repository-workflow.md](../megin/references/repository-workflow.md). Follow the approved behavior scenarios and test conventions in the selected Repo.

For each behavior, identify an assertion that would fail before the implementation, run it and preserve its output, then make the smallest implementation change and rerun it. A syntax/import/setup failure is not evidence that the behavior test is red. Add relevant boundary and failure cases. Run focused and approved broader checks, recording exact commands, working directories, exit codes, and test counts.

Before each file write, verify the Repo lock with `repo_workspace.py check --repo <Repo> --work-id <Work ID> --writer <identity>`. Keep tests and code within approved paths. Do not stage or commit. Handoff: red/green evidence tied to the same approved scenario and current snapshot.
