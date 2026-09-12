# BUG Closure Policy v2

This policy is a status and evidence overlay for existing `bug-assessment/v1`
and `bug-verification/v1` records. It does not rewrite either contract or turn
an assessment into a product conclusion.

## Separate evidence from disposition

`verification.result` records the independently validated result of the
existing verification contract: `verified`, `partial`, or `failed`. The
`current_disposition` is the current operational decision for one BUG. A
missing verification record, an inconclusive original symptom, or a `partial`
verification can never be inferred as `fixed-verified`.

The only terminal dispositions are `fixed-verified` and `rejected`. The
following dispositions remain unresolved and must appear in the report:

- `confirmed-open`: the current version reproduces the original symptom;
- `evidence-pending`: the symptom or required evidence is inconclusive;
- `environment-blocked`: a required platform or tool capability is unavailable;
- `contract-blocked`: an approved contract cannot express the required work;
- `accepted-risk`: a time-bounded risk decision permits operation without a fix;
- `deferred`: work is deliberately scheduled for a later decision.

## Fixed gate

Only `fixed-verified` may use a fixed or resolved closure claim. It requires
all of the following in the same status revision:

1. `verification.result` is `verified` and is bound to a real
   `bug-verification/v1` file;
2. the original symptom is `present` before the fix and `absent` after it;
3. regression evidence contains distinct red and green evidence;
4. every required full-verification command and every required platform passes;
5. an `APPROVED` reviewer has a distinct identity from the implementation
   owner; and
6. no blocker or outstanding risk decision remains.

Proxy evidence, a successful rerun, a single-platform result, or an absent
reviewer is not a fixed gate. The validator fails closed when any item is
missing.

## Blockers, risk and timebox

An environment or contract blocker records its class, missing capability or
gap, owner, due date, alternative, escalation role, release impact, next
action, and evidence references. A blocker does not assert that the product is
fixed or still broken.

`accepted-risk`, `deferred`, and `rejected` carry an explicit decision, owner,
reason, mitigation, impact scope, expiry, reopen condition, next review, and
approval evidence. High and Critical decisions require distinct
`Product/Risk` and `Engineering/Delivery` approvers; the implementation owner
cannot satisfy both roles. An `accepted-risk` disposition also requires an independent reviewer with an `APPROVED` result.

Every record uses the default business-day timebox T0+1 (owner and next
action), T0+3 (blocker classification), T0+5 (escalation), and T0+10 (a
concrete decision). A later approved policy revision may make the SLA
stricter, but a status record may not silently omit a deadline.

## History, scope and reporting

Each BUG has an append-only `status-N.json` chain. `previous.path` and
`previous.sha256` must identify the immediately preceding revision. A common
work scope may name several BUGs, but every BUG keeps its own assessment,
verification, disposition, owner, next action, platform evidence, and history.
One BUG passing must not cover another BUG.

Reports are read-only projections. They count all unresolved dispositions,
separate verification results from dispositions, and preserve every evidence
manifest entry. Formal performance outliers, failed output, recovery material,
and reviewer identity evidence are never removed or replaced by a later
successful run.

Windows and Linux are separate release obligations. A single platform result
is platform-limited evidence, not an unconditional cross-platform closure.

The policy uses the existing file-first Human Gate and exact identity. It adds
no third approval Gate, and `bug_status.py` has no create, update, apply, or
overwrite command.
