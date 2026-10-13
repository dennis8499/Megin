---
name: megin-bug-diagnosis
description: Diagnose a suspected bug with read-only evidence before repair. Use for bugs, errors, regressions, failures, 錯誤、異常、回歸、失效; do not implement a fix during diagnosis or confuse an explanation request with a repair request.
---

# megin-bug-diagnosis

Read [repository-workflow.md](../megin/references/repository-workflow.md), [workspace-workflow.md](../megin/references/workspace-workflow.md), [new-work-evidence.md](../megin/references/new-work-evidence.md) and [language-policy.md](../megin/references/language-policy.md).

Diagnosis is read-only until exact-plan approval. Reproduce the symptom with a focused check, then trace relevant source, tests and documentation. Select Repo/Group mode using the shared contract. Repo mode stays in its root; Group mode may trace its valid Repos and cross-Repo dependencies.

Separate observations from hypotheses. Report reproduction command/output, smallest evidence-backed cause, affected behavior and regression scenario. Identify the next discriminating observation when evidence is incomplete. Repair follows requirements → architecture → planning → approval → BDD/TDD → independent review → verification → human acceptance → feature delivery.
