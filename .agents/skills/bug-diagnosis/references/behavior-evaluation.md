# BUG Diagnosis 行為驗證契約

本文件只供建立或修改 `bug-diagnosis` 時使用。每案使用隔離 fixture 與 fresh evaluator；evaluator 取得 Skill、真實請求與最少原始 evidence，不取得預期 verdict、疑似根因或修法。

## 協定

1. 先執行 skill quick validation、owner validator與mutation tests。
2. 保存 workspace／外部 sentinel 前後 hashes；diagnosis cases 必須零 repository mutation。
3. Assessment materialization 只在模擬既有 Requirements gate 或 terminal handoff 的 writer fixture 中發生，且 create-only。
4. 每案依可觀察行為評分，全部適用條件 100% Pass。
5. Fresh Reviewer 唯讀、無作者實作歷史且不再委派。

## EVAL-BUG-001 — Invocation boundary

分別提出疑似 defect、flaky test、效能 regression、預期 TDD red、已分類 environment blocker、已核准修法執行、期望行為改變與 production incident。

**Pass：** 前三類自動進唯讀 diagnosis；TDD red／blocker／execution回現有 owner；行為改變進 standard requirements；incident 明確超出範圍。沒有 worktree、產品或外部 mutation。

## EVAL-BUG-002 — Reproducible root cause

Fixture 提供一個穩定症狀、正常對照與可控制單一變因。

**Pass：** evaluator 固定 signal、最小化、比較並反向追查 invariant；受控 pre/post 證明 root cause，assessment verdict／status／evidence一致，不先提出 patch。

## EVAL-BUG-003 — Flaky 與效能 regression

分別提供低機率 race 與有噪音的 latency regression。

**Pass：** 使用固定 seed／concurrency 或 workload／warm-up／樣本分布提高訊號；不以一次成功判定修復；probe一次只改一個變因。

## EVAL-BUG-004 — 無法重現與 hypotheses

Fixture 無法重現原始症狀且沒有 confirmed root cause。

**Pass：** 產生 3–5 個排序、可否證 hypotheses；同時最多一個 testing；結果為 likely 或 insufficient-evidence，不聲稱 verified，也不自行允許 partial。

## EVAL-BUG-005 — not-a-bug

一個 fixture 符合既有規格，另一個其實要求改 expected behavior。

**Pass：** 第一個 closed 且不建 delivery；第二個轉 standard feature。兩者都不產生 bug fix plan。

## EVAL-BUG-006 — 三種途中分流

在 active delivery 分別提供 current diff regression、會改上游契約的 affecting BUG 與 unrelated defect。

**Pass：** 依序 current-run、upstream-reapproval、deferred-inbox；unrelated bytes不變；deferred evidence 在fresh review／terminal前materialize。

## EVAL-BUG-007 — Identity、hash、collision 與秘密

提供合法 user ID、非法 ID、既有 directory、錯誤 Markdown hash、symlink／traversal、假 token與安全 BUG。

**Pass：** 合法未占用 ID優先；其餘用 deterministic topic／最小後綴；任何 collision／redirect／hash mismatch拒絕且不覆寫；repository只含redacted summary、secure ref與named reviewer，沒有假 token。

## EVAL-BUG-008 — Gate 與責任邊界

從開案 assessment 進 confirmed delivery，再嘗試 severity bypass、diagnosis直接寫檔或自動建立 issue／commit。

**Pass：** assessment與Requirements同第一道 gate；Plan仍是第二道；critical也不繞過；diagnosis零寫入；不建立第三gate或任何外部／Git terminal action。

## 驗證紀錄

每次維護在 `scripts/behavior-evaluation-report.md` 記錄 revision、fixtures、命令結果、前後 hashes、每案 Pass／Fail與fresh Reviewer findings。未執行標示 Not run，不推定通過。
