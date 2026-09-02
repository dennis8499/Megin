# BUG Assessment：bug-knowledge-apply-commit-boundary-toctou

- BUG ID：`bug-knowledge-apply-commit-boundary-toctou`
- Revision：1
- Verdict：`confirmed`
- Severity：`critical`
- Relation：`current-scope`
- Source Work：`work-20260831-project-knowledge-system-19202d78`
- Disposition：`current-run`

## Observed／Expected／Impact

- Observed：`apply_candidate` 的最後 preimage check 返回後、`os.replace` 執行前若出現 create 或 update 競爭內容，競爭內容會被覆蓋，apply 仍回成功並建立 Ready receipt。
- Expected：commit boundary 必須提供真正的 create-only／compare-and-swap 語義；競爭內容出現時回 `PREIMAGE_DRIFT`、保留其位元組、零 receipt 且零部分提交。
- Impact：未經核准的外部或並行 repository state 可能永久遺失，破壞 AC-013、BDD-013 與可重試交易保證。
- Symptom oracle：final check 後注入的 competitor bytes 必須保持完全相同，且 promotion receipt 不存在。

## Reproduction／Amplification

- Status：`reproduced`
- 最小步驟：分別封存一個 create 與 update Candidate，在每個 operation 的最後 preimage check 返回後立即寫入 competitor，再繼續 apply。
- 結果：修正前 Windows governance 16 tests 中只有兩個新案例失敗，兩者皆因預期 `KnowledgeError` 但 apply 成功；fresh reviewer 的 Windows／Linux probe 亦回 `concurrent_bytes_preserved=false`、`receipt_count=1`。
- Evidence refs：`host-temp:commands/preliminary-r2-fresh-retry-fixing/windows-WP-002-red.txt`、`host-temp:reviews/preliminary-r2-fresh-retry/outputs/06-apply-commit-boundary-toctou-windows.json`、`host-temp:reviews/preliminary-r2-fresh-retry/outputs/07-apply-commit-boundary-toctou-linux.json`

## Compare／Trace

- Preimage validation與 Candidate/postimage 驗證均已通過；缺口只存在於最後 check 與 replace 之間。
- 既有測試把競爭寫入安排在 per-operation check 之前，未覆蓋真正 check/use gap。
- 根因可由相同 fixture 在 Windows 與 Linux 重現，並非平台或沙箱差異。

## Hypotheses

根因已由 fresh reviewer 精確 probe 與兩個 deterministic red tests 交叉確認，無開放假設。

## Root cause confidence

- Status：`confirmed`
- Confidence：`high`
- Summary：apply 以可覆寫的 `os.replace` 執行提交，而最後 preimage check 與該系統呼叫不是單一原子條件操作。

## Risks／Safety

- Security／privacy／data risk：否（僅使用隔離、非敏感 repository fixture；風險屬 repository integrity）。
- Redacted summary：不適用。
- Secure evidence refs：無。
- Named human reviewer：無。

## Disposition 與下一步

- Disposition：`current-run`；直接屬於 WP-002／BDD-013／TEST-013／AC-013。
- Next falsifiable action／owner：Implementation executor 以原子 no-replace ownership transfer 實作 create／update commit，安全 rollback 只處理本次擁有的位元組，並重跑 Windows／Linux focused、full 與 fresh review。
- 禁止聲明：尚未完成 fresh review；不得自動 commit／push／merge／deploy。
