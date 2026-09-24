# 計畫：Group 根目錄與多 Repo 工作流程

## 計畫資訊

- work_id: work-20260924-remote-aware-merge
- plan_version: plan-1
- requirements_revision: req-1
- base_branch: `main`
- base_commit: `86c727916d03835ea4821d0f34a69ba0d0433fe1`
- feature_branch: `feature/work-20260924-remote-aware-merge`
- workspace: `C:/Users/denni/OneDrive/Desktop/新增資料夾/Megin`
- merge_strategy: `--no-ff`
- delivery_target: 單 Repo 本機整合；本次 Megin 原始碼工作依使用者驗收後在本機 `main` 整合

本計畫修改的是獨立 Megin Skills 原始碼 Repo；Group v2 是要交付的執行模型。此原始碼維護工作沿用目前已核准的 Repo-local v1 記錄與 `--repo` 品質檢查器，供維護 Megin 本身使用。發佈後的新產品工作只從 Group root 執行並使用 Group v2。

## 變更

- 更新 Megin 入口及各階段 Skills，將 Group 根目錄作為執行根；只辨識 Group 直屬 Git Repo，以相對路徑記錄目標 Repo，所有 Git 操作明確指定 Repo。
- 新增 Group `workflow/v2` 與 `quality-contract/v2`，工作紀錄位於 `Group/docs/work/<Work ID>/`。契約列出每個 Repo 的遠端、基礎分支、基線 SHA、feature branch、允許路徑，以及執行檢查的目錄和命令。
- 擴充 `quality_gate.py`，以 `--group-root` 和 `--work-id` 讀取 Group 紀錄，檢查路徑邊界、每 Repo 產品快照、集中紀錄摘要、複合驗收快照、分支及遠端漂移。保留既有 `--repo` v1 檢查器供 Megin 本身此過渡工作與歷史品質測試使用；使用文件只公開 Group 工作模式。
- 定義單 Repo 驗收後本機 feature commit、基礎分支 fast-forward 及 `--no-ff` 合併；多 Repo 僅建立各 feature commit，所有 commit 完成後交由使用者手動合併。
- 更新 README、OPERATIONS、CI、Group 情境測試與 `megin-skills.zip`；不修改其他 Repo 或歷史 Work ID。

## 允許路徑

- `.agents/skills/megin/`
- `.agents/skills/megin-behavior-contract/`
- `.agents/skills/megin-bug-diagnosis/`
- `.agents/skills/megin-code-review/`
- `.agents/skills/megin-finishing-delivery/`
- `.agents/skills/megin-human-acceptance/`
- `.agents/skills/megin-implementation-execution/`
- `.agents/skills/megin-project-knowledge/`
- `.agents/skills/megin-requirements-discovery/`
- `.agents/skills/megin-technical-planning/`
- `.agents/skills/megin-test-driven-development/`
- `.agents/skills/megin-verification-before-completion/`
- `README.md`
- `OPERATIONS.md`
- `.github/workflows/knowledge-portability.yml`
- `megin-skills.zip`
- `tests/quality-gates/`
- `tests/group-workspace/`
- `docs/work/work-20260924-remote-aware-merge/`

禁止修改 Megin 範圍以外的 Repo、遠端資源、使用者設定及其他既有 Work ID。

## 任務

| 任務 | 依賴 | 狀態 |
| --- | --- | --- |
| T1 — 建立 Group 需求、情境與核准紀錄 | — | completed |
| T2 — 新增 Group 品質閘門回歸測試 | T1 | in_progress |
| T3 — 實作 Group v2 複合快照與 gate | T2 | pending |
| T4 — 更新分支、入口、各階段 Skills 與文件 | T1 | pending |
| T5 — 更新封裝、CI 與發佈 ZIP | T3, T4 | pending |
| T6 — 獨立唯讀審查及修正 | T5 | pending |
| T7 — 完成前驗證與人工驗收 | T6 | pending |

## 驗證命令

- `python -X utf8 -B tests/group-workspace/test_group_workflow.py`
- `python -X utf8 -B tests/quality-gates/test_quality_gate.py`
- `python -X utf8 -B tests/requirements-discovery/test_rules.py`
- `python -X utf8 -B .agents/skills/megin/scripts/validate_skills.py --archive megin-skills.zip`
- `python -X utf8 -B tests/requirements-discovery/check_materials.py`
- `python -X utf8 -B tests/requirements-discovery/test_materials.py`
- `git diff --check`

## 交接

核准依據：使用者於 2026-09-24 明確要求實作本計畫。測試與獨立審查通過後停在人工驗收；驗收以前不暫存、不提交、不合併。
