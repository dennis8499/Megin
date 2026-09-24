# 需求：從 GitLab Group 根目錄執行 Megin

- work_id: work-20260924-remote-aware-merge
- requirements_revision: req-1
- language: zh-TW

## 目的與邊界

讓 Megin 從不屬於 Git Repo 的 Group 根目錄執行，並操作 Group 直屬的一個或多個 Repo。新工作紀錄集中於 `docs/work/<Work ID>/`；一份 Work ID 可以涵蓋多個 Repo。

納入：Group 根目錄技能安裝與發現、Repo 選取與路徑隔離、集中工作紀錄、跨 Repo 複合快照與品質閘門、遠端分支漂移處理、單 Repo 本機整合、跨 Repo feature commit 交接、技能文件與套件更新。

排除：GitLab API、推送、Merge Request、自動跨 Repo 合併，以及 Test/Test2 的既有紀錄遷移。

## 來源

| ID | 名稱或路徑 | 定位 | 查證日期 | 確定性 |
| --- | --- | --- | --- | --- |
| SRC-001 | 使用者核准計畫 | 本次對話中的完整計畫內容 | 2026-09-24 | confirmed |
| SRC-002 | `.agents/skills/megin/references/branch-policy.md` | 現有 feature branch 與本機整合規則 | 2026-09-24 | confirmed |
| SRC-003 | `.agents/skills/megin/scripts/quality_gate.py` | 現有單一 Repo 品質閘門 | 2026-09-24 | confirmed |
| SRC-004 | OpenAI Skills 文件 | Group 工作目錄的 `.agents/skills` 發現規則 | 2026-09-24 | confirmed |
| SRC-005 | Git `ls-remote` 與 `merge` 文件 | 遠端參照與 `--no-ff` 語義 | 2026-09-24 | confirmed |

## 決策與假設

| ID | 決策 | 狀態 |
| --- | --- | --- |
| Q-001 | Group 根目錄不是 Git Repo；Skills 放在 `Group/.agents/skills/` | decided |
| Q-002 | 新紀錄放在 `Group/docs/work/<Work ID>/`，以本機檔案保存 | decided |
| Q-003 | 新版僅支援 Group 根目錄；不處理 Test/Test2 | decided |
| Q-004 | 一個 Work ID 可包含多個 Repo；遠端只讀檢查，不推送 | decided |
| Q-005 | 單 Repo 驗收後本機 `--no-ff` 合併；多 Repo 建立 feature commits 後交使用者手動合併 | decided |
| Q-006 | 遠端無法確認或基線漂移時停止，不沿用舊驗收 | decided |

## 驗收

- `SCN-001`: 從 Group 根目錄只選取直屬 Git Repo，模糊時要求指定，不接受逸出 Group 的路徑。
- `SCN-002`: 新 Work ID 的需求、計畫、情境與證據全部寫入 Group 的 `docs/work/<Work ID>/`。
- `SCN-003`: 品質閘門以 Group 相對紀錄與每個 Repo 的核准路徑計算複合快照，變更任一受保護內容都會使證據失效。
- `SCN-004`: 各 Repo 記錄遠端、基礎分支、基線 SHA 與 feature branch；遠端不可讀或漂移會阻止交付。
- `SCN-005`: 單 Repo 交付建立 feature commit，再快轉本機基礎分支並執行 `--no-ff` 合併，驗證父提交與內容。
- `SCN-006`: 多 Repo 交付逐 Repo 建立 feature commit，不合併基礎分支；部分提交可續作並保留逐 Repo 狀態。
- `SCN-007`: 發佈 ZIP 可安裝至 Group `.agents/skills/`，文件說明 Group 層啟動與續作。

## 探索缺口與完成判定

所有高影響決策已由使用者在本次對話中決定。驗收須涵蓋暫存 Group、至少兩個 Repo、遠端漂移與兩種交付模式。
