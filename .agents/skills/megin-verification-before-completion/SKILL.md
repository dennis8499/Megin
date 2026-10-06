---
name: megin-verification-before-completion
description: Prove a Megin change is complete with fresh commands, scenarios, review evidence, and snapshot checks. Use for final verification, release readiness, 完成前驗證、驗證交付; do not skip failed or stale obligations.
---


# Megin verification before completion

Read [../megin/references/repository-workflow.md](../megin/references/repository-workflow.md) and [../megin/references/quality-gates.md](../megin/references/quality-gates.md). Verify only the exact approved Work ID, plan, and snapshot in the selected Repo.

Run every approved check from its recorded working directory and preserve raw output, exit code, and test counts. Include relevant static, contract, regression, and full-suite checks already named by the plan. Do not substitute a convenient passing check for an approved obligation. Compare the snapshot before and after; any change requires a fresh review and verification.

Run the read-only `acceptance` gate with `quality_gate.py check --repo <Repo> --work-id <Work ID> --gate acceptance`. This gate checks current evidence and independent review; it does not represent user acceptance. Report failures with exact evidence and keep the workflow out of delivery until all checks pass.
