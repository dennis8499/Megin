# language: zh-TW
功能: 單一 Repo 與 Group 的遠端 master feature 交付
  所有新增情境由 tests/quality-gates/test_unified_workflow.py 和 test_skill_package.py 驗證。

  場景: 架構與精確計畫核准後才建立目標分支
    假設需求與所有 Repo 架構已有來源證據
    而且使用者核准選定 Repo、遠端 master SHA、情境與檢查
    當 writer 取得共享鎖並準備分支
    那麼只有選定 Repo 具有該 master commit 的 feature 分支
    而且未選定 Repo 及本機 master 指標保持不動

  場景: 不可用或漂移的 master 基準必須阻擋
    假設遠端只有 main，或 master 已與核准 SHA 不同
    當流程準備分支或嘗試交付
    那麼流程停止且不自動採用 main 或本機 HEAD
    而且使用者既有修改與索引被保留

  場景: 新鮮獨立 Review 與真實測試證據才可驗收
    假設 BDD 情境綁定 red/green 測試與目前組合快照
    當 red 是 setup 錯誤、reviewer 為 writer、context 被重用或快照過期
    那麼驗收關卡失敗
    而且三次修正耗盡與中斷續作不可重置 Review 歷程

  場景: 接受前禁止暫存且 checkout 不得提前執行 hooks
    假設尚未取得目前快照的使用者接受
    當分支準備完成或嘗試交付
    那麼流程不得暫存產品或流程檔案
    而且 post-checkout hook 不會改寫或暫存內容

  場景: 人工接受後只提交 feature 且可續作
    假設全部選定 Repo 已通過同一快照的獨立 Review 與驗證
    而且使用者明確接受該快照
    當多 Repo 提交中途失敗後續作
    那麼已完成 feature commit 被保留而剩餘 Repo 接續提交
    而且全部完成前鎖不被釋放
    而且 completion 驗證基準、已提交測試及驗收內容，不合併 master

  場景: 發佈包可獨立閱讀並精確重建
    當建構兩次完整 13 Skill 壓縮檔
    那麼兩個檔案位元相同
    而且 README 與 OPERATIONS 的本機連結均存在於壓縮檔
    而且新增未核准資源會被封裝驗證拒絕
