# Megin 工作流程：feature 分支與人工審核後本機整合

- schema: megin-skills-workflow/v1
- work_id: work-20260921-feature-branch-delivery
- repository: C:/Users/denni/OneDrive/Desktop/新增資料夾/Megin
- base_commit: 44e29147209099368d8eed8cc773582148c26eaa
- branch: main
- base_branch: main
- feature_branch: feature/work-20260921-feature-branch-delivery
- merge_strategy: --no-ff
- delivery_target: base_branch
- route: large
- phase: delivery
- status: complete
- plan_version: plan-1
- last_updated: 2026-09-21

## 目的與邊界

本 Work ID 將 Megin 的交付流程改為從 `main` 基線建立 feature branch，在 feature branch 完成開發、
獨立審查、自動驗證與人工驗收，通過後建立 feature commit 並以 `--no-ff` 合併回本機 `main`。本次
只修改 Skills 規則、工作紀錄範本、README、OPERATIONS、可分發封裝與本 Work ID 證據，不新增 runtime、
遠端 PR、推送、部署、branch 刪除或 worktree 清理。

## 驗收

情境 `REQ-BRANCH-001` 至 `REQ-BRANCH-006` 詳見 [features/branch-policy.feature](features/branch-policy.feature)。
自動驗證需通過分支行為隔離測試、Skills 封裝驗證、既有語言政策回歸與 `git diff --check`；人工驗收
需確認實作起點、驗收前主分支保護、驗收後 `--no-ff` 整合、漂移重新驗證及中斷恢復情境。

| 情境 | 任務 | 自動驗證 | 人工驗收 | 證據 |
| --- | --- | --- | --- | --- |
| `REQ-BRANCH-001` | T2、T3 | `verify_branch_policy.py` | 必要 | `implementation/verification-output.txt`、`acceptance.md` |
| `REQ-BRANCH-002` | T3 | `verify_branch_policy.py` | 必要 | `implementation/verification-output.txt`、`acceptance.md` |
| `REQ-BRANCH-003` | T3、T4 | `verify_branch_policy.py` | 必要 | `implementation/verification-output.txt`、`acceptance.md` |
| `REQ-BRANCH-004` | T3、T5、T6、T7 | `verify_branch_policy.py` | 必要 | `implementation/verification-output.txt`、`acceptance.md` |
| `REQ-BRANCH-005` | T3、T4 | `verify_branch_policy.py` | 必要 | `implementation/verification-output.txt`、`acceptance.md` |
| `REQ-BRANCH-006` | T3、T4 | `verify_branch_policy.py` | 必要 | `implementation/verification-output.txt`、`acceptance.md` |

## 計畫與核准

計畫版本：`plan-1`。使用者在 2026-09-21 以「PLEASE IMPLEMENT THIS PLAN」明確核准本次完整計畫。
本紀錄綁定 `main` 的基線 `44e29147209099368d8eed8cc773582148c26eaa`、feature branch
`feature/work-20260921-feature-branch-delivery` 與本機 `--no-ff` 交付目標。

允許修改的產品路徑：`.agents/skills/megin*/SKILL.md`、`.agents/skills/megin/references/workflow-record.md`、
`.agents/skills/megin/references/branch-policy.md`、`README.md`、`OPERATIONS.md`、`megin-skills.zip`。
允許修改的工作紀錄路徑是本 Work ID 目錄；禁止修改其他產品文件、既有工作紀錄或遠端資源。

知識範圍：檢視目前十二個 Skills、工作流程紀錄契約、README、OPERATIONS、封裝驗證器與既有語言政策；
不更新 canonical project knowledge。

## 任務清單

| 任務 | 依賴 | 負責人 | 狀態 | 證據 |
| --- | --- | --- | --- | --- |
| T1 — 建立 feature 基線與 Work ID 紀錄 | — | writer | completed | 本紀錄、`requirements.md`、`plan-1/plan.md` |
| T2 — 建立共用分支政策 | T1 | writer | completed | `branch-policy.md` |
| T3 — 接入各階段 Skills 與工作紀錄規則 | T2 | writer | completed | Skills diff、`workflow-record.md` |
| T4 — 更新 README、OPERATIONS、情境與封裝 | T3 | writer | completed | feature 檔案、`implementation/verification-output.txt` |
| T5 — 新鮮唯讀審查 | T4 | fresh reviewer | completed | `review-2.md` |
| T6 — 完成前自動驗證 | T5 | writer | completed | `verification.md`、`implementation/verification-output.txt` |
| T7 — 人工驗收 | T6 | user | completed | `acceptance.md` |
| T8 — 知識檢視、feature commit 與 `--no-ff` 整合 | T7 | writer | completed | `knowledge.md`、feature commit `7c2fbdc`、`integration.md` |

## 證據

- [requirements.md](requirements.md)
- [plan-1/plan.md](plan-1/plan.md)
- [features/branch-policy.feature](features/branch-policy.feature)
- [implementation/outcome.md](implementation/outcome.md)
- [implementation/verification-output.txt](implementation/verification-output.txt)
- [review.md](review.md)
- [review-2.md](review-2.md)
- [verification.md](verification.md)
- [acceptance.md](acceptance.md)
- [knowledge.md](knowledge.md)
- [integration.md](integration.md)

## 阻礙與下一步

第二輪新鮮唯讀審查已在 `review-2.md` 回傳 `APPROVED`；完成前驗證的所有核准命令已對相同
feature 快照重新通過。`acceptance-1` 已接受，source-backed knowledge review 結果為 `no-change`，
feature implementation commit 為 `7c2fbdc6ad0c49b3dc4a4c5b31cd4f623d8bc891`，delivery evidence
commit 為 `4d472ef6ad0c49b3dc4a4c5b31cd4f623d8bc891`，並已成功以 `--no-ff` 建立 merge commit
`c814ad33864351dd1e806093735f9c7d6d58b04c`。主分支產品樹與 feature tip 一致，feature branch 保留；
本 Work ID 已完成；目前 checkout 在 `main`，feature branch `feature/work-20260921-feature-branch-delivery`
仍保留。
若日後發現整合漂移或需恢復，workflow.md 保留目前 branch、提交與下一個恢復動作的事件紀錄。

## 交付

Acceptance version：`acceptance-1`。Knowledge result：`no-change`。Feature implementation commit：
`7c2fbdc6ad0c49b3dc4a4c5b31cd4f623d8bc891`。Delivery evidence commit：
`4d472ef6ad0c49b3dc4a4c5b31cd4f623d8bc891`。Merge commit：
`c814ad33864351dd1e806093735f9c7d6d58b04c`。Merge parents、祖先關係、產品樹一致性與 feature branch
保留檢查均通過。最終狀態：`complete`。

## 事件紀錄

- 2026-09-21 — requirements/planning/approval — 使用者提供並核准 `plan-1` — 建立 Work ID、記錄 `main`
  基線與 feature branch；下一步是實作。
- 2026-09-21 — implementation — 從 `main` 的 `44e29147209099368d8eed8cc773582148c26eaa` 建立並切換到
  `feature/work-20260921-feature-branch-delivery` — 尚未修改產品檔案；下一步是接入共用政策。
- 2026-09-21 — implementation — 完成共用分支政策、各階段 Skills 接入、工作紀錄範本、README、OPERATIONS、
  行為情境與 `megin-skills.zip` — `validate_skills.py`、語言政策回歸、5 個隔離 Git 情境與 `git diff --check`
  均通過；下一步是新鮮唯讀審查。
- 2026-09-21 — review — fresh reviewer 回傳 `CHANGES_REQUIRED`，finding F1 — 自動情境需補上政策契約、
  acceptance gate、漂移停止與 workflow 恢復紀錄的檢查；下一步是 bounded fix 後重新審查。
- 2026-09-21 — implementation — 完成 F1 bounded fix，加入政策契約檢查、錯誤 branch guard、acceptance
  gate 模型與恢復證據檢查 — E1 至 E4 重新通過；下一步是以新快照重新審查。
- 2026-09-21 — review — fresh reviewer 以新快照回傳 `APPROVED`，F1 已關閉 — 下一步是重新執行
  所有核准命令並完成前驗證。
- 2026-09-21 — verification — E1 至 E4 與 branch/worktree snapshot checks 重新通過，review-2 與驗證
  對應同一 feature 快照 — 轉入 `phase: acceptance`、`status: awaiting_user`，等待 `acceptance-1`。
- 2026-09-21 — verification — acceptance handoff 建立後再次執行 E1 至 E4，結果仍為通過且沒有 staged
  paths — 維持 `phase: acceptance`、`status: awaiting_user`，等待使用者回覆 `acceptance-1`。
- 2026-09-21 — acceptance — 使用者回覆 `work-20260921-feature-branch-delivery / acceptance-1 / 接受` —
  六個核准情境通過，轉入 `phase: delivery`；下一步是 knowledge review、feature commit 與本機整合。
- 2026-09-21 — delivery — source-backed knowledge review 回傳 `no-change`，沒有 canonical promotion，
  source digest 與範圍記錄於 `knowledge.md` — 下一步是在 feature branch 建立提交。
- 2026-09-21 — delivery — 在已接受的 feature branch 建立 implementation commit `7c2fbdc`，只包含
  27 個核准路徑 — 下一步是記錄提交證據並在未漂移的 `main` 使用 `--no-ff` 整合。
- 2026-09-21 — delivery — 建立 delivery evidence commit `4d472ef6ad0c49b3dc4a4c5b31cd4f623d8bc891` 後，
  在未漂移的 `main` 執行 `git merge --no-ff` — merge commit 為
  `c814ad33864351dd1e806093735f9c7d6d58b04c`，兩個父提交、祖先關係、產品樹一致性與 feature branch
  保留均通過；Work ID 狀態改為 `complete`。
