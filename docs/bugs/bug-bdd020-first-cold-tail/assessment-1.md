# BUG Assessment：bug-bdd020-first-cold-tail

- BUG ID：`bug-bdd020-first-cold-tail`
- Revision：1
- Verdict：`confirmed`
- Severity：`medium`
- Relation：`current-scope`
- Source Work：`work-20260902-skill-script-performance-0ae7b62a`
- Disposition：`current-run`

## Observed／Expected／Impact

- Observed：最終完整 BDD 的 BDD-020 在 250 files／20 pages 縮小 workload 中，第一個 fresh-process cold query 為 2.1603529 秒，後四個僅 0.2581294–0.2928059 秒；功能與 cold／warm hashes 仍相同。
- Expected：五個計時的 fresh-process cold samples 與五個 warm samples 均不超過 2.0 秒，功能 hash 相同，fixture 完整清除。
- Impact：一次性工具／檔案系統 readiness 成本被混入第一個計時樣本，會讓全量驗證間歇失敗；功能正確性與 fixture cleanup 不受影響。
- Symptom oracle：任何 `durations_seconds.cold_queries` 值超過 2.0 秒即為症狀存在；同時用固定 functional hash 與 fixture absence 排除功能或清理錯誤。

## Reproduction／Amplification

- Status：`intermittent`
- 最小步驟：執行 Project Knowledge full BDD；觀察 BDD-020 的五個 cold samples。再以相同 250/20 workload 重複 10 次，並做 6 組交錯次序的 control／單一 untimed fresh-process preflight paired probe。
- 固定條件與樣本：full BDD 出現 1 次第一 cold sample 超標；10 次相同重複未再超標，但每輪第一 sample 都比後四筆慢；paired probe 只改變「計時前是否先執行一次獨立 fresh-process query」。
- Evidence refs：`commands/sequence/0116-CMD-BDD-FULL-001-FINAL-CURRENT-BYTES.json`、`diagnosis/bdd020-cold-start-tail/repeat-summary.json`、`diagnosis/bdd020-cold-start-tail/paired-preflight.stdout.json`。

## Compare／Trace

- 最近正常／目前異常：同一失敗報告的第一 cold query 為 2.1603529 秒，後四筆為 0.2581294–0.2928059 秒；正式 50k/5k benchmark 的五筆 cold query 為 1.7740888–1.7945034 秒且全數通過。
- 最小案例：不改 fixture、query、functional oracle、fresh-process 邊界或 2 秒門檻，只在五筆計時前加入一個丟棄結果的不計時 fresh-process readiness probe。
- Data／control flow：`run_benchmark` 建好全新 fixture 後立即把第一個 `_cold_query` 納入計時；一次性的 Python／Git／repository metadata readiness 成本因此進入 sample，而非被 measurement setup 隔離。

## Hypotheses

| Rank | ID | Causal statement | Variable | Prediction | Falsifier | Outcome | Evidence |
|---|---|---|---|---|---|---|---|
| 1 | H-001 | 第一個 fresh process 同時承擔一次性工具與 repository readiness 成本，造成尾延遲污染五個計時樣本。 | 計時前只增加一個不計時的獨立 fresh-process query。 | 第一個計時 sample 顯著下降，五個計時 samples 與功能結果維持不變。 | paired probe 無一致改善或功能結果改變。 | `supported` | `diagnosis/bdd020-cold-start-tail/paired-preflight.stdout.json` |
| 2 | H-002 | 五個 fresh-process queries 的穩態演算法本身超過 2 秒。 | 比較第一筆與後四筆、以及正式 50k/5k 五筆。 | 若為真，多筆或中位數應持續超標。 | 後四筆、10 次重複與正式 benchmark 全部低於 2 秒。 | `falsified` | `commands/sequence/0113-CMD-CI-001-FINAL-CURRENT-BYTES.stdout.txt`、`diagnosis/bdd020-cold-start-tail/repeat-summary.json` |
| 3 | H-003 | 功能 hash 不一致或 fixture cleanup 失敗導致 BDD-020 red。 | 檢查失敗報告的 hashes 與命令後 fixture existence。 | 若為真，hash 不同或 fixture 殘留。 | hashes 相同且 fixture 不存在。 | `falsified` | `commands/sequence/0116-CMD-BDD-FULL-001-FINAL-CURRENT-BYTES.json`、`commands/sequence/0116-CMD-BDD-FULL-001-FINAL-CURRENT-BYTES.stdout.txt` |

## Root cause confidence

- Status：`confirmed`
- Confidence：`high`
- Summary：6/6 交錯 paired probes 都讓第一個計時 cold sample 下降；control 中位數 0.52843495 秒，preflight 中位數 0.26636865 秒，降低 49.59%，且全部功能 outcome 通過。這個受控單變因介入證明取樣順序把一次性 readiness 成本混入第一筆。
- Evidence refs：`diagnosis/bdd020-cold-start-tail/paired-preflight-command.json`、`diagnosis/bdd020-cold-start-tail/paired-preflight.stdout.json`。

## Risks／Safety

- Security／privacy／data risk：否
- Redacted summary：不適用
- Secure evidence refs：無
- Named human reviewer：不適用

## Disposition 與下一步

- Disposition：這是目前 WP-003 新增 cold benchmark 的 `current-scope` 測量缺陷；在同一 run 加入不計時但仍為獨立 process 的 readiness probe，不放寬 2 秒契約、不改五筆計時樣本與功能 oracle。
- Next falsifiable action／owner：Implementation writer 先新增 regression red，要求 `_cold_query` 共呼叫六次但 report 只保存五筆計時 samples；再做最小實作並重跑 focused、full 與 fresh review。
- 禁止聲明：assessment 尚未宣稱已修復；不得自動建立 Work／issue／commit／push／merge／deploy／通知。
