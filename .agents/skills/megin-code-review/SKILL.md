---
name: megin-code-review
description: Perform a fresh read-only review of an approved Megin snapshot. Use for code review, quality review, scope review, knowledge integrity, 審查、檢視修改、品質檢查; do not edit, commit, delegate, or approve your own changes.
---

# Megin code review

Read [../megin/references/language-policy.md](../megin/references/language-policy.md) before
creating a review report. Write findings, explanations, and event text in Traditional Chinese;
retain verdict tokens, paths, symbols, commands, and evidence identifiers in English or verbatim.

Start in a fresh reviewer context after the writer reports completion. Load the exact approved Work
ID and plan, inspect the full diff and surrounding code, tests, configuration, documentation,
generated artifacts, knowledge claims, and current branch/snapshot. Confirm every changed path is
allowed and every acceptance scenario has meaningful coverage.

Check behavior, error paths, compatibility, security/privacy, data and permission effects,
operational failure handling, test quality, evidence freshness, and source-backed knowledge. Record
findings with severity, path or symbol, evidence, and a concrete correction. Return exactly one
verdict: `APPROVED`, `CHANGES_REQUIRED`, or `BLOCKED`.

`APPROVED` covers the exact snapshot only. Any change after the review invalidates it and requires a
fresh review. A reviewer is read-only and cannot approve its own work; if independent review is not
available, record `BLOCKED` and leave the work at `awaiting_review`.
