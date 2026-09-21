# 新鮮唯讀審查：feature 分支與人工審核後本機整合

## 審查範圍與快照

- Work ID：`work-20260921-feature-branch-delivery`
- 核准計畫：`plan-1`
- 審查 branch：`feature/work-20260921-feature-branch-delivery`
- 審查基線：`44e29147209099368d8eed8cc773582148c26eaa`

本次是獨立、唯讀的快照審查。除本檔案外，未修改產品檔案、未暫存、未提交，也未合併。

## 已確認事項

- `git branch --show-current` 回傳 `feature/work-20260921-feature-branch-delivery`。
- `git rev-parse main` 與 `git rev-parse feature/work-20260921-feature-branch-delivery` 均回傳 `44e29147209099368d8eed8cc773582148c26eaa`；`git log main..feature/work-20260921-feature-branch-delivery` 沒有提交。
- `git ls-tree -r --name-only main -- docs/work/work-20260921-feature-branch-delivery` 沒有輸出，且 `git diff --cached --name-status` 沒有輸出；`main` ref 未包含本 Work ID 的修改或提交。
- 變更路徑均落在 `plan-1` 列出的 `.agents/skills/megin*/SKILL.md`、共用 references、`README.md`、`OPERATIONS.md`、`megin-skills.zip` 或本 Work ID 目錄內。
- `.agents/skills/megin/references/branch-policy.md` 已涵蓋 feature branch 基線、驗收前主分支保護、快照／基線漂移、衝突與中斷保留現場，以及 `git merge --no-ff` 後的雙親與內容檢查；各需參與階段的 Skills、`workflow-record.md`、README 與 OPERATIONS 已接入相同控制值。
- `megin-skills.zip` 的完整性由 `validate_skills.py --archive megin-skills.zip` 驗證；驗證器會比對封裝的檔案集合與內容 digest，命令通過。

## 新鮮驗證證據

| Evidence | 命令／結果 |
| --- | --- |
| E1 | `python -X utf8 -B .agents/skills/megin/scripts/validate_skills.py --archive megin-skills.zip` → `validated 12 Megin Skills` |
| E2 | `python -X utf8 -B docs/work/work-20260921-requirements-language/implementation/verify_language_policy.py` → `validated language policy references for 12 Skills` |
| E3 | `python -X utf8 -B docs/work/work-20260921-feature-branch-delivery/implementation/verify_branch_policy.py` → 5 個隔離 Git 情境通過，涵蓋 feature 建立、`--no-ff` 雙親、基線漂移、衝突及中斷後 refs 保留 |
| E4 | `git diff --check` → exit status `0`、無輸出 |

## Findings

### F1 — Medium — feature 情境的自動覆蓋宣告超出驗證腳本實際範圍

**路徑：** `docs/work/work-20260921-feature-branch-delivery/features/branch-policy.feature`、`docs/work/work-20260921-feature-branch-delivery/implementation/verify_branch_policy.py`

所有 `REQ-BRANCH-001` 至 `REQ-BRANCH-006` 都把 `verify_branch_policy.py` 標示為 automatic evidence，但腳本僅建立獨立 Git repository 並驗證 Git 操作結果，沒有讀取或斷言共用政策、各階段 Skills 或 `workflow.md` 的流程約束。具體缺口如下：

- `REQ-BRANCH-001` 沒有驗證在 `main` 直接開始實作會被拒絕。
- `REQ-BRANCH-002` 沒有模擬未取得 acceptance response 的狀態，也沒有驗證此時禁止 feature commit，或確認 `main` 沒有本 Work ID 的提交。
- `REQ-BRANCH-004` 沒有驗證偵測漂移後停止、記錄具體證據，並要求重新審查、驗證及人工驗收。
- `REQ-BRANCH-005` 與 `REQ-BRANCH-006` 沒有驗證 `workflow.md` 記錄目前 branch、提交及恢復動作。

因此 E3 可證明底層 Git 語意，不能單獨證明 feature 所述的 Megin 流程行為，未符合 `megin-code-review` 對每個驗收情境具實質覆蓋的要求。

**具體修正：** 擴充 `verify_branch_policy.py`，以最小的靜態／情境檢查驗證政策、相關 Skills 與工作紀錄範本包含上述可觀察約束，並在隔離 Git 情境中加入 acceptance gate、Work ID、漂移停止及恢復紀錄的模型；或把無法自動驗證的斷言明確改為僅人工驗收，且不要將腳本列為它們的 automatic evidence。完成後重新執行 E1 至 E4，並以新快照重新審查。

## Verdict

CHANGES_REQUIRED
