---
name: delivery-orchestrator
description: 交付新的軟體行為或架構變更：建立或續接 Work ID 專用 Git worktree，並路由需求探索、技術規劃、實作執行與 fresh review。適用於新功能、已完成唯讀分診的修錯、實質重構及介面／資料／依賴變更；純解說、診斷、審查、plan-only、格式與微小文字修改不適用。
---

<!-- authority: delivery-entrypoint -->

# Delivery Orchestrator

以穩定 work_id 保存 workspace identity、兩次人工核准與跨階段交接。Child Skills 擁有內容品質與執行；本 Skill 擁有 Git workspace、delivery state 與 routing。

## 呼叫邊界

| 請求 | 路由 |
|---|---|
| 新功能、已有 `confirmed`／`likely` assessment 的修錯、實質重構、介面／資料／依賴行為變更 | 本 Skill |
| 疑似 BUG 但尚無 assessment | 先用 `bug-diagnosis` 唯讀分診；此時不建立 worktree |
| `not-a-bug` | 期望行為改變時走 standard requirements，否則結束且不建立 run |
| 純解說、診斷、唯讀審查、plan-only | 對應一般／階段工作流 |
| 格式或微小文字修改 | 直接處理，不建立 delivery run |

完成條件：請求唯一落在一列；不適用時沒有 registry、branch 或 worktree mutation。

## 不變量

- New work 的 base 是 strict-clean attached primary；resume 只接受可驗證 record。
- 唯一自動 Git mutation 是 helper 建立 worktree／branch。嚴禁 stash、reset、clean、stage、commit、push、merge、deploy、delete 或 cleanup。
- Requirements 與 Plan 各有一次完整人工核准；第二次核准直接授權 Implementation。
- BUG run 使用 optional `work_kind: bug` overlay；critical／high 不繞過 gate。缺 `work_kind` 的舊 record 等同 standard work。
- Runtime record 在 host temp；repository artifacts 只存相對路徑，秘密只存 digest、byte count 或遮蔽事件。
- ID、path、branch、registry 與 generation continuity 必須可證明；collision／drift 保留現場並停止。

## 1. BUG 開案前分診

修錯請求在任何 `probe/start` 前先完整執行 `bug-diagnosis`。只有 schema-valid `confirmed`／`likely` assessment Candidate可建立 `work_kind: bug` run；`bug_id` 使用核准 assessment identity。Diagnosis 自身保持唯讀。

完成條件：standard work開案不產生BUG欄位（途中發現時才加入deferred overlay）；bug work有唯一 primary BUG identity，assessment仍等待第一次既有 Requirements gate create-only materialize。

## 2. 取得 identity

完整讀取 [Workspace 與 Run](references/workspace-and-run.md)。優先使用已綁定或明示 work_id；否則 locate：唯一 active 就 resume，多個只列 ID，沒有才 new work。

New work／generation 再讀取 [Workspace 建立](references/workspace-creation.md)，以 probe／start 建立。GIT_TRUST_REQUIRED 時取得 unsandboxed Git 授權後原樣重跑，不新增或繞過 safe.directory。

完成條件：schema-valid record 的 repo、worktree、branch、base 與 registry binding 全相符；new generation 另為 ready。後續 repository 命令以該 worktree 為 cwd。

## 3. 路由 phase

Workspace ready 後讀取 [階段路由](references/stage-routing.md)，只載入目前 child：

- requirements → requirements-discovery
- planning → technical-planning
- implementation → implementation-execution
- knowledge → 展示 reviewed Candidate，等待獨立 knowledge promotion 核准；產品修改則回 implementation

Child 先持久化結果；orchestrator 再以一次 atomic transition 保存 refs／state。

Required knowledge overlay下，Requirements與Plan各自以原核准evidence同時綁定Ready knowledge receipt；planning receipt的`formal_paths`必須精確等於owner-validated完整Ready-plan bundle，`no-change`也不能省略。Implementation先實體保存preliminary fresh report／raw outputs，repo-side Outcome以current run ID、report path／hash與逐command evidence綁定；封存Candidate後由另一位final fresh Reviewer核對含Outcome的product snapshot及完整knowledge pre-tree／expected post-tree snapshot，再進knowledge phase，不能直達delivery Complete。Final finding修正使用下一個create-only Outcome revision，不覆寫舊版。舊record缺`knowledge_gate`時維持legacy routing。

BUG run另依階段綁定：Requirements approval 同時保存 assessment JSON／Markdown hashes；Plan綁定`bug_context`；Implementation Complete需要獨立`bug-verification/v1`，`failed`不得Complete，`partial`只依已核准safeguards成立。Required overlay在進knowledge時綁verification，legacy在terminal Complete綁定。

完成條件：record phase/status 與 child 狀態一致，current refs 可重算 hash；未完成 child 沒有被越過或重跑。

## 4. Resume／Blocked／Complete

Resume 從最早未完成 action 繼續。Blocked 追加 blocker evidence；解除時在同 phase 追加 recovery evidence。Legacy Complete先保存 implementation Ledger／review refs，再轉 complete/complete；required overlay則先進knowledge/awaiting_user，只有matching promotion receipt、完整knowledge post-tree相符與full lint通過才凍結delivery。

交付回報 work_id、generation、worktree／branch、phase／status、current refs、next action 與 record path；Complete 另含 fresh verdict 與未提交 diff。

完成條件：terminal ordering、schema 與 append-only semantics 通過；workspace 保留且沒有 terminal Git／發布動作。

## 維護

修改本 bundle 才讀取 [行為驗證契約](references/behavior-evaluation.md)，執行 static、unit、integration、forward evaluator 與 fresh review。完成條件：適用案例有隔離 evidence，schema bytes／CLI 相容，報告只記實際結果。
