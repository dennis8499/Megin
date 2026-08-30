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
| Ready ready-plan/v1，開始或續跑實作 | 本 Skill |
| 未核准／無版本 plan，或需要規劃 | Technical Planning |
| 需求仍待探索 | Requirements Discovery |
| 只要求唯讀審查 | Review workflow |

完成條件：輸入唯一落在一列；只有第一列可在 Preflight 通過後取得產品寫入權。

## 不變量

- Ready bundle、sources、delivery requirements 與治理唯讀。
- 寫入集合精確等於 plan 明列的產品、測試與 test-only 設定；秘密、無關檔案與未授權外部狀態不變。
- 嚴禁 stage、commit、push、merge、deploy、建立 ticket、cleanup 或刪除 worktree。
- Fresh Reviewer capability 不可用時為 Blocked；Reviewer 只核准固定 snapshot，Complete 後 run 凍結。

## 1. Preflight

完整讀取 [Preflight 與 Ledger](references/preflight-and-ledger.md)。再依實際分支載入：

- 有 delivery-run/v1 → [Orchestrated Delivery](references/orchestrated-delivery.md)
- 既有 binding 或 Ready/source revision → [Resume 與 Revision](references/resume-and-revision.md)
- 第一個 public seam／entrypoint 不存在 → [Greenfield Bootstrap](references/greenfield-bootstrap.md)

Producer 缺口為 Awaiting upstream reapproval；workspace、能力、工具、baseline 或 dirty-state 問題為 Blocked。

完成條件：全部適用契約通過、host-temp Ledger 已保存 evidence，且產品／測試／dependencies／Ready／外部狀態 hashes 與 Preflight 前相同；才進 Executing。

## 2. Executing

完整讀取 [BDD／TDD 執行迴圈](references/bdd-tdd-loop.md)。依 WP DAG 穩定拓撲序執行 public-seam BDD red → inner test red → minimal green → refactor-with-green → BDD／related green。Greenfield red 前的 production shape 只來自已核准 BOOT contract。

完成條件：每個新行為都有時間順序正確的 red／green；一個 WP 的 scenarios、tests、commands、scope 與追溯全通過後才為 Verified；全部 WP Verified 才進 Verifying。

## 3. Verifying／Reviewing

完整讀取 [Reviewer 契約](references/reviewer-contract.md)。主代理 fresh 跑全部 full commands；失敗走 Fixing，使 affected WP 與必要 downstream 依序 Invalidated → Executing → Verified。

全量通過後建立 canonical snapshot。每輪由一個 fresh read-only Reviewer 直接讀 raw artifacts／Ledger／outputs，自行重跑命令並回傳 implementation-review/v1。Blocking finding 走 Fixing 與另一位 Reviewer；snapshot drift 保存 invalid report 後回 Verifying；breaker 仍由 Reviewer 契約判定。

完成條件：雙方 required commands passed、coverage 完整、沒有 blocking finding，report before／after 與目前 snapshot 相同。

## 4. Terminal delivery

讀取 [品質契約](references/quality-contract.md)與 [交付協定](references/delivery-protocol.md)。前者只判 Pass／Fail；後者唯一擁有 state 與 terminal ordering。

完成條件：結果唯一為 Complete、Awaiting upstream reapproval 或 Blocked。Complete 發生在 raw response／outputs／report 保存及保存後 snapshot 重算成功之後；worktree 與未提交 diff 保留。

## 維護

修改本 bundle 才讀取 [行為驗證契約](references/behavior-evaluation.md)，執行 owner validator／mutation tests、九個 forward cases、integration 與 fresh review；報告只記錄實際結果。
