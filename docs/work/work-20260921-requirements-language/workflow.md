# Megin 工作流程：需求探索詢問與交付文件語言

- schema: megin-skills-workflow/v1
- work_id: work-20260921-requirements-language
- repository: C:/Users/denni/OneDrive/Desktop/新增資料夾/Megin
- base_commit: db669c7db35af31ab6fc22c63d4f0eca8c60da63
- branch: main
- route: large
- phase: delivery
- status: complete
- plan_version: plan-1
- last_updated: 2026-09-21

## 目的與邊界

本次變更修正 Megin Skills-only 流程的需求探索與交付文件語言。當需求的用途、使用者、功能邊界或驗收條件仍有重大未知時，流程必須用繁體中文提出一個最高影響問題並等待回答；在回答前不得完成需求整理或進入規劃。所有新產出的交付文件以繁體中文撰寫，AI 技能指令與技術控制值保留英文。

範圍包含十二個 Skills 的規則、共用語言政策、工作流程紀錄範本、可執行情境與 `megin-skills.zip`。Quartz.NET 需求只作為驗收案例，不實作 Quartz.NET Template，也不翻譯既有 README、OPERATIONS 或歷史工作紀錄。

## 驗收

需求修訂：`requirements-1`。情境 `REQ-LANG-001` 至 `REQ-LANG-004` 詳見 [features/language-policy.feature](features/language-policy.feature)。自動驗證需通過來源與封裝檢查、文件規則檢查及 `git diff --check`；互動驗收需確認廣泛需求會先提問、未完整回答會繼續停留在需求探索，以及完整需求不會被迫追加無意義問題。

| 情境 | 任務 | 自動驗證 | 人工驗收 | 證據 |
| --- | --- | --- | --- | --- |
| `REQ-LANG-001` | T2 | 僅規則靜態檢查 | 必要 | `implementation/verification-output.txt`、`acceptance.md` |
| `REQ-LANG-002` | T2 | 僅規則靜態檢查 | 必要 | `implementation/verification-output.txt`、`acceptance.md` |
| `REQ-LANG-003` | T2 | 僅規則靜態檢查 | 必要 | `implementation/verification-output.txt`、`acceptance.md` |
| `REQ-LANG-004` | T3、T4 | `verify_language_policy.py` | 必要 | `implementation/verification-output.txt`、`acceptance.md` |

## 計畫與核准

計畫版本：`plan-1`。使用者在 2026-09-21 以「PLEASE IMPLEMENT THIS PLAN」明確要求執行前一則完整計畫；本 Work ID 將該計畫綁定為目前執行目標。

允許修改的產品路徑：`.agents/skills/megin*/SKILL.md`、`.agents/skills/megin/references/workflow-record.md`、`.agents/skills/megin/references/language-policy.md`、`megin-skills.zip`。允許修改的工作紀錄路徑是本 Work ID 目錄。禁止修改其他產品文件、既有工作紀錄、Quartz.NET 專案或遠端資源。

知識範圍：檢視目前十二個 Skills、工作流程紀錄契約、封裝驗證器與現有 README/OPERATIONS；不更新 canonical project knowledge。

核准命令：

- `python -X utf8 -B .agents/skills/megin/scripts/validate_skills.py --archive megin-skills.zip`
- Work ID 文件規則檢查腳本
- 文件語言與需求停等規則檢查腳本
- `git diff --check`

交付目的地：同一個 `main` 工作樹的單一本機提交；不推送、不建立 PR、不整合遠端分支。

## 任務清單

| 任務 | 依賴 | 負責人 | 狀態 | 證據 |
| --- | --- | --- | --- | --- |
| T1 — 建立基線、需求與情境 | — | writer | completed | requirements.md、features/language-policy.feature |
| T2 — 新增共用語言政策與需求停等規則 | T1 | writer | completed | 技能來源 diff |
| T3 — 將語言政策引用接到所有階段 Skills | T2 | writer | completed | 技能來源 diff |
| T4 — 更新 workflow 範本並重建封裝 | T2、T3 | writer | completed | implementation/outcome.md |
| T5 — 新鮮唯讀審查 | T4 | fresh reviewer | completed | review.md |
| T6 — 驗證與人工驗收 | T5 | writer/user | completed | verification.md、acceptance.md |
| T7 — 知識檢視與本機提交 | T6 | writer | completed | knowledge.md、提交識別碼 |

## 證據

- [requirements.md](requirements.md)
- [plan-1/plan.md](plan-1/plan.md)
- [features/language-policy.feature](features/language-policy.feature)
- [implementation/outcome.md](implementation/outcome.md)
- [implementation/verification-output.txt](implementation/verification-output.txt)
- [review.md](review.md)
- [verification.md](verification.md)
- [acceptance.md](acceptance.md)
- [knowledge.md](knowledge.md)

## 阻礙與下一步

目前沒有阻礙。`acceptance-1` 已通過，source-backed knowledge review 結果為 `no-change`，單一本機提交已建立並完成最終紀錄。

## 交付

Acceptance version：`acceptance-1`。Knowledge result：`no-change`，沒有 canonical promotion。所有 staged paths 都在 plan-1 允許範圍內。第一個提交為 `177ad6734b9fab8ec83290897e0719915519f5a3`；最終 commit identity 以本紀錄 amend 後 `git rev-parse HEAD` 的值為準。狀態：`complete`。

## 事件紀錄

- 2026-09-21 — requirements/planning/approval — 使用者要求執行已提出的「修正需求探索與交付文件語言」計畫 — 建立 Work ID、綁定 `plan-1` 與基線；下一步是實作。
- 2026-09-21 — implementation — 完成共用語言政策、需求停等規則、所有階段引用、workflow 範本與封裝重建 — 規則檢查、封裝驗證、ZIP CRC 與 `git diff --check` 通過；下一步是新鮮唯讀審查。
- 2026-09-21 — review — fresh reviewer 回傳 `CHANGES_REQUIRED` — 修正入口分類順序、補上四個情境的命令／人工驗收／任務／證據映射，並建立 `implementation/verification-output.txt`；下一步是重新審查。
- 2026-09-21 — review — fresh reviewer 以最新快照回傳 `APPROVED` — 三項 finding 均已關閉；下一步是完成前驗證。
- 2026-09-21 — verification — `verification-1` 的語言政策、Skills 封裝、ZIP CRC 與差異檢查均通過 — 轉入 `phase: acceptance`、`status: awaiting_user`，等待 `acceptance-1`。
- 2026-09-21 — acceptance — 使用者回覆 `work-20260921-requirements-language / acceptance-1 / 接受` — 四個核准情境通過，轉入 `phase: delivery`；下一步是知識檢視與本機提交。
- 2026-09-21 — delivery — source-backed knowledge review 回傳 `no-change`，沒有 canonical promotion — 下一步是只暫存 plan-1 允許路徑並建立單一本機提交。
- 2026-09-21 — delivery — 建立本機提交 `177ad6734b9fab8ec83290897e0719915519f5a3`，只包含 27 個核准路徑 — 更新本紀錄為 `status: complete`，再以同一提交 amend 最終交付資訊。
