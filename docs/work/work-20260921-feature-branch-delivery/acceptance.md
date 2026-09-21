# 人工驗收：feature 分支與人工審核後本機整合

- work_id: `work-20260921-feature-branch-delivery`
- acceptance_version: `acceptance-1`
- branch: `feature/work-20260921-feature-branch-delivery`
- base_branch: `main`
- base_commit: `44e29147209099368d8eed8cc773582148c26eaa`
- environment: 本機 Windows checkout；一個 repository root worktree
- response: `work-20260921-feature-branch-delivery / acceptance-1 / 接受`
- accepted_at: `2026-09-21 10:54:12 +08:00`
- accepted_snapshot: feature branch working tree at `HEAD 44e29147209099368d8eed8cc773582148c26eaa`, before delivery-only evidence updates

請依下列使用者可見情境確認文件與目前工作狀態。這些情境不要求重做內部驗證命令。

## REQ-BRANCH-001 — 從主分支基線建立 feature branch

操作：查看 `.agents/skills/megin/references/branch-policy.md`、README 的流程說明，以及目前
`git branch --show-current` 與 `git rev-parse main`。

預期：規則要求從記錄的 `main` 基線建立 `feature/work-20260921-feature-branch-delivery`，
目前 checkout 位於該 feature branch，並禁止直接在 `main` 開始產品實作。

## REQ-BRANCH-002 — 人工驗收前保持主分支與提交不變

操作：查看 `workflow.md`、`verification.md` 的 feature/base SHA 與目前 Git 狀態。

預期：人工驗收回覆前不建立 feature commit、不暫存、不切回 `main` 整合；`main` 仍維持
`44e29147209099368d8eed8cc773582148c26eaa`。

## REQ-BRANCH-003 — 驗收後以 `--no-ff` 本機整合

操作：閱讀 `megin-finishing-delivery/SKILL.md`、README 與 `branch-policy.md` 的交付段落。

預期：接受後先在 feature branch 建立 feature commit，再確認 `main` 沒有漂移，執行
`git merge --no-ff <feature_branch>`；整合結果保留兩個父提交與 feature branch。

## REQ-BRANCH-004 — 漂移或快照變更重新驗證

操作：閱讀 `branch-policy.md` 與 `workflow-record.md` 的漂移恢復規則。

預期：`main` 前進、feature 快照改變或 branch 身分不符時，流程停止並要求重新審查、驗證與
人工驗收；舊 acceptance 不可套用到新快照。

## REQ-BRANCH-005 — 衝突保留現場

操作：閱讀 `branch-policy.md` 的衝突處理與 `workflow.md` 的「阻礙與下一步」。

預期：衝突時不自動 reset、stash、刪除 branch 或改寫歷史，並記錄目前 branch、提交與下一個
恢復動作。

## REQ-BRANCH-006 — 中斷後可恢復

操作：閱讀 `branch-policy.md` 的整合證據與 `workflow-record.md` 的交付欄位。

預期：feature commit 後中斷時保留 feature branch、feature commit 與未整合的 `main`，可依
工作紀錄恢復；成功整合後保留 feature branch。

## 回覆格式

所有情境通過時，請回覆：

`work-20260921-feature-branch-delivery / acceptance-1 / 接受`

若有情境未通過，請回覆同一 Work ID 與版本，並指出情境 ID、觀察結果及阻礙。

## 驗收結果

使用者已於 2026-09-21 10:54:12 +08:00 回覆 `work-20260921-feature-branch-delivery / acceptance-1 / 接受`。
六個核准情境均接受；交接至 `phase: delivery`，下一步是 source-backed knowledge review、feature
commit 與 `--no-ff` 本機整合。
