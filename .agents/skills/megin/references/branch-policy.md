# Megin 分支與本機整合政策

這是所有需要開發、審查、驗證、人工驗收或交付的 Megin 工作共用的 Git 分支政策。
它定義分支身分、驗收前後的變更邊界，以及本機整合的證據要求；不新增 Megin 執行器。

## 分支生命週期

規劃完成且計畫獲得明確核准後，先從已確認的主分支提交建立一個明確命名的 feature branch。
計畫與 `workflow.md` 必須記錄 `base_branch`、`base_commit`、`feature_branch`、目前工作目錄及
`merge_strategy: --no-ff`。本 repository 的主分支是 `main`；其他 repository 依現有 Git 設定
判定主分支，若無法唯一判定才詢問使用者。

實作、測試、審查與自動驗證只能在 feature branch 進行。實作開始前確認目前 branch 等於計畫的
`feature_branch`，且建立分支時的基線等於 `base_commit`。主分支在人工驗收之前不得出現本 Work ID
的產品變更、提交或 merge。

已審查快照的產品、測試、設定、核准契約、正式文件或發佈內容變更，會使審查與驗證失效；
追加 Work ID 的純流程紀錄不改變產品快照，但已引用證據遭修改或刪除時該證據失效。
快照與證據的唯一詳細定義見 [quality-gates.md](quality-gates.md)，不得把整個 `docs/work/**` 排除。
若主分支在人工驗收後、整合前前進，先把最新主分支
整合到 feature branch，處理衝突後重新執行審查、驗證與人工驗收；不能把舊驗收套用到新快照。
未提交的無關修改、branch 身分漂移或衝突無法安全處理時，保留現場、記錄阻礙並停止，不自動
`reset`、`stash`、刪除 branch 或改寫歷史。

## 驗收後交付

人工驗收回覆必須明確包含 Work ID、acceptance version 與通過的 feature 快照。之後才可在
feature branch 執行知識檢視、暫存核准路徑並建立 feature commit。提交前再次確認 feature branch、
驗收快照、主分支目標與工作樹狀態。

feature commit 完成後切回 `base_branch`，確認目標分支仍是計畫記錄的整合基線；若目標分支已前進，
依前述規則回到 feature branch 重新整合與驗收。只有目標分支乾淨且基線未漂移時，才使用
`git merge --no-ff <feature_branch>` 建立保留整合邊界的 merge commit。推送、Pull Request、部署、
branch 刪除與 worktree 清理不屬於本地交付。

整合後確認：merge commit 有兩個父提交、feature commit 是整合結果的祖先、目標分支包含已驗收
內容，且 feature 與目標分支的產品樹一致。工作紀錄保留 branch 建立、feature commit、merge 命令、
父提交檢查與整合結果；merge SHA 以 Git merge commit 的輸出及最終交付回報保存，不為了填入自身
SHA 反覆 amend merge commit。純流程證據追加須與受驗產品內容分開辨識。

## 工作紀錄欄位

計畫與交付紀錄至少保留以下控制值：

```text
base_branch: main
base_commit: <SHA used to create the feature branch>
feature_branch: feature/<work-id>
merge_strategy: --no-ff
delivery_target: base_branch
feature_commit: <SHA after acceptance>
merge_commit: <SHA reported after integration>
```

`base_branch` 的實際名稱、SHA、分支名稱與提交識別碼保持原文；解釋與事件敘述遵循共用語言政策。
