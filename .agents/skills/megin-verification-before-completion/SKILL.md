---
name: megin-verification-before-completion
description: Prove a Megin change is complete with fresh commands, scenarios, review evidence, and snapshot checks. Use for final verification, release readiness, 完成前驗證、驗證交付; do not skip failed or stale obligations.
---

# megin-verification-before-completion

Read [repository-workflow.md](../megin/references/repository-workflow.md), [workspace-workflow.md](../megin/references/workspace-workflow.md), [new-work-evidence.md](../megin/references/new-work-evidence.md) and [language-policy.md](../megin/references/language-policy.md).

Verify the exact approved Work ID/plan/snapshot. Run every approved command from its recorded cwd with original stdout/stderr, exit codes and test counts. Do not substitute convenient checks for obligations. Include declared cross-Repo compatibility tests; checks require nonzero executed tests, no failures and no skips.

When declared, use fixed committed inputs and exact read-only runner probes from [verification-extensions.md](../megin/references/verification-extensions.md). Bind their digests in structured and raw output. Resolve runner failures before proceeding.

Set verification/acceptance phase and run the read-only `acceptance` gate with the selected root and Work ID. This checks review and automated evidence; it is not human acceptance. Any changed snapshot needs repair, a new independent review and fresh verification within the existing correction cap.
