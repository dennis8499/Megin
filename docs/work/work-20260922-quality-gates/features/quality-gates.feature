Feature: Megin 品質關卡的可核對交接

  @QG-001 @review
  Scenario: 行為證據指出真正的斷言
    Given 核准情境含可觀察結果與測試命令
    When writer 只提供編譯失敗作為 Red
    Then 不得宣稱該結果已有行為 Red 證據

  @QG-002 @human
  Scenario: 自身修改需要獨立審查
    Given writer 已提交唯讀審查交接
    When 沒有不同上下文的 reviewer 原始結果
    Then 工作保持 awaiting_review，不能標記為 APPROVED

  @QG-003 @human
  Scenario: Reviewer 核對測試的證明力
    Given 情境要求 recovery 或 Kafka 持久化後才提交 offset
    When 測試只檢查設定值或直接以 consumer 提交 offset
    Then reviewer 指出尚未證明的行為與需要的可觀察斷言

  @QG-004 @automatic
  Scenario: 未完成的必要驗證阻擋驗收
    Given 計畫要求執行一項測試
    When 測試失敗、受阻、零命中、跳過或沒有結果
    Then acceptance gate 不通過並列出具體原因

  @QG-005 @automatic
  Scenario: 快照區分產品與流程紀錄
    Given 產品快照已受審
    When 新增未追蹤產品檔案或更改核准契約
    Then 舊核准失效
    When 只追加合法流程紀錄
    Then 產品快照維持相同

  @QG-006 @human
  Scenario: 工作包可恢復
    Given 一個工作包已結束
    When 下一個 writer 或 reviewer 接手
    Then 可從紀錄辨識完成內容、驗證、缺口及下一步
