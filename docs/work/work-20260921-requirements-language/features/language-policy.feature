Feature: 需求探索提問與交付文件語言

  @REQ-LANG-001
  Scenario: 廣泛需求在需求探索先停等澄清
    # automatic: manual-only (the conversation gate is not replaceable by a parser check)
    # manual_acceptance: required
    # task: T2
    # evidence: implementation/verification-output.txt, acceptance.md
    Given 使用者只提供「我想要實作一個完整實現 Quartz.Net 所有功能的 .net core 10 Template，包含前端頁面的操作」
    When Megin 開始需求探索
    Then Megin 以繁體中文提出一個最高影響的澄清問題
    And workflow.md 保持 `phase: requirements` 與 `status: awaiting_user`
    And Megin 不產生完整功能承諾或規劃文件

  @REQ-LANG-002
  Scenario: 回答仍不完整時維持需求探索
    # automatic: manual-only (the conversation gate is not replaceable by a parser check)
    # manual_acceptance: required
    # task: T2
    # evidence: implementation/verification-output.txt, acceptance.md
    Given 前一個澄清問題的回答仍未決定用途、邊界或驗收條件
    When Megin 恢復需求探索
    Then Megin 只提出下一個最高影響的澄清問題
    And Megin 不把未確認的產品選擇寫成已核准需求

  @REQ-LANG-003
  Scenario: 完整需求不追加形式問題
    # automatic: manual-only (the conversation gate is not replaceable by a parser check)
    # manual_acceptance: required
    # task: T2
    # evidence: implementation/verification-output.txt, acceptance.md
    Given 使用者已提供用途、受眾、範圍、排除項目與可觀察驗收結果
    When Megin 開始需求探索
    Then Megin 直接建立繁體中文需求文件
    And Megin 可以交接到 `phase: planning`

  @REQ-LANG-004
  Scenario: 新交付文件遵循繁體中文政策
    # automatic: python -X utf8 -B docs/work/work-20260921-requirements-language/implementation/verify_language_policy.py
    # manual_acceptance: required
    # task: T3, T4
    # evidence: implementation/verification-output.txt, acceptance.md
    Given Megin 進入任一會產出交付文件的階段
    When Megin 建立或更新該階段文件
    Then 人類可讀標題、說明、表格與事件敘述使用繁體中文
    And 技術欄位、狀態值、識別碼、路徑、指令、程式碼與 Gherkin 關鍵字保留英文
