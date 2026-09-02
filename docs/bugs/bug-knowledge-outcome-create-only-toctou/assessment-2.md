# BUG Assessment：bug-knowledge-outcome-create-only-toctou

- BUG ID：`bug-knowledge-outcome-create-only-toctou`
- Revision：2
- Verdict：`confirmed`
- Severity：`high`
- Relation：`current-scope`
- Source Work：`work-20260831-project-knowledge-system-19202d78`
- Disposition：`current-run`

## Observed／Expected／Impact

- Observed：revision 1 的 atomic no-replace 修正已保留 byte-different competitor，但 `_rollback_pair_publication` 仍以「目前 bytes 等於本次 payload」推定 ownership。若第一筆在第二筆 collision 前被獨立移除並以相同 bytes 重建，rollback 會刪除這筆獨立內容。
- Expected：preliminary review outputs/report 與 Outcome Markdown/JSON 的 pair publication 必須 create-only；任何第二筆 collision 都只可回滾仍可證明由本次 writer 擁有的第一筆，byte-identical 的獨立 replacement 必須保留。
- Impact：審查或 Outcome 的獨立 create-only entry 可在 rollback 中消失，造成稽核歷史不完整。
- Symptom oracle：兩種 collision code 都回正確 typed error，第二筆 competitor 保留，而且 byte-identical、獨立重建的第一筆仍存在。

## Reproduction／Amplification

- Status：`reproduced`
- 最小步驟：先 publish 第一筆；立即 unlink 並以相同 bytes 獨立重建；在第二筆 publish 前建立 competitor；分別執行 `OUTCOME_EXISTS` 與 `PRELIMINARY_REVIEW_EXISTS`。
- 結果：Windows 與 Linux 各有兩個預期 assertion failure，均指出 `rollback deleted the independent first entry`；fresh R3 probe 也在兩個平台回報 `first_exists_after_rollback=false`。
- Evidence refs：`host-temp:commands/preliminary-r3-fixing/windows-WP-003-red-retry-2.json`、`host-temp:commands/preliminary-r3-fixing/linux-WP-003-red.json`、`host-temp:reviews/preliminary-r3-fresh/outputs/06-outcome-identical-owner-windows.observation.json`、`host-temp:reviews/preliminary-r3-fresh/outputs/07-outcome-identical-owner-linux.observation.json`

## Compare／Trace

- Pair 的原子 no-replace publish 與 typed collision 已成立，缺口只在第一筆 rollback 的 ownership oracle。
- `_rollback_pair_publication` 先把目前 target 原子移到 retirement path，再以 bytes equality 判斷是否刪除；相同 bytes 無法區分原 writer inode 與獨立 replacement。
- 根因直接屬於 WP-003／BDD-008／TEST-008，不需要變更 Ready scope 或介面。

## Hypotheses

根因已由 Windows／Linux reviewer probe 與 deterministic red tests 確認，無開放假設。

## Root cause confidence

- Status：`confirmed`
- Confidence：`high`
- Summary：pair rollback 把 payload byte equality 當成 writer ownership，因而刪除 byte-identical 的獨立 directory entry。

## Risks／Safety

- Security／privacy／data risk：否（fixture 不含敏感資料；風險屬 evidence 與 repository integrity）。
- Redacted summary：不適用。
- Secure evidence refs：無。
- Named human reviewer：無。

## Disposition 與下一步

- Disposition：`current-run`。
- Next falsifiable action／owner：Implementation executor 在 publish 前保存不可由相同 bytes 偽造的檔案 identity，rollback 僅移除 identity 與 bytes 都仍屬本次 publication 的 target；再重跑同一 Windows／Linux regression、完整驗證與 fresh review。
- 禁止聲明：尚未完成 green 與 fresh review；不得自動 commit／push／merge／deploy。
