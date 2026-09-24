Feature: 從 GitLab Group 根目錄執行 Megin

  Scenario: SCN-001 從 Group 根目錄選取 Repo 並拒絕越界路徑
    Given Group 目錄含有兩個直屬 Git Repo
    When Megin 探索 Group 目錄並收到唯一或多個 Repo 的工作範圍
    Then 它記錄選定的 Repo 相對路徑，且無法判定時要求使用者指定
    And 它拒絕指向 Group 外部的 Repo 路徑

  Scenario: SCN-002 將一項工作紀錄集中於 Group
    Given 工作綁定至少一個 Repo
    When Megin 建立 Work ID
    Then 需求、計畫、情境與品質證據位於 Group/docs/work/<Work ID>/

  Scenario: SCN-003 驗證多 Repo 的組合快照
    Given 核准契約列出多個 Repo 與 Group 工作文件
    When 品質閘門產生快照並檢查核准、審查或驗收
    Then 每 Repo 產品內容及受保護的 Group 文件共同決定快照
    And 任一受保護內容改變會使既有證據失效

  Scenario: SCN-004 阻止遠端基線漂移後交付
    Given 工作記錄遠端基礎分支 SHA
    When 遠端不可讀或其 SHA 與核准基線不同
    Then 品質閘門阻止交付並要求重新確認基線

  Scenario: SCN-005 單 Repo 驗收後本機整合
    Given 單 Repo 工作已通過人工驗收且交付快照一致
    When Megin 建立 feature commit 並完成本機整合
    Then 本機基礎分支包含 feature commit 並保留 --no-ff merge commit

  Scenario: SCN-006 多 Repo 工作交付 feature commits
    Given 多 Repo 工作已通過同一輪人工驗收
    When Megin 逐一建立各 Repo 的 feature commit
    Then 它不合併任何基礎分支，且所有提交完成後交付合併資訊

  Scenario: SCN-007 在 Group 層安裝並續作 Megin
    Given Skills 已安裝於 Group/.agents/skills/
    When Codex 從 Group 根目錄啟動或續作 Work ID
    Then 它載入 Megin Skills 並從 Group/docs/work/<Work ID>/ 找到狀態
