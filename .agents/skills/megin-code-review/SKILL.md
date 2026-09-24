---
name: megin-code-review
description: Perform a fresh read-only review of an approved Megin snapshot. Use for code review, quality review, scope review, knowledge integrity, 審查、檢視修改、品質檢查; do not edit, commit, delegate, or approve your own changes.
---

# Megin code review

Read [../megin/references/language-policy.md](../megin/references/language-policy.md) and
[../megin/references/group-workspace.md](../megin/references/group-workspace.md) and
[../megin/references/branch-policy.md](../megin/references/branch-policy.md) before creating a
review report. Write findings, explanations, and event text in Traditional Chinese;
retain verdict tokens, paths, symbols, commands, and evidence identifiers in English or verbatim.

Start in a fresh reviewer context after the writer reports completion. Load the exact central Group
Work ID and plan, inspect each selected Repo's full diff and surrounding code, tests, configuration,
documentation, generated artifacts, knowledge claims, plus the protected Group plan and current
composite snapshot. Confirm every Repo is on its recorded feature branch, each base branch has not
entered the product diff, each changed path is allowed, and every acceptance scenario has meaningful
coverage. Run the Group `review` quality gate with `--group-root` and `--work-id`.
Read [../megin/references/quality-gates.md](../megin/references/quality-gates.md) and retain the
actual fresh reviewer source and raw verdict. Independently trace each consequential promise to
the assertion that would fail if the behavior were absent; distinguish configuration, mock, and
partial integration evidence from the promised full path.
Start the saved raw review with the exact machine-readable `context`, `verdict`, and `snapshot`
lines defined by that reference. The structured evidence must point to those same hashed lines.

Check behavior, error paths, compatibility, security/privacy, data and permission effects,
operational failure handling, test quality, evidence freshness, and source-backed knowledge. Record
findings with severity, path or symbol, evidence, and a concrete correction. Return exactly one
verdict: `APPROVED`, `CHANGES_REQUIRED`, or `BLOCKED`.

`APPROVED` covers the exact multi-Repo and protected Group product snapshot only. A protected
change, remote/base advance, or branch identity mismatch requires a fresh review. A reviewer is
read-only and cannot approve its own work; if independent review is not
available, record `BLOCKED` and leave the work at `awaiting_review`.
