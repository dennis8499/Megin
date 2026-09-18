# v2 派工、審查與交付收尾契約

本文件補充既有 [實作執行 Skill](../SKILL.md) 的 portable `megin` v2 path。
它不改寫 `implementation-execution/references/execution-records.schema.json` 或
任何既有 `delivery-run/v1` Ledger；v1 工作仍依原 owner contract 執行。

## 1. 受授權的單一 writer

Controller／Delivery Orchestrator 擁有 v2 state、dispatch、phase transition 與
finish handoff。產品程式與測試由一名取得 current authorization 的 implementation
writer 執行；writer 可以是受監督的 implementation subagent，也可以在沒有子代理
能力時由 controller 以相同規則循序執行。

Dispatch package 必須綁定以下內容：

- `work_id`、state revision、task class 與 exact current checkout／worktree／branch identity；
- 已核准的 design／requirements／plan digest、驗收與來源；
- 這個 work package 的允許修改路徑、不得修改的路徑與必要 interfaces；
- focused、related、full verification commands 及報告位置；
- knowledge scope、finish destination 與回報格式。

Writer 只能在 dispatch package 宣告的範圍內寫入。每個 workspace 同一時間最多
一名 writer；不得平行啟動兩個會修改相同 repository、workspace 或 state 的 writer。
新的 writer 必須等待前一份結果以 create-only assignment／result 回寫並由
Controller 重新授權；writer 不自行再委派工作，也不能以 prompt、branch 名稱、
檔案路徑或子代理名稱取得寫入權。循序多工作包會保存上一份 assignment 的 baseline
dirty paths 與每個 baseline path 的內容／mode digest；後續 writer 只能保留這些精確
bytes，若改動先前 work package 的檔案就會被阻擋。最後的 review 仍涵蓋整個未提交
workspace。

Writer 回報 `completed`、`needs_revision`、`blocked` 或 `awaiting_upstream`，
並附 changed paths、測試輸出、疑慮與下一步。Controller 只把符合 dispatch package
的結果寫入 state；越界或無法證明的結果停止在 review／blocked，不能默認接受。

## 2. TDD、fresh review 與 bounded fix loop

每個新增行為仍遵守 outside-in BDD、inner TDD、focused／related tests，再執行
核准的 full validation。先有能表達驗收的失敗測試，再做最小 production change，
每次重構保持綠燈；沒有可靠 red 或驗收與目前 scope 不符時回到 upstream planning。

Implementation 完成後，Controller 啟動一個新的 read-only Reviewer session。Reviewer
必須直接讀取目前 diff、核准來源、測試與原始 outputs，不接收 implementation
conversation、writer 辯護、預期 verdict 或前一位 Reviewer 的結論；Reviewer 不可
寫入、安裝依賴、提交 Git、發佈或再委派 subagent。

Reviewer 必須確認：

1. 所有核准驗收與 scope 都有實作、測試與 code evidence；
2. 必要 commands 已執行且結果新鮮，`failed`、`blocked`、`not_run` 不能支持通過；
3. diff、state、knowledge scope 與 finish destination 沒有 drift 或秘密洩漏；
4. review snapshot before／after 相同，且 findings 可由 evidence 重算。

Reviewer 回傳 `APPROVED`、`CHANGES_REQUIRED` 或 `BLOCKED`。`CHANGES_REQUIRED`
只交回同一個 authorized writer 修正；修正後以新的 assignment、測試 evidence、
snapshot 與 fresh Reviewer round 重新驗證。沿用既有進展式 breaker：同一 blocking
finding 沒有實質進展時停止並回報 blocked，不靠無限重試或更換文字重置計數。沒有
fresh Reviewer capability 時，v2 run 停在 `blocked`，或在能力尚未提供時維持
`implementation` phase 並等待 reviewer handoff。

## 3. Automatic knowledge review

v2 approval 的 `knowledge_scope` 是本次交付的明確授權邊界。Implementation review
通過後，Controller 以核准 scope 產生 create-only knowledge candidate，保存來源、
確定性、pre/post snapshot、操作與 payload digest，再由獨立 fresh review 檢查產品
與 knowledge 兩棵樹的結果。

Candidate 通過 schema、source、lint、snapshot 與 scope 檢查後，v2 可自動套用
核准範圍內的 knowledge update，並把結果、digest 與 review evidence 綁進同一個
finish handoff。來源不足、衝突、scope drift、lint 失敗或任何 reviewer blocking
finding 都停止在 `blocked`；不得寫入 canonical knowledge，也不得
把測試成功當成 knowledge approval。

這是 v2 的自動知識審查／回寫行為。v1 的 Project Knowledge Candidate 仍須依
`draft → candidate → review → explicit human approval → apply` 生命週期與原本的
Knowledge promotion gate；v2 不會將舊 Candidate 或 v1 approval 自動升格。

## 4. Git finish handoff

Finish 只在 implementation review、knowledge review（若有 scope）與完整驗證通過
後執行。它是 v2 `finish` command 的唯一交付出口，且每一步都以 state identity、
approved path set 與 current snapshot 做 preflight。

新工作預設 `finish_mode=unstaged`。此模式完成 preflight、驗證與 knowledge review 後，
保留目前 feature branch 的修改，不執行 `git add`、commit、push 或 PR；保存 changed
paths、snapshot 與根據 approved request 產生的建議 commit message。若 index 已有 staged
內容，或 HEAD 已經改變，finish fail closed，不自動復原使用者操作。

`finish_mode=commit` 或 `finish_mode=draft-pr` 才執行以下 Git handoff：

1. 只 stage approved product、test、文件與已通過 review 的 knowledge paths；
2. 建立一個可重算的 commit，保存 commit SHA、changed paths 與驗證 evidence；
3. 若 state 指定 remote 且認證／網路可用，push 目前 delivery branch；
4. 推送成功後建立或重用該 branch 的 draft pull request，保存 PR identity 與 URL；
5. 結果分別記為 `local_verified`、`delivered_unstaged`、`committed`、`pushed`、
   `draft_pr_created` 或 `publication_pending`，不得把較早的狀態誤報為完成。

缺少 remote、認證或網路時保留本地 commit 與 state，讓 `resume`／`finish` 只重試
未完成的發布步驟；若 branch 已有相同 head 的 draft PR，重用它，不建立重複 PR。
Merge、deployment、worktree cleanup 與刪除仍是獨立動作，不由 v2 finish 自動執行。

Finish handoff 要提供問題、結果、驗證、review／knowledge 摘要、commit／branch、
publication state、待決事項與 state path。Git hook、外部服務回應與秘密不得寫入
state；只保存必要的遮蔽摘要、exit、byte count、digest 與可追溯 evidence。

## 5. v1 compatibility

既有 v1 implementation contract 仍以主代理唯一 writer、host-temp Ledger、fresh
read-only Reviewer，以及不自動 stage／commit／push／merge／deploy／cleanup 為準。
只有明確標記 `delivery-run/v2` 且經 v2 dispatch authorization 的新 run 才啟用本
文件的 delegated writer、automatic knowledge review 與 Git finish handoff。
