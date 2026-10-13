# Megin 0.7.0 實作需求

本工作依使用者的「PLEASE IMPLEMENT THIS PLAN」及其完整計畫執行。這些文件記錄套件維護與驗證，不是新流程的可執行 quality-contract，也不代表使用者已接受實作成果。

- REQ-001：需求探索後加入獨立程式碼架構探索，才制定計畫與取得該版本人工核准。
- REQ-002：原生套件提供單一 Repo 與 Group；探索所有有效直屬 Repo，只修改與建立分支於核准目標。
- REQ-003：每個目標固定遠端身分及 refs/heads/master 的完整 SHA；核准後 fetch/recheck，建立 feature/<Work ID>，不改用 main 或本機 HEAD。
- REQ-004：BDD 情境、TDD red/green、驗證與人工驗收綁定同一快照；初審 round 0 加最多三次修正，每次獨立唯讀 context，續作不重置。
- REQ-005：兩模式共用 Git common-dir Repo 鎖；Group 另持主鎖；跨 Repo 有依賴順序、相容性與組合快照驗證。
- REQ-006：人工接受後才能暫存／建立 feature commit；不合併、不推送；部分多 Repo 提交可續作。
- REQ-007：舊契約保留相容性，未完成工作阻擋升級；新版 receipt v2；13 Skills、文件、CI 及可重現 ZIP 同步。

GitLab Issue/MR 與新版 MergeReviewer receipt 消費端不在本次範圍。Linux 執行需由 CI 提供；本機驗證不冒稱 Linux 已通過。
