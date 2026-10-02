Feature: Megin Group 工作區契約

  @SCN-001
  Scenario: 拒絕缺漏、重複或自相矛盾的 Group 工作紀錄
    Given 一份合法且已核准的 Group v3 工作計畫
    When workflow 標頭重複、狀態非法或 Group／Repo／交付模式與契約不一致
    Then validate-record 與所有適用的品質 gate 均以可定位的理由失敗

  @SCN-002
  Scenario: 套用選填 Group 預設而不限制可選 Repo
    Given Group 沒有設定檔、有效共用預設，或僅含部分 Repo 的覆寫
    When Megin 解析一個直接位於 Group root 下的 Git Repo
    Then request、Repo 覆寫、Group 預設與既有 Repo 探索依序決定 remote 和 base branch，未列在 overrides 的直屬 Repo 仍可選
    And 核准後修改設定檔不會改寫或重新解析此 Work ID 的基線

  @SCN-003
  Scenario: 同一 Group 只有一個寫入者且中斷鎖保留
    Given 一個已核准的 implementation work ID 已取得 Group lock
    When 另一 work ID 或不同 writer context 嘗試取得或使用此 lock
    Then 另一寫入者被拒絕，舊 writer 中斷後 lock 仍保留，只有核准完成或明確確認後可釋放

  @SCN-004
  Scenario: 驗證全部 Repo 的交接圖與完成提交
    Given 一份包含所有選定 Repo 的核准 handoff graph、測試義務及預先列出的 delivery process record
    When 合併順序遺漏 Repo、依賴循環、相容性檢查缺漏或交付 SHA 不存在
    Then delivery／completion gate 失敗
    When 所有 Repo 有有效的依序合併計畫且 commit tree 符合接受快照
    Then completion gate 可驗證真正的 feature commit 和適用的單 Repo no-ff merge
    And 部分 Repo 已完成時保留提交並交代下一步

  @SCN-005
  Scenario: 用十二個 Skills 的實際檔案內容驗證版本
    Given 來源或 Group 安裝中的十二個 Skills 檔案
    When 產生指紋、改變其中一個指令資源、或新增 Python cache
    Then 同內容指紋相同、指令內容變化要求停止續作、Python cache 不改變指紋

  @SCN-006
  Scenario: 在 Linux 和 Windows 執行相同實際工作區驗證
    Given Git 建立的隔離 Group 中包含中文及空白路徑、CRLF 檔案和 Git mode
    When 兩個 process 同時對同一 Group 要求 claim
    Then 兩個平台使用相同行為測試，恰有一個 claimant 成功，測試完成無 skipped cases
