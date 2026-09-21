# 計畫：補齊 feature 分支與人工審核後合併流程

## 計畫資訊

- plan_version: `plan-1`
- requirements_revision: `requirements-1`
- base_branch: `main`
- base_commit: `44e29147209099368d8eed8cc773582148c26eaa`
- feature_branch: `feature/work-20260921-feature-branch-delivery`
- workspace: `C:/Users/denni/OneDrive/Desktop/新增資料夾/Megin`
- merge_strategy: `--no-ff`
- delivery_target: `base_branch`（本機 `main`）

## 實作變更

- 新增 `.agents/skills/megin/references/branch-policy.md`，集中定義基線、feature branch、驗收前後
  邊界、主分支漂移、衝突、中斷恢復與 `--no-ff` 整合證據。
- 更新入口、需求探索、技術規劃、實作、審查、驗證、人工驗收與交付 Skills，使每一階段引用同一
  分支政策並拒絕不符合 branch 或快照條件的交接。
- 更新 `workflow-record.md`、README 與 OPERATIONS，加入分支控制值、驗收前主分支保護、feature
  commit、merge commit 與整合檢查。
- 建立 `features/branch-policy.feature` 與隔離 Git 驗證腳本，實際核對分支、SHA、提交父關係、
  漂移、衝突與中斷恢復；重建 `megin-skills.zip`。

## 允許與禁止路徑

允許修改：`.agents/skills/megin*/SKILL.md`、`.agents/skills/megin/references/workflow-record.md`、
`.agents/skills/megin/references/branch-policy.md`、`README.md`、`OPERATIONS.md`、`megin-skills.zip`，
以及本 Work ID 目錄。禁止修改既有 Work ID、遠端資源、其他產品檔案與歷史提交。

## 任務

| 任務 | 依賴 | 負責人 | 狀態 | 證據 |
| --- | --- | --- | --- | --- |
| T1 — 建立 feature 基線與 Work ID 紀錄 | — | writer | completed | `workflow.md`、`requirements.md`、本計畫 |
| T2 — 建立共用分支政策 | T1 | writer | in_progress | `branch-policy.md` |
| T3 — 接入各階段 Skills 與工作紀錄規則 | T2 | writer | pending | Skills diff、`workflow-record.md` |
| T4 — 更新 README、OPERATIONS、情境與封裝 | T3 | writer | pending | `features/branch-policy.feature`、驗證輸出 |
| T5 — 新鮮唯讀審查 | T4 | fresh reviewer | pending | `review.md` |
| T6 — 完成前自動驗證 | T5 | writer | pending | `verification.md` |
| T7 — 人工驗收 | T6 | user | awaiting_user | `acceptance.md` |
| T8 — 知識檢視、feature commit 與 `--no-ff` 整合 | T7 | writer | pending | `knowledge.md`、整合證據 |

## 驗證命令

- `python -X utf8 -B .agents/skills/megin/scripts/validate_skills.py --archive megin-skills.zip`
- `python -X utf8 -B docs/work/work-20260921-feature-branch-delivery/implementation/verify_branch_policy.py`
- `python -X utf8 -B docs/work/work-20260921-requirements-language/implementation/verify_language_policy.py`
- `git diff --check`
- `git status --short --branch`、`git diff --name-only`、分支與提交祖先檢查

## 交接規則

所有核准內容與命令綁定本計畫與 feature branch。人工驗收以前不得暫存、提交或整合；任何快照或
主分支基線變更都回到實作、審查、驗證與人工驗收。自動驗證通過後停在 `phase: acceptance`、
`status: awaiting_user`，等待使用者以 Work ID 與 acceptance version 回覆。
