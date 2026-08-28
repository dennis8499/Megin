---
name: implementation-execution
description: 執行已核准的 `ready-plan/v1`：依 WP 以 outside-in BDD／inner TDD 實作、全量驗證並交 fresh 唯讀 Reviewer。用於開始或續跑 Ready 計畫；規劃、需求探索、未核准計畫與單純審查不適用。
---

# 實作執行

把已核准的 `ready-plan/v1` 收斂成可重現的實作與獨立審查證據。主代理是唯一 writer；fresh Reviewer 只讀且不再委派。

## 不可變邊界

- Ready bundle、原始 sources 與治理全程唯讀；producer contract 缺陷回到上游重新規劃與核准。
- 唯一允許的產品寫入是 plan 明列的產品、測試與必要 test-only 設定；秘密、無關檔案及未授權外部狀態維持原狀。
- 不自行 stage、commit、push、merge、部署、發 ticket、清理或刪除 worktree。
- fresh 唯讀 subagent 能力不可用時進入 `Blocked`；主代理不替代 Reviewer。
- Reviewer 只核准固定 snapshot；相同 snapshot 完成後維持不變。

## 1. Preflight

完整讀取[Preflight 與 Ledger](references/preflight-and-ledger.md)。它是 execution workspace、binding、run identity、baseline、resume 與 revision 的唯一權威。驗證 `ready-plan/v1` schema／核准／hashes／base SHA／DAG／commands、fresh Reviewer 能力、專用 worktree、排他 binding、dirty baseline、工具及全部適用 Observed baseline。

任一檢查失敗時，在零產品變更下進入 `Awaiting upstream reapproval` 或 `Blocked`。全部通過且 Ledger 已保存原始證據時才能 `Preflight → Executing`。

## 2. Executing

Preflight 通過後完整讀取[BDD／TDD 執行迴圈](references/bdd-tdd-loop.md)。依 `WP-*` DAG 穩定拓撲序逐包、逐 scenario 執行 outside-in BDD red → 映射 inner TDD red／minimal green／refactor-with-green → BDD／related green；必要 `BOOT-*` 只建立 plan 核准的行為中立 contract shape。

每個 transition、diff 與 raw output 寫入 Ledger。所有 WP 為 `Verified` 才進入 `Verifying`。

## 3. Verifying 與 Reviewing

進入 `Verifying` 後，完整讀取[Reviewer 契約](references/reviewer-contract.md)，fresh 執行所有 full commands。自行驗證失敗時依[交付協定](references/delivery-protocol.md)轉 `Fixing`，使受影響 WP `Invalidated → Executing → Verified`，再回 `Verifying`。

全量通過才建立 canonical snapshot 並進入 `Reviewing`。每輪由全新、無實作歷史、唯讀且不得委派的 Reviewer 自行重跑並回傳 `implementation-review/v1` raw report／outputs；主代理保存。Blocking findings 走 `Fixing → Verifying` 並使用另一個 fresh Reviewer；breaker 或不可執行狀況依 Reviewer 契約分流。

Reviewer `APPROVED` 後，主代理先重算 snapshot。相同才可追加 report 並完成；drift report 標記失效，回到 `Verifying`。

## 4. 收斂與交付

準備判定結果時讀取[品質契約](references/quality-contract.md)與[交付協定](references/delivery-protocol.md)。品質契約只做二元檢查；交付協定是唯一執行狀態機與 terminal ordering 權威。終止狀態只有 `Complete`、`Awaiting upstream reapproval`、`Blocked`。

重新核准的 revision 依 Preflight/Ledger impact 規則續跑或要求新 worktree／base／run；舊證據保留為 `superseded`。

維護本 Skill 時才讀取[行為驗證契約](references/behavior-evaluation.md)，執行開發期檢查器與全部案例；一般執行不載入。
