# Workflow examples

Read the relevant case when stage selection, scope or recovery is ambiguous. These are
decision examples; actual Work IDs, digests, raw outputs and human responses come from the run.

## New feature

Request: 「用 Megin 幫訂單 API 加入折扣，還不確定可否與優惠券併用。」

Select Repo/Group, inspect current behavior read-only, then ask the prerequisite-ready
product question under the requirements protocol. Keep `requirements / awaiting_user` while
stacking behavior is unresolved. Stable REQs precede architecture; a fully bound plan and
literal human approval precede claim/prepare and the first product write.

Completion of requirements means observable scope and acceptance are settled, not that
an implementation was proposed or files were already changed.

## Diagnosis only

Request during Megin work: 「解釋重送為何產生重複訂單，先不要修。」

Trace the symptom with a focused check and current source. Report observed command/output,
supported cause, affected behavior and regression scenario; mark unavailable reproduction
as a gap. End with the diagnosis. A later repair request enters requirements → architecture
→ exact-plan approval; the diagnosis itself supplies no product-write approval.

## Unchanged Group consumer

Request: 「只修改 orders-api 的事件金額單位，invoice-worker 不需要改。」

Group discovery still inventories every valid direct-child Repo. Pin source and trace
the producer, unchanged consumer and indirect consumers through aliases/registrations.
Architecture classifies every candidate; affected unchanged peers enter
`verification_repositories` with compatibility checks. Only approved modification Repos
get feature branches. Actual-diff confirmation replays searches on implemented bytes.
Unknown necessary consumer behavior prevents a completed impact claim.

## Interrupted implementation

Request: 「繼續 work-20261015-discount，已做一半。」

Inspect its existing schema/phase, approvals, fingerprint, branches, locks and attempts.
Resume the earliest incomplete action with the same root/Work ID/writer; use `check` for
existing feature branches rather than repeating preparation. Preserve unrelated dirty
files. Baseline/scope/fingerprint drift requires renewed planning, not recreated branches
or reset history.

## Reviewer unavailable or correction cap exhausted

The writer has passing tests but no separate review context: retain the frozen snapshot,
set `awaiting_review` and wait. The writer cannot supply `APPROVED`.

After round 0 and failed corrections 1–3, leave the work incomplete with attempts and
locks retained. Resume does not create a new round 0. A structural gate pass never replaces
an independent review or clears this cap.

## Acceptance and partial delivery

Passing automated checks lead to a human demonstration of the exact Work ID/version/snapshot,
operations and expected results. Save the actual response; without acceptance, staging and
commits remain pending.

If Repo A committed but Repo B failed, preserve A's accepted commit and locks, then resume
`deliver` for missing commits. It verifies retained trees/remote masters and can recover a
commit-before-record crash. Drift requires renewed approvals/evidence. Completion leaves
all accepted Repos on feature branches, with no implicit push, merge, MR or deployment.
