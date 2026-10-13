# 程式碼架構與變更邊界

原先核心為 quality_gate.py / quality_policy.py 的單一 Repo 品質關卡，以及 repo_workspace.py 的工作與分支鎖。Group 能力原在 GitlabWorkSpace overlay。本次將必要能力納入 Megin，同時保留舊 schema dispatch。

| 邊界 | 實作 | 責任 |
| --- | --- | --- |
| 根目錄與遠端 | workspace_context.py | Repo/Group 盤點、遠端選定、credential-free 身分、live master SHA |
| 所有權 | workspace_lock.py | common-dir Repo 鎖、Group 主鎖、穩定取得順序、部分釋放恢復 |
| 架構基準 | source_baseline.py | 固定 commit source 的外部 scratch 探索與 frozen inventory 核對 |
| 快照 | git_snapshot.py | Git 正規化內容／mode、submodule 檢查、跨 Repo handoff DAG |
| 新流程 | unified_workflow.py | v3/v5 契約、claim/prepare、唯讀關卡、驗收後提交與續作 |
| 相容介面 | group_quality_gate.py、workspace_extension.py 及既有 CLI | --repo/--group-root 互斥與舊 schema 行為保留 |
| 證據政策 | quality_policy.py、review_history.py | 架構／計畫核准、逐情境 TDD、追加式獨立 Review |
| 套件 | install_skills.py、validate_skills.py | 未完成升級阻擋、備份與其他 Skills 保留、13 Skill 驗證及穩定 ZIP |

資料流為 frozen requirements/discovery/architecture → exact-plan approval → pinned remote/master + ownership → feature implementation snapshot → raw TDD/check/review evidence → exact human acceptance → committed feature tree → historical v2 receipt。

測試位於 tests/quality-gates：保留 52 個既有案例，新增 38 個原生流程及 2 個套件案例。整合測試使用暫存 bare remotes；模擬的 human/reviewer transcripts 僅驗證結構與阻擋條件，實際獨立 Review 另見 evidence/review-history.md。
