# 需求：強化 Megin Group 工作區驗證與隔離

- work_id: work-20261002-group-workspace-hardening
- requirements_revision: req-1
- language: zh-TW

## 目的與邊界

讓 Megin 在 VS Code 開啟的 Group 資料夾下，能驗證工作紀錄、共用設定與已安裝 Skills 版本，並防止同一 Group 同時進行互相衝突的修改。交付仍由本機 feature branch、獨立審查、人工驗收與既有的本機整合流程完成。

本次納入：Group v3 workflow／quality contract／evidence／snapshot；必要欄位與交付證據驗證；選填的 Group 共用 remote／base branch 預設及 Repo 覆寫；單一 Group 寫入占用；多 Repo 前置依賴、合併順序與相容性檢查；Skills 套件 SHA-256 綁定；Linux 和 Windows CI 的完整行為測試。

所有 Group 直屬 Git Repo 皆可選取，共用設定不是 Repo 白名單。無設定時沿用 Repo 探索；設定只影響新計畫，核准後仍由計畫固定基線。中斷鎖不自動過期。既有已完成 v1/v2 紀錄與 Megin 本身的 v1 維護入口維持可讀。

不納入備份／還原、遠端 Git 查詢逾時調整、Subgroup、GitLab API、推送、Merge Request、自動跨 Repo 合併及修改既有歷史紀錄。

## 來源

| ID | 名稱或路徑 | 定位 | 查證日期 | 確定性 |
| --- | --- | --- | --- | --- |
| SRC-001 | 使用者核准的 `plan-1` | 本 Work ID 已核准計畫及逐項範圍決策 | 2026-10-02 | confirmed |
| SRC-002 | `.agents/skills/megin/scripts/quality_gate.py` | Group v2 欄位解析、品質契約、快照與各 gate | 2026-10-02 | confirmed |
| SRC-003 | `tests/group-workspace/test_group_workflow.py` | Group 根目錄、跨 Repo 快照及部分交付現有行為 | 2026-10-02 | confirmed |
| SRC-004 | `.github/workflows/knowledge-portability.yml` | Linux／Windows matrix 目前只在 matrix 執行封裝驗證 | 2026-10-02 | confirmed |
| SRC-005 | Python 3.13 `open()` 文件 | Windows／POSIX 共用的獨佔建立模式 | 2026-10-02 | confirmed |

## 決策與假設

| ID | 決策 | 狀態 |
| --- | --- | --- |
| Q-001 | 新 Group 工作採 v3；已完成歷史不遷移 | decided |
| Q-002 | Group 設定選填、提供預設與 Repo 覆寫、不限制 Repo 選取 | decided |
| Q-003 | 實作與交付期間整個 Group 只允許一個 Work ID；不自動回收中斷鎖 | decided |
| Q-004 | 多 Repo 合併依賴、完整且有效的合併順序與相容性檢查列為交付 gate 義務 | decided |
| Q-005 | 續作所使用 Skills SHA 與核准值不同時停止並重新確認計畫 | decided |
| Q-006 | Windows 與 Linux 執行相同完整維護測試；Group 仍只接受直屬 Repo | decided |
| Q-007 | 第 2 項紀錄備份／還原與第 3 項遠端逾時改善不在本次範圍 | decided |

## 驗收

`SCN-001` 至 `SCN-006` 見 [工作區改善情境](features/group-hardening.feature)。自動測試證明錯誤紀錄、設定、版本、占用與交接無法通過；跨平台 CI 對兩個 runner 執行同一組行為測試。完成之 Work ID 可透過已紀錄 Git commit 及其樹內容驗證。

## 探索缺口與完成判定

沒有待決的範圍或產品偏好。Group 預設從 `<Group>/.megin/group.json` 讀取；Work ID 證據使用現有 `docs/work/<Work ID>/evidence/` 格式。實作不得更改既有 v1/v2 historical records。
