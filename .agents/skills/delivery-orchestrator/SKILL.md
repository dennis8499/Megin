---
name: delivery-orchestrator
description: 交付軟體變更的統一入口：先依任務大小分類，再建立或續接 Work ID 專用 Git worktree，依目前 phase 路由需求探索、技術規劃、實作執行與 fresh review。適用於新功能、已完成唯讀分診的修錯、實質重構及介面／資料／依賴變更；純解說、診斷、審查、plan-only、格式與微小文字修改不適用。新 portable run 使用 `delivery-run/v2`；沒有 v2 state 的既有工作維持 v1 相容流程。
---

<!-- authority: delivery-entrypoint -->

# Delivery Orchestrator

本 Skill 是唯一 mutating SDLC 入口，以穩定 work_id 保存 workspace identity、階段核准與跨階段交接。Child Skills 擁有內容品質與執行；本 Skill 擁有 Git workspace、delivery state、phase authorization 與 routing。既有 `delivery-run/v1` 仍使用兩次人工核准；portable `delivery-run/v2` 依 [v2 任務分級與核准契約](references/v2-task-routing.md) 讓小任務使用一次 integrated gate，大型變更保留 Requirements 與 Planning 兩個 gate。
人工Gate的review surface一律遵循`.agents/skills/project-knowledge/references/human-gate-review.md`：先重驗immutable review files，Chat只輸出摘要、direct links與exact identity。

## 呼叫邊界

| 請求 | 路由 |
|---|---|
| 新功能、已有 `confirmed`／`likely` assessment 的修錯、實質重構、介面／資料／依賴行為變更 | 本 Skill |
| portable `sdlc` 請求 | 先唯讀分類為 `read_only`、`small`、`large` 或 `bug`；只有核准後的 `small`／`large`／bug run 進入 v2 implementation |
| 使用者直接點名 Requirements／Planning／Implementation，且工作會形成階段成果或其他寫入 | 先進本 Skill，再依 current phase 授權唯一 child |
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
- Child 名稱、prompt、Ready artifact 或 caller flag 不授予寫入權；只有 [階段授權](references/stage-authorization.md) 的 current record 判定有效。
- v2 的 task class、approval policy、writer assignment、knowledge scope 與 publication destination 都由持久化 state 的 digest 綁定；分類及核准前不建立產品 worktree 或 branch。
- v2 同一 worktree 同一時間最多一名取得授權的 implementation writer。writer 可以是 implementation subagent；不得平行寫入，Reviewer 必須是另一個 fresh、唯讀 session。
- v2 的 in-scope knowledge review 與 Git finish handoff 由 `finish` 流程擁有；merge、deployment 與 cleanup 永遠不在自動 finish 範圍內。

## 0. v2 任務分級與 Gate

Portable `sdlc start` 先做唯讀探索並保存 `task_class`。`read_only` 只回報，不建立
run；`small` 使用一份精簡 design brief 與一次 integrated human approval；`large`
使用獨立 Requirements／Planning approval；`bug` 先完成唯讀 diagnosis，再依影響
進入 `small` 或 `large` bug run。分級、升級條件與核准 payload 的完整規則見
[v2 任務分級與核准契約](references/v2-task-routing.md)。

核准後才建立 Work ID 專用 worktree／branch，並自動 dispatch 下一個已授權 phase。
小任務的 integrated approval 涵蓋 scoped implementation、fresh review、knowledge
review 與 finish handoff；大型變更的第二次 Planning approval 後自動進 Implementation，
不再詢問額外的「是否開始實作」。途中若發現架構、契約、資料、權限、依賴或跨模組
影響，保存進度並升級為 large，要求受影響內容重新核准。

## 1. BUG 開案前分診

修錯請求在任何 `probe/start` 前先完整執行 `bug-diagnosis`。只有 schema-valid `confirmed`／`likely` assessment Candidate可建立 `work_kind: bug` run；`bug_id` 使用核准 assessment identity。Diagnosis 自身保持唯讀。

完成條件：standard work開案不產生BUG欄位（途中發現時才加入deferred overlay）；bug work有唯一 primary BUG identity，assessment仍等待第一次既有 Requirements gate create-only materialize。

## 2. 取得 identity

完整讀取 [Workspace 與 Run](references/workspace-and-run.md)。v1 優先使用已綁定或明示 work_id；v2 則由 portable state 以 repository identity／Work ID 定位。兩者都必須先唯讀 locate：唯一 active 才 resume，多個只列 ID，沒有才依分類建立新 work。

New work／generation 再讀取 [Workspace 建立](references/workspace-creation.md)，以 probe／start 建立。GIT_TRUST_REQUIRED 時取得 unsandboxed Git 授權後原樣重跑，不新增或繞過 safe.directory。

完成條件：schema-valid record 的 repo、worktree、branch、base 與 registry binding 全相符；new generation 另為 ready。後續 repository 命令以該 worktree 為 cwd。

## 3. 路由 phase

Workspace ready 後完整讀取 [階段授權](references/stage-authorization.md)與 [階段路由](references/stage-routing.md)。v1 先用 `authorize --repo <current-worktree> --phase <current-phase> --work-id <work-id>` 驗證 exact active phase；v2 使用 state 的 dispatch authorization 與 writer ticket，再只載入目前 child：

- requirements → requirements-discovery
- planning → technical-planning
- implementation → implementation-execution
- knowledge → 重驗reviewed Candidate，Chat只呈現summary projection與direct links，等待獨立knowledge promotion核准；產品修改則回implementation

v1 只有 `outcome: authorized` 才 dispatch；v2 使用等價的 current dispatch authorization 才 dispatch。其他結果保持零 child mutation並由本 Skill 修復或建立 context。取得授權後 Child 先持久化自身結果；orchestrator 再以一次 atomic transition 保存 refs／state。Child 不直接執行 delivery transition。

Required knowledge overlay下，Requirements與Plan各自以原核准evidence同時綁定Ready knowledge receipt；planning receipt的`formal_paths`必須精確等於owner-validated完整Ready-plan bundle，`no-change`也不能省略。Implementation先實體保存preliminary fresh report／raw outputs，repo-side Outcome以current run ID、report path／hash與逐command evidence綁定；封存Candidate後由另一位final fresh Reviewer核對含Outcome的product snapshot及完整knowledge pre-tree／expected post-tree snapshot，再進knowledge phase，不能直達delivery Complete。Final finding修正使用下一個create-only Outcome revision，不覆寫舊版。舊record缺`knowledge_gate`時維持legacy routing。

BUG run另依階段綁定：Requirements approval 同時保存 assessment JSON／Markdown hashes；Plan綁定`bug_context`；Implementation Complete需要獨立`bug-verification/v1`，`failed`不得Complete，`partial`只依已核准safeguards成立。Required overlay在進knowledge時綁verification，legacy在terminal Complete綁定。

完成條件：record phase/status 與 child 狀態一致，current refs 可重算 hash；未完成 child 沒有被越過或重跑。

## 4. Resume／Blocked／Complete

Resume 從最早未完成 action 繼續。Blocked 追加 blocker evidence；解除時在同 phase 追加 recovery evidence。Legacy Complete先保存 implementation Ledger／review refs，再轉 complete/complete；required overlay則先進knowledge/awaiting_user，只有matching promotion receipt、完整knowledge post-tree相符與full lint通過才凍結delivery。

交付回報 work_id、generation、worktree／branch、phase／status、current refs、next action 與 record path；Complete 另含 fresh verdict 與未提交 diff。

完成條件：v1 terminal ordering、schema 與 append-only semantics 通過；workspace 保留且沒有 terminal Git／發布動作。v2 另須由 [v2 派工、審查與交付收尾契約](../implementation-execution/references/v2-dispatch-and-finish.md) 完成 approved-scope knowledge review 與 `finish` handoff；finish 可 commit、push 與建立 draft PR，但不得 merge、deploy 或 cleanup。

## 維護

修改本 bundle 才讀取 [行為驗證契約](references/behavior-evaluation.md)，執行 static、unit、integration、forward evaluator 與 fresh review。完成條件：適用案例有隔離 evidence，schema bytes／CLI 相容，報告只記實際結果。
