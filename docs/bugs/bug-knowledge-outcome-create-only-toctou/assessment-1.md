# BUG Assessment：bug-knowledge-outcome-create-only-toctou

- BUG ID：`bug-knowledge-outcome-create-only-toctou`
- Revision：1
- Verdict：`confirmed`
- Severity：`high`
- Relation：`current-scope`
- Source Work：`work-20260831-project-knowledge-system-19202d78`
- Disposition：`current-run`

## Observed／Expected／Impact

- Observed：`_write_pair_create_only` 在整組 exists check 後逐一 `os.replace`；第二個 target 若於提交邊界被競爭者建立會遭覆蓋，失敗 rollback 也會無條件刪除已被第三方改寫的第一個 target。
- Expected：preliminary review outputs/report 與 Outcome Markdown/JSON 必須原子 create-only；碰撞回 `PRELIMINARY_REVIEW_EXISTS` 或 `OUTCOME_EXISTS`，保留所有 competitor bytes，rollback 只移除仍由本次寫入擁有的內容。
- Impact：審查原始證據或 implementation Outcome 可被靜默覆蓋，create-only revision history 與稽核鏈不再可信。
- Symptom oracle：第二個 target 的 competitor 與第一個 target 的獨立後寫內容均保持 byte-identical，且呼叫回正確 collision code。

## Reproduction／Amplification

- Status：`reproduced`
- 最小步驟：以兩個不存在的 pair targets 開始；第一個 publish 後獨立改寫它，第二個 publish 前建立 competitor，分別使用 Outcome 與 preliminary review collision code。
- 結果：修正前 Windows workflow 22 tests 中只有兩個新 subtests 失敗，皆因預期 `KnowledgeError` 但 pair writer 成功；fresh reviewer probe 亦回 `competitor_bytes_preserved=false`。
- Evidence refs：`host-temp:commands/preliminary-r2-fresh-retry-fixing/windows-WP-003-red.txt`、`host-temp:reviews/preliminary-r2-fresh-retry/outputs/08-outcome-create-only-toctou-windows.json`

## Compare／Trace

- Report／Outcome schema、Ready binding 與 secret scan 均在寫入前通過；缺口只在 create-only persistence primitive。
- 一次性 exists precheck 無法保證後續多個 `os.replace` 的目的端仍不存在。
- 無條件 `unlink` committed target 另形成 rollback check/use 缺口，會刪除獨立狀態。

## Hypotheses

根因已由 fresh reviewer probe 與雙 collision-code deterministic red test 確認，無開放假設。

## Root cause confidence

- Status：`confirmed`
- Confidence：`high`
- Summary：pair writer 以非原子的 exists-check／replace 實作 create-only，且 rollback 未先取得並驗證本次寫入 ownership。

## Risks／Safety

- Security／privacy／data risk：否（fixture 不含敏感資料；風險屬 evidence 與 repository integrity）。
- Redacted summary：不適用。
- Secure evidence refs：無。
- Named human reviewer：無。

## Disposition 與下一步

- Disposition：`current-run`；直接屬於 WP-003／BDD-008／TEST-008。
- Next falsifiable action／owner：Implementation executor 使用 Windows／Linux 原子 no-replace file publish，rollback 先原子移走 current name 並只刪除可證明屬於本次 writer 的位元組，再重跑 workflow、full 與 fresh review。
- 禁止聲明：尚未完成 fresh review；不得自動 commit／push／merge／deploy。
