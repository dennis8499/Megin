# BUG Assessment：bug-bdd016-warm-query-tail

- BUG ID：`bug-bdd016-warm-query-tail`
- Revision：1
- Verdict：`confirmed`
- Severity：`medium`
- Relation：`current-scope`
- Source Work：`work-20260902-skill-script-performance-0ae7b62a`
- Disposition：`current-run`

## Observed／Expected／Impact

- Observed：WP-001 最終完整 BDD 的 BDD-016 在固定 50,000 files／5,000 pages workload 中，5 次 warm query 有 1 次耗時 2.2362605 秒，功能雜湊仍等於固定 oracle。
- Expected：BDD-016 與 Ready plan 要求每個 warm query 及 index candidate 操作均不超過 2.0 秒，且功能結果保持一致。
- Impact：效能尾端延遲使全量驗證間歇失敗並阻擋 WP-001 完成；不影響輸出正確性，但不能宣告交付完成。
- Symptom oracle：固定 workload 下任一 `durations_seconds.queries` 值大於 2.0 秒即為症狀存在；同時以固定 functional SHA-256 排除功能變更。

## Reproduction／Amplification

- Status：`intermittent`
- 最小步驟：在 Windows worktree 執行完整 BDD，觀察 BDD-016；再於相同 50k/5k fixture 中預熱 5 個 query，量測原樣與僅繞過 pre full staged-inventory scan 的成對查詢。
- 固定條件與樣本：完整 BDD 1 次出現 1/5 warm query 超標；受控診斷包含 5 個 profile 樣本及 10 組成對樣本，單一變因為 `_match_cache_fingerprint` 是否重用已捕獲的穩定值。
- Evidence refs：`commands/sequence/0036-CMD-BDD-FULL-001-WP-001-FINAL.json`、`evidence/WP-001-bdd016-diagnosis.json`。

## Compare／Trace

- 最近正常／目前異常：同一最終實作的 4 個 query 為 1.736–1.852 秒，異常 query 為 2.236 秒；功能雜湊完全相同。
- 最小案例：保留相同 fixture、query、process-local match cache、post dirty validation 與功能投影，只把 pre full staged-inventory scan 替換成已捕獲值。
- Data／control flow：`QuerySearchSession.__init__` 每次 warm query 呼叫 `_match_cache_fingerprint`；該 Git 指令重新輸出 50,000 筆、約 4.17 MB staged inventory，profile 耗時 0.765–0.904 秒，之後 `validate` 又執行 0.689–0.805 秒的 dirty scan。

## Hypotheses

| Rank | ID | Causal statement | Variable | Prediction | Falsifier | Outcome | Evidence |
|---|---|---|---|---|---|---|---|
| 1 | H-001 | 每次 warm query 重做 full staged-inventory scan，吃掉約一半時限並造成 2 秒尾端超標。 | 僅繞過 pre full scan。 | 總耗時顯著下降且功能相同。 | 介入後耗時不降或功能不同。 | `supported` | `evidence/WP-001-bdd016-diagnosis.json` |
| 2 | H-002 | 結果組裝或 citation 驗證是主要瓶頸。 | 保留結果與驗證、只移除 pre scan。 | 若為真，介入後耗時應接近原樣。 | 介入後中位數大幅下降。 | `falsified` | `evidence/WP-001-bdd016-diagnosis.json` |
| 3 | H-003 | index candidate 操作造成 BDD-016 失敗。 | 比較失敗報告中的 query 與 index candidate。 | 若為真，index candidate 應超過 2 秒。 | index candidate 明顯低於 2 秒且超標只出現在 query。 | `falsified` | `commands/sequence/0036-CMD-BDD-FULL-001-WP-001-FINAL.stdout.txt` |

## Root cause confidence

- Status：`confirmed`
- Confidence：`high`
- Summary：受控 probe 將中位數由 1.594 秒降至 0.803 秒、最慢由 1.735 秒降至 1.102 秒，10/10 功能相同；inner regression 先證明 warm path 仍重掃 full inventory，最小修正後轉綠，完整 BDD 18/18 與 full owner suite 17/17 也通過。
- Evidence refs：`evidence/WP-001-bdd016-diagnosis.json`、`commands/sequence/0036-CMD-BDD-FULL-001-WP-001-FINAL.json`、`commands/sequence/0038-CMD-TDD-FOCUSED-001-TEST-018-WARM-SNAPSHOT-RED.json`、`commands/sequence/0039-CMD-TDD-FOCUSED-001-TEST-018-WARM-SNAPSHOT-GREEN.json`、`commands/sequence/0049-CMD-BDD-FULL-001-WP-001-WARM-SNAPSHOT-FINAL.json`、`commands/sequence/0051-CMD-TEST-FULL-001-WP-001-WARM-SNAPSHOT-FINAL.json`。

## Risks／Safety

- Security／privacy／data risk：否
- Redacted summary：不適用
- Secure evidence refs：無
- Named human reviewer：不適用

## Disposition 與下一步

- Disposition：這是目前 WP-001 diff 未能穩定滿足已核准 2 秒驗收條件的 `current-scope` 問題，納入同一 run 修正，不改 Requirements／Plan／contract。
- Next falsifiable action／owner：Implementation writer 保存 WP-001 完成證據，並在 fresh review 前以 create-only 方式 materialize 本 assessment。
- 禁止聲明：診斷 assessment 本身不宣稱整體交付完成；不得自動建立 Work／issue／commit／push／merge／deploy／通知。
