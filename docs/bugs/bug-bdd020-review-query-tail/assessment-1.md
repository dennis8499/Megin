# BUG Assessment：bug-bdd020-review-query-tail — 大型儲存庫查詢尾延遲

- BUG ID：`bug-bdd020-review-query-tail`
- Revision：1
- Verdict：`confirmed`
- Severity：`high`
- Relation：`current-scope`
- Source Work：`work-20260902-skill-script-performance-0ae7b62a`
- Disposition：`current-run`

## Observed／Expected／Impact

- Observed：fresh preliminary reviewer 在固定 50,000 個 tracked files 的 portability workload 中，五個 cold samples 全部超過 2.0 秒，五個 warm samples 中兩個超過 2.0 秒；其餘六個全量命令、functional parity 與 fixture cleanup 均通過。
- Expected：Ready 的 BDD-020、TEST-020 與 CMD-CI-001 要求五個 cold 和五個 warm query samples 每一個都不超過 2.0 秒，結果相同且測試後不殘留 fixture。
- Impact：Windows CI 在相同產品 bytes 上會因正常負載波動穩定或間歇超時，阻擋效能交付；沒有資料正確性、cleanup、安全或隱私失敗。
- Symptom oracle：`durations_seconds.cold_queries` 與 `durations_seconds.queries` 的十個值中任一值大於 `max_operation_seconds == 2.0` 即表示症狀存在。

## Reproduction／Amplification

- Status：`reproduced`
- 最小步驟：在 Windows 建立基準工具定義的 50,000 檔 tracked fixture，對固定 token 執行 fresh cold query 與 same-process warm query，保留每個 query 內部 Git child 的 wall time。
- 固定條件與樣本：reviewer 使用五個 cold 加五個 warm samples；本地因果 probe 固定同一 fixture、stage、query token、產品 revision 與結果 normalization，只改 dirty-inventory Git command topology。
- Evidence refs：`reviews/preliminary-round-1/outputs/001-CMD-CI-001.txt`、`diagnosis/bdd020-review-query-tail/profile.json`、`diagnosis/bdd020-review-query-tail/causal-probe.json`、`diagnosis/bdd020-review-query-tail/budget-probe.json`。

## Compare／Trace

- 最近正常／目前異常：主代理先前樣本約為 cold 1.78–1.82 秒、warm 1.41–1.42 秒；fresh reviewer 在相同 snapshot 下量到 cold 2.19–2.31 秒與兩個 warm 2.00／2.78 秒，證明目前 headroom 無法吸收正常 host load。
- 最小案例：單一 query 的 `git grep --cached` 約 0.16 秒；pre combined `git ls-files --stage -v --modified --deleted --others` 約 0.84 秒，post combined dirty scan 約 0.75–0.83 秒，兩者已占約 1.6 秒。將 pre inventory 拆成 staged 0.07 秒、tracked diff 0.05 秒、untracked 0.09 秒後 cold 為 1.31 秒；只拆 pre/post dirty inventory 時 warm 為 0.45 秒。
- Data／control flow：第一個破裂 invariant 位於 `QuerySearchSession` 的 repository snapshot capture／validate；把 staged inventory 與 working-tree dirty discovery 合併到 `git ls-files` 使 Git 對 50,000 paths 做昂貴掃描兩次，搜尋本身不是主要瓶頸。

## Hypotheses

| Rank | ID | Causal statement | Variable | Prediction | Falsifier | Outcome | Evidence |
|---|---|---|---|---|---|---|---|
| 1 | H-001 | combined `ls-files` fingerprint 的 working-tree 掃描成本造成 2 秒尾延遲。 | 僅替換 dirty-inventory Git command topology。 | pre-only 與 post-only 替換會各自降低對應 cold／warm latency，完整替換保持結果相同並低於 2 秒。 | 替換後 latency 不降、結果漂移，或搜尋程序仍占主要時間。 | `supported` | `diagnosis/bdd020-review-query-tail/causal-probe.json` |
| 2 | H-002 | `git grep --cached` 是主要瓶頸。 | 固定 fingerprint，只觀察搜尋 child wall time。 | 若為真，`git grep` 應占總時間的大多數且拆 fingerprint 不會顯著改善。 | `git grep` 約 0.16 秒且拆 fingerprint 使完整 query 由約 1.97 降至 0.69 秒。 | `falsified` | `diagnosis/bdd020-review-query-tail/profile.json` |
| 3 | H-003 | fixture 建立或 readiness warm-up 被錯誤計入每次 query。 | 只量 query 內部 child calls。 | 若為真，query 內部無兩個大型 fingerprint tail，或移除它們仍超過 2 秒。 | query trace 直接顯示兩次約 0.8 秒 fingerprint，替換後 0.64 秒。 | `falsified` | `diagnosis/bdd020-review-query-tail/budget-probe.json` |

## Root cause confidence

- Status：`confirmed`
- Confidence：`high`
- Summary：受控 probe 只替換 dirty-inventory command topology，即可預期地分別消除 cold 與 warm tail；完整候選以 9 個 child processes 在 0.64 秒完成並保持結果相同。合理替代原因 `git grep` 與 fixture readiness 已由分項 wall time 推翻。
- Evidence refs：`diagnosis/bdd020-review-query-tail/profile.json`、`diagnosis/bdd020-review-query-tail/causal-probe.json`、`diagnosis/bdd020-review-query-tail/budget-probe.json`。

## Risks／Safety

- Security／privacy／data risk：否
- Redacted summary：不適用
- Secure evidence refs：無
- Named human reviewer：不適用

## Disposition 與下一步

- Disposition：此缺陷直接違反目前 Ready 的 BDD-020／TEST-020／CMD-CI-001，且根因與修正 seam 都在已核准的 Project Knowledge query scope，故納入同一 run 的 Fixing。
- Next falsifiable action／owner：implementation writer 先加入 split inventory、drift parity、attribute-path reuse 與 ≤10 child-process regression red，再做單一最小演算法修改並重跑五 cold／五 warm 與全量命令。
- 禁止聲明：尚未修復；不得自動建立 Work／issue／commit／push／merge／deploy／通知。
