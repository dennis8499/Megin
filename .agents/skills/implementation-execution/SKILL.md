---
name: implementation-execution
description: 執行已核准的 ready-plan/v1：依 WP 進行 outside-in BDD／inner TDD、全量驗證與 fresh 唯讀 review。適用於開始或續跑 Ready 計畫；規劃、需求探索、未核准計畫與單純審查不適用。
---

<!-- authority: implementation-entrypoint -->

# 實作執行

把 Ready plan 收斂為可重現的產品 diff、Ledger 與獨立審查證據。主代理是唯一 writer；每輪 Reviewer 都是 fresh、唯讀且不再委派。

## 呼叫邊界

| 輸入 | 路由 |
|---|---|
| Ready ready-plan/v1 且不含 `bug_context`，開始或續跑標準實作 | 本 Skill |
| Ready plan 含 `bug_context` 與已核准 assessment，執行 BUG 修復 | 本 Skill 的 BUG overlay |
| 未核准／無版本 plan，或需要規劃 | Technical Planning |
| 需求仍待探索 | Requirements Discovery |
| 只要求唯讀審查 | Review workflow |

完成條件：輸入唯一落在一列；只有前兩列可在 Preflight 通過後取得產品寫入權，第二列另受 BUG overlay 約束。

## 不變量

- Ready bundle、sources、delivery requirements 與治理唯讀。
- 寫入集合精確等於 plan 明列的產品、測試與 test-only 設定；秘密、無關檔案與未授權外部狀態不變。
- 嚴禁 stage、commit、push、merge、deploy、建立 ticket、cleanup 或刪除 worktree。
- Fresh Reviewer capability 不可用時為 Blocked；Reviewer 只核准固定 snapshot，Complete 後 run 凍結。
- BUG assessment 只是診斷 evidence；Requirements 仍唯一擁有 WHAT，Ready plan 仍唯一擁有 HOW。不得在實作期改寫它們來合理化 patch。

## 1. Preflight

完整讀取 [Preflight 與 Ledger](references/preflight-and-ledger.md)。再依實際分支載入：

- 有 delivery-run/v1 → [Orchestrated Delivery](references/orchestrated-delivery.md)
- 既有 binding 或 Ready/source revision → [Resume 與 Revision](references/resume-and-revision.md)
- 第一個 public seam／entrypoint 不存在 → [Greenfield Bootstrap](references/greenfield-bootstrap.md)

Ready binding 通過後、取得產品寫入權前，執行 read-only 知識 preflight：

`python -X utf8 -B .agents/skills/project-knowledge/scripts/knowledge_cli.py query --repo . --stage implementation --query "<目前實作意圖>"`

保存 `knowledge-context/v1` 到 Ledger，並在修改前重讀每個 result 的 `source_refs`。這個步驟不寫回 Wiki 或產品；typed dependency／contract error 為 Blocked。只有本身由 Ready `BOOT-*` 建立 project-knowledge seam 的 run 可使用明列的 bootstrap exception。

Producer 缺口為 Awaiting upstream reapproval；workspace、能力、工具、baseline 或 dirty-state 問題為 Blocked。

完成條件：全部適用契約通過、host-temp Ledger 已保存 evidence，且產品／測試／dependencies／Ready／外部狀態 hashes 與 Preflight 前相同；才進 Executing。

## 2. Executing

完整讀取 [BDD／TDD 執行迴圈](references/bdd-tdd-loop.md)。依 WP DAG 穩定拓撲序執行 public-seam BDD red → inner test red → minimal green → refactor-with-green → BDD／related green。Greenfield red 前的 production shape 只來自已核准 BOOT contract。

完成條件：每個新行為都有時間順序正確的 red／green；一個 WP 的 scenarios、tests、commands、scope 與追溯全通過後才為 Verified；全部 WP Verified 才進 Verifying。

BUG plan 另須先重跑原始症狀 oracle，再取得 regression red；只做一個最小根因修復。診斷失真、修法失敗或影響範圍擴大時立即回 Planning／Requirements，不疊加猜測式 patch。

## 3. Verifying／Reviewing

完整讀取 [Reviewer 契約](references/reviewer-contract.md)。主代理 fresh 跑全部 full commands；失敗走 Fixing，使 affected WP 與必要 downstream 依序 Invalidated → Executing → Verified。

全量通過後先由 fresh read-only Reviewer 完成不含outcome／Candidate binding的preliminary product review；主代理把report與每個raw output create-only保存於current run，並以report logical ref、path與SHA-256建立create-only `implementation-outcome/v1`。Required delivery接著封存knowledge Candidate並建立product／knowledge雙snapshot，再由另一個 fresh read-only Reviewer核對包含outcome的product bytes、Candidate與雙snapshot，回傳final `implementation-review/v1`。兩份report使用連續round且不同path；同一份preliminary report不能兼任final review。Blocking finding 走 Fixing 與另一位 Reviewer；任一snapshot drift 保存invalid report後回Verifying；breaker仍由Reviewer契約判定。

完成條件：preliminary report已實體保存並與Outcome逐command一致；final Reviewer的required commands passed、coverage完整、沒有blocking finding，report product before／after與目前snapshot相同；required overlay的knowledge before／after亦相同且Candidate ref／digest精確一致。

BUG run 同時產生獨立 `bug-verification/v1`。Reviewer 的 `APPROVED` 只表示實作 snapshot 合格；BUG 結果另為 `verified | partial | failed`，兩者不得互相替代。

## 4. Terminal delivery

讀取 [品質契約](references/quality-contract.md)與 [交付協定](references/delivery-protocol.md)。前者只判 Pass／Fail；後者唯一擁有 state 與 terminal ordering。

完成條件：implementation結果唯一為 Complete、Awaiting upstream reapproval 或 Blocked。Implementation Complete 發生在 raw response／outputs／report 保存及保存後 snapshots 重算成功之後；required delivery此時轉knowledge/awaiting_user而非宣稱delivery Complete，直到人工核准promotion與lint通過。Worktree 與未提交 diff 保留。

## 維護

修改本 bundle 才讀取 [行為驗證契約](references/behavior-evaluation.md)，執行 owner validator／mutation tests、十個 forward cases、integration 與 fresh review；報告只記錄實際結果。
