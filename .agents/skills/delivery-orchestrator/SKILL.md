---
name: delivery-orchestrator
description: 交付新的軟體行為或架構變更：建立或續接 Work ID 專用 Git worktree，並路由需求探索、技術規劃、實作執行與 fresh review。適用於新功能、修錯、實質重構及介面／資料／依賴變更；純解說、診斷、審查、plan-only、格式與微小文字修改不適用。
---

<!-- authority: delivery-entrypoint -->

# Delivery Orchestrator

以穩定 work_id 保存 workspace identity、兩次人工核准與跨階段交接。Child Skills 擁有內容品質與執行；本 Skill 擁有 Git workspace、delivery state 與 routing。

## 呼叫邊界

| 請求 | 路由 |
|---|---|
| 新功能、修錯、實質重構、介面／資料／依賴行為變更 | 本 Skill |
| 純解說、診斷、唯讀審查、plan-only | 對應一般／階段工作流 |
| 格式或微小文字修改 | 直接處理，不建立 delivery run |

完成條件：請求唯一落在一列；不適用時沒有 registry、branch 或 worktree mutation。

## 不變量

- New work 的 base 是 strict-clean attached primary；resume 只接受可驗證 record。
- 唯一自動 Git mutation 是 helper 建立 worktree／branch。嚴禁 stash、reset、clean、stage、commit、push、merge、deploy、delete 或 cleanup。
- Requirements 與 Plan 各有一次完整人工核准；第二次核准直接授權 Implementation。
- Runtime record 在 host temp；repository artifacts 只存相對路徑，秘密只存 digest、byte count 或遮蔽事件。
- ID、path、branch、registry 與 generation continuity 必須可證明；collision／drift 保留現場並停止。

## 1. 取得 identity

完整讀取 [Workspace 與 Run](references/workspace-and-run.md)。優先使用已綁定或明示 work_id；否則 locate：唯一 active 就 resume，多個只列 ID，沒有才 new work。

New work／generation 再讀取 [Workspace 建立](references/workspace-creation.md)，以 probe／start 建立。GIT_TRUST_REQUIRED 時取得 unsandboxed Git 授權後原樣重跑，不新增或繞過 safe.directory。

完成條件：schema-valid record 的 repo、worktree、branch、base 與 registry binding 全相符；new generation 另為 ready。後續 repository 命令以該 worktree 為 cwd。

## 2. 路由 phase

Workspace ready 後讀取 [階段路由](references/stage-routing.md)，只載入目前 child：

- requirements → requirements-discovery
- planning → technical-planning
- implementation → implementation-execution

Child 先持久化結果；orchestrator 再以一次 atomic transition 保存 refs／state。

完成條件：record phase/status 與 child 狀態一致，current refs 可重算 hash；未完成 child 沒有被越過或重跑。

## 3. Resume／Blocked／Complete

Resume 從最早未完成 action 繼續。Blocked 追加 blocker evidence；解除時在同 phase 追加 recovery evidence。Complete 先保存 implementation Ledger／review refs，再轉 complete/complete 並凍結。

交付回報 work_id、generation、worktree／branch、phase／status、current refs、next action 與 record path；Complete 另含 fresh verdict 與未提交 diff。

完成條件：terminal ordering、schema 與 append-only semantics 通過；workspace 保留且沒有 terminal Git／發布動作。

## 維護

修改本 bundle 才讀取 [行為驗證契約](references/behavior-evaluation.md)，執行 static、unit、integration、forward evaluator 與 fresh review。完成條件：適用案例有隔離 evidence，schema bytes／CLI 相容，報告只記實際結果。
