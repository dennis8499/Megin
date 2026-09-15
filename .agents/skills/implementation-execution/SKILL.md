---
name: implementation-execution
description: 執行由 Delivery Orchestrator 路由且已核准的 ready-plan/v1，或 portable `delivery-run/v2` dispatch：依 WP 進行 outside-in BDD／inner TDD、全量驗證與 fresh 唯讀 review。適用於開始或續跑 governed implementation；規劃、需求探索、未核准計畫與單純審查不適用。
---

<!-- authority: implementation-entrypoint -->

# 實作執行

把 Ready plan 或 v2 dispatch package 收斂為可重現的產品 diff、Ledger 與獨立審查證據。v1 的主代理是唯一 writer；v2 則由一名 current authorization 綁定的 implementation writer 執行，writer 可以是受監督的 subagent。兩條路徑的每輪 Reviewer 都是 fresh、唯讀且不再委派。

## 呼叫邊界

| 輸入 | 路由 |
|---|---|
| Exact `implementation/active` `delivery-run/v1` 與 Ready ready-plan/v1，開始或續跑標準實作 | 本 Skill |
| Exact `implementation/active` BUG `delivery-run/v1`、Ready plan 與已核准 assessment | 本 Skill 的 BUG overlay |
| portable `delivery-run/v2` implementation dispatch（`small`、`large` 或已完成 diagnosis 的 bug） | 依 [v2 派工、審查與交付收尾契約](references/v2-dispatch-and-finish.md) 取得 writer assignment，循序實作並交給 fresh Reviewer |
| Ready plan 或歷史 standalone Ledger，但沒有 exact active delivery | 交給 Delivery Orchestrator 建立或續接 context；只可唯讀檢查舊 bytes |
| 未核准／無版本 plan，或需要規劃 | Technical Planning |
| 需求仍待探索 | Requirements Discovery |
| 只要求唯讀審查 | Review workflow |

完成條件：輸入唯一落在一列；v1 只有前兩列可在階段授權與 Preflight 都通過後取得產品寫入權，第二列另受 BUG overlay 約束。v2 必須有 exact dispatch authorization 與單一 writer assignment；沒有 assignment 或 reviewer capability 時保持零產品 mutation。

## v2 可組合方法

v2 plugin 將本 Skill 的執行責任拆成可組合的方法；本 Skill 仍是 implementation
dispatch 與結果整合的 owner：

| 方法 | 責任 |
|---|---|
| `test-driven-development` | outside-in BDD、inner TDD 與每個 slice 的 red／green evidence |
| `code-review` | fresh、read-only Reviewer、scope／quality findings 與修正複查 |
| `verification-before-completion` | focused／related／full commands、證據新鮮度、snapshot 與完成判定 |
| `finishing-delivery` | approved scope 的 knowledge review、commit／push／draft PR handoff 與可續跑 publication state |

方法只能被 current v2 assignment 或 v1 階段授權載入；方法本身不授予 writer、phase
transition 或 Git finish 權限，也不能另開第二條 mutation path。

## 不變量

- Ready bundle、sources、delivery requirements 與治理唯讀。
- 寫入集合精確等於 plan 明列的產品、測試與 test-only 設定；秘密、無關檔案與未授權外部狀態不變。
- v1 嚴禁 stage、commit、push、merge、deploy、建立 ticket、cleanup 或刪除 worktree；v2 的 Git stage／commit／push／draft PR 只可由 approved `finish` handoff 執行。
- Fresh Reviewer capability 不可用時為 Blocked；Reviewer 只核准固定 snapshot，Complete 後 run 凍結。
- BUG assessment 只是診斷 evidence；Requirements 仍唯一擁有 WHAT，Ready plan 仍唯一擁有 HOW。不得在實作期改寫它們來合理化 patch。
- v2 同一 worktree 同一時間最多一名 writer；subagent writer 不可平行執行、再委派或擴大 allowed paths。Controller 保存 assignment／result，Reviewer 必須是不同 fresh、read-only session。
- v2 knowledge review 只處理 approval payload 明列的 knowledge scope；scope drift、lint／source／snapshot conflict 或 blocking finding 停止在 awaiting／blocked，不自動回寫。

## 0. 取得階段授權

完整讀取 `.agents/skills/delivery-orchestrator/references/stage-authorization.md`。v1 在建立或續寫 execution run、binding、Ledger、evidence、fixture、產品 diff 或外部狀態前執行：

`python -X utf8 -B .agents/skills/delivery-orchestrator/scripts/delivery_workspace.py authorize --repo . --phase implementation [--work-id <work-id>]`

只有 `outcome: authorized` 且 record 精確為 `implementation/active` 才進入 v1 Preflight。`routing_required` 或 typed error 時維持 repository、host-temp 與外部狀態零寫入，交還 `delivery-orchestrator`。Ready plan、使用者直接點名、prompt、路徑或既有 standalone Ledger 都不能代替授權；歷史 standalone Ledger 與 Ready artifacts 僅供唯讀檢查。v2 以 state 的 current dispatch authorization 與 writer assignment 作同等檢查，沒有 assignment 不得寫入。

完成條件：任何 execution mutation 前已有 current Delivery authorization；唯讀 review／治理／測試例外沒有 run、Ledger 或產品 mutation。v2 的 assignment、task class、scope、knowledge 與 finish destination digest 必須與 state 一致。

## 1. Preflight

完整讀取 [Preflight 與 Ledger](references/preflight-and-ledger.md)及必要的 [Orchestrated Delivery](references/orchestrated-delivery.md)。再依實際分支載入：

- 既有 binding 或 Ready/source revision → [Resume 與 Revision](references/resume-and-revision.md)
- 第一個 public seam／entrypoint 不存在 → [Greenfield Bootstrap](references/greenfield-bootstrap.md)

v2 另讀取 [v2 派工、審查與交付收尾契約](references/v2-dispatch-and-finish.md)，驗證 dispatch
package、唯一 writer assignment、allowed path set、test／evidence destination、
knowledge scope 與 finish destination。v2 不要求目標專案載入本 repository 的
`.agents/skills`；portable plugin 會將 runtime state 保存在 repository 外。

Ready binding 通過後、取得產品寫入權前，執行 read-only 知識 preflight：

`python -X utf8 -B .agents/skills/project-knowledge/scripts/knowledge_cli.py query --repo . --stage implementation --query "<目前實作意圖>"`

保存 `knowledge-context/v1` 到 Ledger，並在修改前重讀每個 result 的 `source_refs`。這個步驟不寫回 Wiki 或產品；typed dependency／contract error 為 Blocked。只有本身由 Ready `BOOT-*` 建立 project-knowledge seam 的 run 可使用明列的 bootstrap exception。

Producer 缺口為 Awaiting upstream reapproval；workspace、能力、工具、baseline 或 dirty-state 問題為 Blocked。

完成條件：全部適用契約通過、host-temp Ledger 已保存 evidence，且產品／測試／dependencies／Ready／外部狀態 hashes 與 Preflight 前相同；才進 Executing。

## 2. Executing

完整讀取 [BDD／TDD 執行迴圈](references/bdd-tdd-loop.md)。依 WP DAG 穩定拓撲序執行 public-seam BDD red → inner test red → minimal green → refactor-with-green → BDD／related green。Greenfield red 前的 production shape 只來自已核准 BOOT contract。v2 由 current writer assignment 依相同順序執行；同一 worktree 不平行 dispatch。

完成條件：每個新行為都有時間順序正確的 red／green；一個 WP 的 scenarios、tests、commands、scope 與追溯全通過後才為 Verified；全部 WP Verified 才進 Verifying。

BUG plan 另須先重跑原始症狀 oracle，再取得 regression red；只做一個最小根因修復。診斷失真、修法失敗或影響範圍擴大時立即回 Planning／Requirements，不疊加猜測式 patch。

## 3. Verifying／Reviewing

完整讀取 [Reviewer 契約](references/reviewer-contract.md)。主代理依 Ready validation plan fresh 跑一次全部 logical obligations；經完整 child inventory 證明的 coverage edge 不重複執行相同 physical command，並自動保存原始 evidence bundle。失敗走 Fixing，使 affected WP 與必要 downstream 依序 Invalidated → Executing → Verified。

全量通過後先由 fresh read-only Reviewer 完成六項便宜 precheck；若可審才 fresh 執行一次全量驗證與不含outcome／Candidate binding的preliminary product review。主代理把report與每個raw output create-only保存於current run，並以report logical ref、path與SHA-256建立create-only `implementation-outcome/v1`。Required delivery接著封存knowledge Candidate並建立product／knowledge雙snapshot，再由另一個 fresh read-only Reviewer核對包含outcome的product bytes、Candidate與雙snapshot，回傳final `implementation-review/v1`。Final 只有在所有執行輸入未變且差異只含本 Work ID 的連續 create-only terminal additions時可驗證並引用preliminary commands；其餘情況 fresh 全量執行。兩份report使用連續round且不同path；同一份preliminary report不能兼任final review。Blocking finding 走 Fixing 與另一位 Reviewer；任一snapshot drift 保存invalid report後回Verifying；breaker仍由Reviewer契約判定。

完成條件：preliminary report已實體保存並與Outcome逐command一致；final Reviewer的required commands passed、coverage完整、沒有blocking finding，report product before／after與目前snapshot相同；required overlay的knowledge before／after亦相同且Candidate ref／digest精確一致。v2 另要求 review 結果綁定 dispatch assignment、knowledge review 與 publication handoff；fresh Reviewer 不得與 writer 共用 session。

BUG run 同時產生獨立 `bug-verification/v1`。Reviewer 的 `APPROVED` 只表示實作 snapshot 合格；BUG 結果另為 `verified | partial | failed`，兩者不得互相替代。

## 4. Terminal delivery

讀取 [品質契約](references/quality-contract.md)與 [交付協定](references/delivery-protocol.md)。前者只判 Pass／Fail；後者唯一擁有 state 與 terminal ordering。

完成條件：implementation結果唯一為 Complete、Awaiting upstream reapproval 或 Blocked。Implementation Complete 發生在 raw response／outputs／report 保存及保存後 snapshots 重算成功之後；required delivery此時轉knowledge/awaiting_user而非宣稱delivery Complete，直到人工核准promotion與lint通過。Worktree 與未提交 diff 保留。v2 通過 implementation／knowledge review 後交給 `finish`；finish 才可在 approved scope 內 stage、commit、push 與建立 draft PR，並將缺 remote／認證／網路記為可續跑的 publication pending。

## 維護

修改本 bundle 才讀取 [行為驗證契約](references/behavior-evaluation.md)，執行 owner validator／mutation tests、十個 forward cases、integration 與 fresh review；報告只記錄實際結果。
