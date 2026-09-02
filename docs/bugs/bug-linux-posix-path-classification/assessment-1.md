# BUG Assessment：bug-linux-posix-path-classification

- BUG ID：`bug-linux-posix-path-classification`
- Revision：1
- Verdict：`confirmed`
- Severity：`medium`
- Relation：`current-scope`
- Source Work：`work-20260831-project-knowledge-system-19202d78`
- Disposition：`current-run`

## Observed／Expected／Impact

- Observed：Linux 上 BUG owner 的 19 個 contract tests 固定有 2 個失敗；一般現存目錄會被 `_is_reparse_path` 判為 redirect，並短路最小 assessment revision 檢查。
- Expected：一般 POSIX 目錄不得被判為 symlink／reparse point；真實 symlink 仍須 fail closed，最小可用 revision 必須被檢查。
- Impact：阻斷本次已核准的 Linux 完整測試與 release gate；不影響已通過的 Windows 執行結果。
- Symptom oracle：同一 Linux owner command 必須 19/19 通過，且普通目錄的 `_is_reparse_path` 結果為 false、真實 symlink 為 true。

## Reproduction／Amplification

- Status：`reproduced`
- 最小步驟：在 Linux 執行 BUG owner contract tests；另對普通 temporary directory 呼叫 `_is_reparse_path` 與 revision 7 的 `create_only_errors`。
- 固定條件與樣本：Python 3.12.3、POSIX、同一 source snapshot；完整測試 1/1 次重現，兩個 focused tests 1/1 次重現。
- Evidence refs：`host-temp:evidence/bug-linux-posix-path-classification-diagnosis.json`

## Compare／Trace

- 最近正常／目前異常：Windows full suite 通過；Linux full suite 的 BUG owner 只有兩個 ordinary-path/revision cases 失敗。Validator 與 tests 的 Git blob 均與 HEAD 相同，證明缺陷早於本次 diff，但本次 Linux release contract 使其成為 current-scope blocker。
- 最小案例：普通 temporary directory 不是 symlink，Linux `lstat()` 不提供 `st_file_attributes`，原函式仍回傳 true。
- Data／control flow：`_is_reparse_path` 讀取不存在的 POSIX member → `AttributeError` 與 `OSError` 共用 fail-closed 分支 → ordinary path 被判為 redirect → normal binding 報錯且最小 revision 分支被抑制。

## Hypotheses

根因已由單一變因 pre/post probe 確認，無開放假設。

## Root cause confidence

- Status：`confirmed`
- Confidence：`high`
- Summary：POSIX 缺少 Windows-only `st_file_attributes` 是第一個破裂 invariant；在不改檔案的執行期 probe 中，僅將缺少該 member 解讀為零，即同時恢復正確 revision 診斷並讓兩個原失敗測試通過。
- Evidence refs：`host-temp:evidence/bug-linux-posix-path-classification-diagnosis.json`

## Risks／Safety

- Security／privacy／data risk：否
- Redacted summary：不適用
- Secure evidence refs：無
- Named human reviewer：無

## Disposition 與下一步

- Disposition：`current-run`；已核准 NFR-002／AC-016 與 full verification 要求 Linux 通過，且最小修正不改 Requirements、Plan、公開介面、依賴或 contract。
- Next falsifiable action／owner：Implementation executor 轉入 Fixing，使 WP-003 與 downstream WP-004 失效，先保存 regression red，再只修正 POSIX attribute 分類，重跑 owner、Windows／Linux full verification 與 fresh reviews。
- 禁止聲明：尚未修復；不得自動建立 Work／issue／commit／push／merge／deploy／通知。

