---
name: delivery-orchestrator
description: 為新的軟體行為或架構變更建立或續接 Work ID 專用 Git worktree，並編排 requirements-discovery、technical-planning、implementation-execution 至 fresh review。用於要求落地的新功能、修錯、實質重構與介面／資料／依賴變更；純解說、診斷、審查、plan-only、格式或微小文字修改不適用。
---

# Delivery Orchestrator

以一個穩定 `work_id` 把需求、規劃與實作留在同一個隔離 workspace。既有三個階段 Skill 各自擁有內容與核准規則；本 Skill 只擁有 workspace、跨階段狀態與交接。

## 不可變邊界

- 新 work 只從嚴格 clean、attached 的 primary worktree 建立；resume 只依既有 record，不以 primary dirty state 阻擋。
- Worktree／branch 建立是唯一自動 Git mutation；不 stash、reset、clean、stage、commit、push、merge、部署、刪除或清理 worktree。
- 需求與計畫各保留一次完整人工核准。計畫成為 Ready 後，原始落地請求與兩次核准共同授權直接進入實作，不再詢問第三次。
- Runtime record 位於 host temp，不提交；秘密只保存遮蔽事件或 digest，不保存原值。
- 相同 `work_id`、path、branch 或 registry 有無法證明一致的碰撞時停止，不接管或覆寫。

## 1. 決定 new 或 resume

完整讀取[Workspace 與 Run 契約](references/workspace-and-run.md)。優先使用本對話已綁定或使用者提供的 `work_id`；否則執行 helper 的 `locate`：只有一個 active work 時續跑，多個時只請使用者選擇，沒有時才建立新 work。使用者明確要求另一個新 work 時不得誤接既有 record。

新 work 先以 `probe` 取得 repo／HEAD／clean evidence 與建議 ID，再以 `start` 建立。任何後續 repo 命令與寫入都以回傳的 delivery worktree 為 cwd；不能取得 sibling path 寫入授權時，在 Git mutation 前停止。

## 2. 依 phase 編排

Workspace ready 後完整讀取[階段路由契約](references/stage-routing.md)，並只載入目前 phase 對應的既有 Skill：

1. `requirements`：完整讀取並遵守 `../requirements-discovery/SKILL.md`，指定 `docs/work/<work_id>/requirements.md` 或最小 revision 後綴。
2. `planning`：需求 Ready 後完整讀取並遵守 `../technical-planning/SKILL.md`，指定 `docs/work/<work_id>/plan/` 或最小 revision 後綴。
3. `implementation`：技術計畫 Ready 後完整讀取並遵守 `../implementation-execution/SKILL.md`；fresh Reviewer 與 terminal ordering 仍由該 Skill 擁有。

每個可重現的 approval、artifact、阻塞與 child Ledger 先持久化，再用 helper `transition` 追加 event。Technical Planning 發現需求缺口時回 `requirements`；Implementation 要求上游重新核准時回 `planning`。`Complete` record 不重開。

## 3. 交付與維護

中斷、等待核准或 Blocked 時回報 `work_id`、worktree、branch、phase／status、目前 artifacts、blocker 與 run record path。Complete 時另回報 requirements、Ready handoff、implementation Ledger、fresh review 結果及未提交 diff；保留 workspace 原狀。

維護本 Skill 時才讀取[行為驗證契約](references/behavior-evaluation.md)，執行其中的靜態檢查、隔離 Git fixtures 與 fresh evaluator；一般 runtime 不載入。
