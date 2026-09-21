# 計畫 1：需求探索詢問與交付文件語言

## 摘要

需求修訂：`requirements-1`。

新增單一共用語言政策，將重大未知的提問與停等規則寫入入口、需求探索及技術規劃，並讓所有交付階段直接引用同一政策。更新 workflow 範本的可讀文字，重建並驗證技能封裝。

## 實作工作包

### T2 — 共用政策與需求停等規則

- 新增 `.agents/skills/megin/references/language-policy.md`，定義人類可讀內容、AI 指令及技術控制值的語言邊界，並定義需求探索的停等狀態。
- 更新 `.agents/skills/megin/SKILL.md`，在入口規則中要求先判斷重大未知，並引用語言政策。
- 更新 `megin-requirements-discovery/SKILL.md`，明確規定重大未知時只問一題、以繁體中文提問、更新 `awaiting_user`，等待回答後再繼續。
- 更新 `megin-technical-planning/SKILL.md`，拒絕未完成需求的規劃交接，並引用語言政策。

### T3 — 所有階段的文件語言引用

- 在 behavior contract、bug diagnosis、project knowledge、implementation、TDD、code review、verification、human acceptance、finishing delivery 等 Skills 加入政策引用。
- 保留每個 Skill 的英文操作指令與控制欄位，僅將它產出的可讀文件規則指向繁體中文政策。

### T4 — 範本與封裝

- 更新 `.agents/skills/megin/references/workflow-record.md` 的範例說明與區段描述為繁體中文，保留 schema、欄位鍵、狀態值與狀態轉移語法。
- 執行既有封裝流程重建 `megin-skills.zip`，不得加入未列入來源的額外檔案。

## 允許與禁止路徑

允許：十二個 `.agents/skills/megin*/SKILL.md`、`.agents/skills/megin/references/language-policy.md`、`.agents/skills/megin/references/workflow-record.md`、`megin-skills.zip` 及本 Work ID 文件。禁止：README、OPERATIONS、既有 Work ID、Quartz.NET 專案、遠端資源與未列出的產品路徑。

## 驗證命令與證據

- `python -X utf8 -B .agents/skills/megin/scripts/validate_skills.py --archive megin-skills.zip`
- 工作紀錄結構、語言政策引用與停等規則檢查（記錄於 `implementation/verification-output.txt`）
- `git diff --check`
- 以 Quartz.NET 廣泛描述及完整需求描述進行人工情境驗收；記錄於 `acceptance.md`

## 知識與交付

知識範圍僅檢視來源 Skills、工作流程契約與封裝驗證器；結果預期為 `no-change`。完成新鮮唯讀審查、所有自動驗證與使用者人工驗收後，在 `main` 建立一個本機提交。
