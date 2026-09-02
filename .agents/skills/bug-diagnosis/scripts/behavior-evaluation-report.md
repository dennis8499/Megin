# BUG Diagnosis behavior evaluation report

- Revision: working tree
- Forward cases: 19/19 Pass on the Plan revision 3 candidate
- Fresh Reviewer: see the superseding 2026-08-31 entry and formal implementation Ledger

執行後只記錄實際 command／fixture evidence 與 Pass／Fail；不得預先宣稱通過。

## 2026-08-30 — local contract verification

- Base HEAD: `11316066df74e8b4828bd77ca80c743886d7f283`; isolated Work ID: `work-20260830-bug-diagnosis-flow-590d6e65`.
- `bug-assessment/v1` schema SHA-256: `a61608a17930c5f747bd986f709b54d8d3c6f5e8a3be2b1e591bd6b2094a0134`.
- Owner validator and skill quick validation: Pass; owner schema／mutation／forward-fixture tests: **14/14 Pass**.
- Deterministic fixtures cover legal-ID collision allocation, create-only writes, confirmed／likely／not-a-bug dispositions, one-variable hypotheses, Markdown hash binding and both known-value and credential-shaped secret rejection.
- Forward cases are contract fixtures, not an unrecorded live-agent claim. Fresh read-only Reviewer: pending.
- Owner corpus excluding this report and caches: **9 files, 54,080 bytes, SHA-256 `ca8dd6bcc1a6cfcdaade54bd15142113cc8d813a34bc30af6b5bb5067c5db393`** under the sorted `relative-path<TAB>byte-count<TAB>file-sha256<LF>` manifest.

### Findings-first correction before re-review

The first fresh review returned `CHANGES_REQUIRED`; among its findings, the delivery consumer had not forwarded in-memory `known_secret_values` into assessment materialization. The public API now forwards exact values, while CLI callers provide only repeatable `--known-secret-env` names; neither names nor values enter the record. The corrected diagnosis corpus is **9 files, 54,179 bytes, SHA-256 `eabb68b5f015dc0fccd1bd09bd216542cbcb86e496aac4a0b8479a8a68199668`**. Re-review remains pending and is not a Pass.

### Final fresh review closure

The corrected integrated candidate received implementation `APPROVED` and BUG contract `PASS` from a fresh, read-only Reviewer that did not use behavior reports as an oracle. No diagnosis finding remained. Owner validator, quick validation and all **14/14** diagnosis fixtures passed; exact-value scanning is exercised both by the owner fixture and by the Delivery consumer fixture. Final report-excluding owner corpus remains **9 files, 54,179 bytes, SHA-256 `eabb68b5f015dc0fccd1bd09bd216542cbcb86e496aac4a0b8479a8a68199668`**.

## 2026-08-31 — Plan revision 3 superseding evidence capture

- Owner validator and skill quick validation: **Pass**; current diagnosis suite: **19/19 Pass**.
- The integrated author run passed **91/91** tests: diagnosis 19, Requirements 8, Technical Planning 7, Implementation 14 and Delivery safety／worktree／transition 43. Five owner validators and five skill quick validations also passed; `git diff --check` reported no error.
- Raw assessment JSON is scanned before parsing, duplicate object keys are rejected, and error text does not reproduce the known-value test marker. The persisted Delivery consumer exercises the same raw-byte contract.
- Report-excluding owner corpus: **9 files, 75,740 bytes, SHA-256 `1feecb4995e9212ee78c0dba6a35b8512fe07f2370e5acb55d4c2065521283f3`** under the sorted `relative-path<TAB>byte-count<TAB>file-sha256<LF>` manifest.
- A fresh read-only Reviewer independently passed 5/5 owner validators plus diagnosis 19/19, Implementation 14/14, Delivery mutations 20/20, BUG overlay 14/14 and terminal 8/8. Its only blocking observation was this report's stale `Not run`／14-case header; no implementation finding remained. This entry and the header correct that report-only inconsistency. The subsequent report-only attestation will be persisted in the formal implementation Ledger and is not preclaimed here.

## 2026-09-01 — POSIX ordinary-path classification correction

- Linux full verification reproduced two owner failures: an ordinary POSIX directory was classified as a symlink／reparse point, which also suppressed the smallest-revision diagnostic. A single-variable runtime probe showed that POSIX `lstat()` lacks the Windows-only `st_file_attributes` member; interpreting only that absent member as zero made both focused cases pass while real symlink rejection remained fail closed.
- The minimal implementation change uses `getattr(..., "st_file_attributes", 0)` and continues treating actual `OSError` as unsafe. No Requirements, Plan, schema, public interface or dependency changed.
- Author verification: skill quick validation **Pass**; owner validator **Pass**; Windows diagnosis suite **19/19 Pass**; native Linux diagnosis suite **19/19 Pass**; `git diff --check` **Pass**. The project WP-003 rerun also passed BDD discovery 17/17, TDD workflow 14/14, promotion BDD 3/3, delivery BDD 4/4, full BDD 17/17 and the related suite with all eight selected commands at exit 0.
- A fresh independent read-only Reviewer did not use this report as an oracle and returned `APPROVED` with no findings. It independently passed quick validation, owner validation, EVAL-BUG-001..008 inventory and diagnosis 19/19; its ordinary-path, missing-path and inspection-failure probes confirmed that absent platform metadata is safe while inspection errors remain fail closed. Native Linux was covered by the author run, not preclaimed by that Reviewer.
- Report-excluding owner corpus: **9 files, 77,677 bytes, SHA-256 `41937201045420f90986d9ab5338cc80931c86dcd961f775fddb1cf88c4289f9`** under the sorted `relative-path<TAB>byte-count<TAB>file-sha256<LF>` manifest. The formal implementation review will include this report-only update in its own product snapshot.
