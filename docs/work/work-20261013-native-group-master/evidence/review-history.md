# 獨立 Review 歷程

本檔是此實作工作的真實 Review 摘要，並非供測試或流程關卡冒用的使用者驗收紀錄。每輪均為新的獨立唯讀 context。

| Round | Context | Skills SHA-256 | Verdict |
| --- | --- | --- | --- |
| 0 | /root/independent_review_0 | 4544e1f6eab9d211973e33a816a1c857f33152e99b723cf4028a5cb675482c49 | CHANGES_REQUESTED |
| 1 | /root/independent_review_1 | 95fd0c4029f7220d941bc31e8d9cbf489c8ec742e28304234bbc5993935f5d89 | CHANGES_REQUESTED |
| 2 | /root/independent_review_2 | bf872771900544bbcddbb3ada57a43f9daa7eca72624297a98a8de060a26e46e | CHANGES_REQUESTED |
| 3 | /root/independent_review_3 | edce77e62052fb7537c39bb2b6f8689dac92e4cc5d2ce1865d17fee2e12d583e | APPROVED |

## Round 0 修正

- 已保留 Review attempts 而 quality summary 遺失時，禁止重新 claim/write，避免重置三次修正上限。
- 將實際遠端 master 的 Git source objects 連結至探索證據；增加不切換產品分支的 baseline scratch 探索。
- Group TDD 測試必須屬於選定 Repo。
- SSH 遠端身分保留 username 與 SCP 相對家目錄語意。

## Round 1 修正

- 驗收前禁止暫存任何檔案，涵蓋流程紀錄。
- 提交時以命令範圍的空 hooksPath 隔離會改寫已驗收內容的 Git hooks。
- 忽略且未納入產品快照的 TDD 測試不得授權驗收；完成關卡直接驗證已提交測試檔內容。
- 補上 live completion 的遠端核對；歷史 receipt 不受後續遠端變動影響。

## Round 2 修正

- baseline/prepare 的 fetch 明確指定 --refmap=，禁止自訂 remote fetch mapping 更新或倒退本機 master。
- 分支切換隔離 post-checkout hooks，避免驗收前改寫或暫存。
- 全目標先檢查切換是否覆蓋已安裝的 Skills、設定或目前工作紀錄；有衝突先停止，保留本機內容。
- 額外修正壓縮檔文件閉合性：包含 OPERATIONS，並轉換 root 文件的本機連結。

上述缺陷均加入可重現回歸案例。Round 2 的五個新增 workflow 測試修正前全部失敗（22.705 秒），修正後連同兩個 package 測試共七項通過（17.707 秒）。套件文件測試也先重現缺少 OPERATIONS 的失敗。

## Round 3

Reviewer 對核准的雲端 master 流程回覆 APPROVED，未確認範圍內的實質缺陷。其獨立驗證了固定指紋、完整 13 Skill 壓縮檔，以及三個針對性案例（單一 Repo 交付／歷史 receipt、Group commit 後中斷恢復、升級防護；86.406 秒通過）。Reviewer 沒有修改實作、封裝或 Git 狀態，未代跑完整回歸或真實雲端認證。

已確認的非阻擋限制：workspace_context.py 的 URL 正規化拒絕沒有 hostname 的 file:///C:/... 本機遠端，即使 Git 能查詢 master；一般本機路徑可用。Reviewer 依使用者的雲端 master 範圍將此列為後續 transport 支援事項。本輪使用新的獨立唯讀 context；其 APPROVED 不等於人類驗收。

## 提交前換行正規化

使用者授權 Commit 後，git add 顯示 git_snapshot.py 的 CRLF 會被索引正規化為 LF。為避免 ZIP 與提交來源不一致，工作目錄同步改為 LF 並重建套件；Python AST（含位置）完全相同，原始／新 ZIP 逐 entry 比對僅此換行差異。本節不改寫 Review 的原始指紋或宣稱新增一輪 Review；提交用指紋與驗證詳見 [line-endings.md](line-endings.md)。
