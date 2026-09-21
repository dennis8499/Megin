# 需求：feature 分支與人工審核後本機整合

## 目標

補齊 Megin Skills-only 交付流程，使每個需要修改 repository 的工作都從主分支的明確基線建立
feature branch，在 feature branch 完成開發、獨立審查、自動驗證與人工驗收，驗收通過後才建立
feature commit 並以 `--no-ff` 本機合併回主分支。

## 使用者與範圍

使用者是透過 Codex 使用 Megin Skills 的開發者與進行人工審核的人員。納入範圍包含共用分支政策、
Megin 入口、需求探索、技術規劃、實作、審查、驗證、人工驗收、交付 Skills、工作紀錄範本、README、
OPERATIONS、可分發 ZIP 與可執行情境驗證。主分支依 repository 既有設定判定；本 repository 的主分支
是 `main`。

## 排除範圍

不新增 Megin runtime、hook、MCP、Plugin 或遠端 PR 流程；不自動 fetch、pull、push、部署、刪除
feature branch 或清理 worktree；不搬移既有已進入 `main` 的歷史提交，也不改寫歷史。

## 行為需求

- 計畫核准後才可從已確認的主分支基線建立 `feature/<work-id>`，並在 `workflow.md` 保留主分支、
  基線 SHA、feature branch、工作目錄與 `--no-ff` 目標。
- 實作、測試、審查與驗證必須在 feature branch；人工驗收前主分支不可有本 Work ID 的變更或提交。
- 主分支漂移、驗收後快照變更、無關未提交修改、branch 身分不符或衝突無法處理時，保留現場並
  停止；主分支漂移或快照變更須重新審查、驗證與人工驗收。
- 人工驗收明確通過後才可在 feature branch 建立提交；確認整合目標仍符合計畫後，使用
  `git merge --no-ff` 合併回主分支。
- 整合完成必須核對兩個父提交、feature commit 祖先關係、目標分支內容與已驗收內容一致，並保存
  整合證據；保留 feature branch。

## 驗收標準

1. `REQ-BRANCH-001`：核准計畫後，Megin 從記錄的主分支基線建立指定 feature branch，且實作前拒絕
   直接在主分支修改。
2. `REQ-BRANCH-002`：人工驗收前，Megin 不建立 feature commit、不切回主分支整合，也不建立 merge
   commit。
3. `REQ-BRANCH-003`：人工驗收通過後，Megin 在 feature branch 建立提交並以 `--no-ff` 合併，merge
   commit 具有兩個父提交且保留 feature branch。
4. `REQ-BRANCH-004`：主分支漂移、驗收後內容改變、衝突或中斷恢復都會停止在有證據的狀態；只有重新
   審查、驗證與驗收後才可整合。
5. `REQ-BRANCH-005`：衝突發生時保留現場、分支與恢復資訊，不自動清理或改寫歷史。
6. `REQ-BRANCH-006`：流程在 feature commit 後中斷時，保留 feature commit 與主分支未整合狀態，
   可依工作紀錄恢復。
