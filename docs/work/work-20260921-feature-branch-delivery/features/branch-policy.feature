Feature: feature 分支與人工審核後本機整合

  @REQ-BRANCH-001
  Scenario: 從主分支基線建立 feature branch
    # automatic: python -X utf8 -B implementation/verify_branch_policy.py
    # manual_acceptance: required
    # task: T2, T3
    Given 工作計畫記錄主分支 `main` 與基線提交
    When Megin 開始已核准的實作
    Then Megin 建立並切換到 `feature/<work-id>`
    And Megin 拒絕在主分支直接開始實作

  @REQ-BRANCH-002
  Scenario: 人工驗收前不整合
    # automatic: python -X utf8 -B implementation/verify_branch_policy.py
    # manual_acceptance: required
    # task: T3
    Given feature branch 尚未取得人工驗收回覆
    When Megin 完成自動驗證
    Then 主分支沒有本 Work ID 的提交或 merge commit
    And Megin 不建立 feature commit

  @REQ-BRANCH-003
  Scenario: 驗收後以 no-ff 合併並保留 feature branch
    # automatic: python -X utf8 -B implementation/verify_branch_policy.py
    # manual_acceptance: required
    # task: T3, T4
    Given 使用者已回覆 Work ID 與 acceptance version 並接受 feature 快照
    When Megin 完成 feature commit 並整合回主分支
    Then Megin 使用 `git merge --no-ff`
    And merge commit 有兩個父提交且 feature branch 仍存在

  @REQ-BRANCH-004
  Scenario: 主分支漂移或已驗收快照改變時重新驗證
    # automatic: python -X utf8 -B implementation/verify_branch_policy.py
    # manual_acceptance: required
    # task: T3, T5, T6, T7
    Given 主分支在驗收後前進，或 feature 快照在驗收後改變
    When Megin 嘗試整合
    Then Megin 停止並記錄具體漂移或變更證據
    And Megin 必須重新審查、驗證與人工驗收

  @REQ-BRANCH-005
  Scenario: 整合衝突保留現場
    # automatic: python -X utf8 -B implementation/verify_branch_policy.py
    # manual_acceptance: required
    # task: T3, T4
    Given 整合發生衝突
    When Megin 無法安全完成整合
    Then Megin 不自動 reset、stash、刪除 branch 或改寫歷史
    And workflow.md 記錄目前分支、提交與下一個恢復動作

  @REQ-BRANCH-006
  Scenario: feature commit 後中斷保留恢復點
    # automatic: python -X utf8 -B implementation/verify_branch_policy.py
    # manual_acceptance: required
    # task: T3, T4
    Given feature commit 已建立但尚未整合
    When Megin 在整合前中斷
    Then 主分支仍維持原基線且 feature branch 與提交仍存在
    And workflow.md 記錄目前分支、提交與下一個恢復動作
