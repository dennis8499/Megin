# Historical single-Repo delivery receipts

After the completion gate passes and `workflow.md` records `status: complete`,
export `megin-repo-delivery-receipt/v1`:

```text
python .agents/skills/megin/scripts/delivery_receipt.py --repo <Repo> --work-id <Work ID>
python .agents/skills/megin/scripts/delivery_receipt.py --repo <Repo> --work-id <Work ID> --output <Repo>/docs/work/<Work ID>/evidence/receipt.json
```

Without `--output`, JSON goes to stdout. To archive it, predeclare the exact
`docs/work/<Work ID>/evidence/receipt.json` in the approved `process_records`.
Only that path is writable; aliases, links and other evidence files are rejected.
An identical repeated export succeeds. A different existing receipt is preserved
and export fails.

The receipt binds Work ID, plan version, accepted snapshot, base/feature/merge
commits, delivered tree, fixed inputs and the hashes of the protected plan and
raw verification, review, acceptance and delivery records. Export revalidates
their proof and the original feature/merge ancestry. Native acceptance requires
a human; delegated simulation acceptance belongs to the Workspace distribution.

Historical validation uses the delivered Git objects and original records.
Later product edits, Skills upgrades, branch advances and remote changes do not
invalidate the historical receipt. Preserve the Git objects and protected Work
records: changed plans, raw logs, false gates or missing objects still fail.
Live delivery and completion retain their current snapshot and branch checks.

MergeReviewer can consume the receipt with its optional `--megin-receipt` for a
committed review whose head is exactly the receipt's feature or merge commit.
It validates the receipt independently and includes the identity and digest in
the context and report. A receipt proves the recorded local delivery; it does
not assert remote publication or MR merge.
