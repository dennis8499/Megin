# BUG Assessment：bug-knowledge-promotion-retirement-read-failure

- BUG ID：`bug-knowledge-promotion-retirement-read-failure`
- Revision：1
- Verdict：`confirmed`
- Severity：`high`
- Relation：`current-scope`
- Source Work：`work-20260831-project-knowledge-system-19202d78`
- Disposition：`current-run`

## Observed／Expected／Impact

- Observed：update commit 先把 validated preimage 移到 `commit-boundary` retirement path，再讀取 retired bytes。該 read 發生 I/O fault 時，helper 尚未回傳，所以 caller 的 `applied` 不含此 operation；一般 rollback 只清 staging、把 journal 標成 `rolled_back`，canonical target 卻保持缺失。
- Expected：target retirement 後、Candidate publish 前的任何失敗，都必須把 approved preimage 恢復到 canonical target；若因 competitor 無法恢復，transaction 必須保持 recovery-required，不得宣稱 rolled back。
- Impact：已核准知識頁可能從 canonical repository tree 消失，只剩 registry 內的 retirement bytes，且 journal 狀態錯誤地表示回滾完成。
- Symptom oracle：injected retirement read fault 回 typed recoverable failure，canonical target 仍是原 approved bytes、無 Ready receipt、journal 為真正 rolled back，且沒有 stranded retirement preimage。

## Reproduction／Amplification

- Status：`reproduced`
- 最小步驟：建立一個 update Candidate；在 `_rename_create_only(target, retired)` 成功後，讓第一次 `retired.read_bytes()` 拋出 `OSError`；等待 `apply_candidate` caller rollback 完成後檢查 target、journal 與 retirement path。
- 結果：Windows 與 Linux 各有一個預期 assertion failure，均指出 `rollback left the approved target missing`；fresh R3 probe 在兩平台均回報 `target_exists_after_caller_rollback=false` 且 retirement count 為 1。
- Evidence refs：`host-temp:commands/preliminary-r3-fixing/windows-WP-002-red-retry-2.json`、`host-temp:commands/preliminary-r3-fixing/linux-WP-002-red.json`、`host-temp:reviews/preliminary-r3-fresh/outputs/08-promotion-retirement-windows.observation.json`、`host-temp:reviews/preliminary-r3-fresh/outputs/09-promotion-retirement-linux.observation.json`

## Compare／Trace

- Final preimage check 與 atomic retirement 已成立；缺口只在 retirement 成功後到 helper 回傳前的 exception safety。
- `_publish_operation_at_commit_boundary` 沒有包住 retired read 的 restore guard；`apply_candidate` 又只在 helper 成功後 append `applied`，因此 caller rollback 看不到已被退休的 target。
- 根因直接屬於 WP-002／BDD-013／TEST-013，不需要變更 Ready scope 或介面。

## Hypotheses

根因已由 Windows／Linux reviewer probe 與 deterministic red tests 確認，無開放假設。

## Root cause confidence

- Status：`confirmed`
- Confidence：`high`
- Summary：update preimage retirement 與 subsequent read 之間沒有 exception-safe restore，且 caller 的 rollback tracking 只在 helper 成功後才登記 operation。

## Risks／Safety

- Security／privacy／data risk：否（fixture 不含敏感資料；風險屬 repository data integrity）。
- Redacted summary：不適用。
- Secure evidence refs：無。
- Named human reviewer：無。

## Disposition 與下一步

- Disposition：`current-run`。
- Next falsifiable action／owner：Implementation executor 對 retirement 後的所有 failure path 執行 restore；restore collision 時保留 retirement bytes 與 in-progress journal 並回 `RECOVERY_REQUIRED`，再重跑同一 Windows／Linux regression、完整驗證與 fresh review。
- 禁止聲明：尚未完成 green 與 fresh review；不得自動 commit／push／merge／deploy。
