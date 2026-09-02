# BUG Assessment：bug-knowledge-apply-concurrent-state-loss

- BUG ID：`bug-knowledge-apply-concurrent-state-loss`
- Revision：1
- Verdict：`confirmed`
- Severity：`high`
- Relation：`current-scope`
- Source Work：`work-20260831-project-knowledge-system-19202d78`
- Disposition：`current-run`

## Observed／Expected／Impact

- Observed：Candidate 已驗證 target preimage 後，另一個狀態可在 replace 前出現；apply 隨後覆蓋它，失敗 rollback 又依舊 preimage 刪除或還原，沒有保留較新的狀態。
- Expected：每一次 commit 與 rollback 都必須以目前 bytes 精確等於已驗證 preimage／本次 postimage 為條件；任何 mismatch 都零覆蓋、零刪除並回傳可恢復衝突。
- Impact：併發或外部寫入的 repository state 可能遺失，違反 AC-013／BDD-013 的 zero-commit 與可重試承諾。
- Symptom oracle：插入的 later state 在 apply 失敗後仍須逐 byte 存在；目前最小案例為不存在。

## Reproduction／Amplification

- Status：`reproduced`
- 最小步驟：在隔離 repository 封存 create Candidate；preimage check 後、第一個 canonical replace 前建立另一份 target bytes，接著觸發既有 after-replace failure boundary。
- 結果：`injected=true`、`result_code=PROMOTION_FAILED`、`later_state_preserved=false`、target 被刪除。
- Evidence refs：`host-temp:evidence/bug-knowledge-apply-concurrent-state-loss-diagnosis.json`

## Compare／Trace

- `_assert_validated_preimages_current` 只在 staging 前批次檢查一次。
- apply loop 的 `os.replace` 沒有逐 operation 條件檢查。
- `_rollback` 對 create 無條件 unlink、對 update 無條件 replace preimage。

## Hypotheses

根因由 deterministic insertion boundary 與 rollback 結果確認，無開放假設。

## Root cause confidence

- Status：`confirmed`
- Confidence：`high`
- Summary：commit 存在 precheck-to-replace gap，rollback 也未確認 current bytes 是否仍屬於本次 apply。

## Risks／Safety

- Security／privacy／data risk：否（重現只使用隔離非敏感 fixture；風險分類為資料完整性）
- Redacted summary：不適用
- Secure evidence refs：無
- Named human reviewer：無

## Disposition 與下一步

- Disposition：`current-run`；直接屬於 WP-002。
- Next falsifiable action／owner：Implementation executor 先加入逐 operation commit mismatch 與 rollback later-state regression red，再實作 conditional commit／rollback，重跑 recovery、BDD-013、Windows/Linux full 與 fresh review。
- 禁止聲明：尚未修復；不得自動 commit／push／merge／deploy。
