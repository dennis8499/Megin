---
name: bug-diagnosis
description: 診斷疑似 BUG、flaky failure、效能回歸或不明工程異常：在修復前以唯讀 evidence 建立可重現訊號、最小案例、可否證根因假設與 disposition。也用於 delivery 途中發現的新 BUG；預期中的 TDD red、已分類環境 blocker、已核准修法執行與 production incident response 不適用。
---

<!-- authority: bug-diagnosis-entrypoint -->

# BUG 診斷

把「看起來壞了」收斂成可重現、可否證、可交接的 assessment。這個 Skill 只診斷，不修改 repository、產品、測試、設定、依賴或外部狀態。

## 呼叫邊界

| 輸入 | 路由 |
|---|---|
| 疑似 BUG、flaky／效能回歸、未知失敗原因 | 本 Skill，保持唯讀 |
| Active delivery 途中出現未核准異常 | 本 Skill，先保存診斷再分類 |
| 預期中的 BDD／TDD red | 回目前 execution slice |
| 已分類的環境、權限、工具 blocker | 回 Blocked recovery |
| 已有 Ready plan，要求執行核准修法 | `implementation-execution` |
| 期望行為改變而非既有行為違反 | `requirements-discovery` 的 standard feature |
| Production 止血、rollback、部署、通報、事故復盤 | Incident workflow；本 Skill 不處理 |

完成條件：輸入唯一落在一列；只有前兩列進入診斷，而且 workspace／外部狀態 bytes 維持不變。

## 1. 建立精確症狀訊號

先執行 read-only 知識 preflight：

`python -X utf8 -B .agents/skills/project-knowledge/scripts/knowledge_cli.py query --repo . --stage bug --query "<目前症狀與元件>"`

保存 `knowledge-context/v1` 作為 diagnosis evidence，並在提出假設前重讀每個 result 的 `source_refs`。這個步驟不寫回 Wiki、assessment 或產品；typed dependency／contract error 使 diagnosis 保持 Blocked。只有 Ready BOOT plan 明列 skill 尚不存在時可使用其 bootstrap exception。

記錄 observed／expected behavior、首次或最近已知正常、環境與輸入、頻率／分布、影響、severity，以及能分辨「症狀存在／不存在」的 oracle。缺 expected behavior 時先標為未知，不把推測當 BUG。

完成條件：同一操作可由另一位工程人員判斷是否出現同一症狀；severity 只影響優先與風險回報，不繞過任何 gate。

## 2. 進行 tight diagnosis loop

完整讀取 [診斷迴圈](references/diagnosis-loop.md)。依序嘗試重現或提高發生率、最小化案例、比較正常／異常與近期變更、反向追查資料流。每次 probe 只改一個變因，保存 command、輸入、輸出 digest、觀察與下一個判定。

完成條件：已證明 root cause，或有 3–5 個依 likelihood／impact 排序的可否證假設，且同時最多一個 `testing`。

## 3. 形成 assessment 與 disposition

完整讀取 [Assessment 契約](references/assessment-contract.md)；需要人類可讀內容時再讀 [模板](references/assessment-template.md)。Assessment 是 diagnosis evidence，不是 Requirements 或 Plan。

- `confirmed`／`likely`：可提議 bug delivery；在建立 worktree 前仍不得寫 repository。
- `not-a-bug`：若是 expected behavior 改變，轉 standard feature；否則結束且不建立 delivery run。
- `insufficient-evidence`：保存下一個可否證 probe，不以猜測進入修復。

開案時，assessment 與 Requirements Candidate 在第一道既有 gate 一起完整展示、一起綁定；核准後才由 delivery／requirements writer create-only materialize。途中 deferred assessment 先留在 host-temp evidence，fresh review 前或任何 terminal handoff 前由目前 delivery writer materialize。

完成條件：verdict、reproduction／root-cause status、relation、severity、風險、disposition 與 evidence refs 可由 schema 驗證；診斷 Skill 自身沒有 repository write。

## 4. 途中 BUG 分流

| Relation | 結果 |
|---|---|
| `current-scope` | 目前 diff 造成或違反已核准行為；納入同 run 的 Fixing 與驗收 |
| `affecting-current-work` | 影響成果且需改 Requirements／Plan／contract；保存後進 `Awaiting upstream reapproval` |
| `unrelated` | 不影響目前成果；不得順手改碼，只進全域 BUG inbox |

若關係證據不足，維持 `insufficient-evidence`，不得用最方便的分類擴張 scope。

## 5. 交接

交付 assessment Candidate、目前最強 evidence、已排除假設、root-cause 信心、下一個 owner 與禁止聲明。不得說「已修復」；`partial` 只由核准 Plan 與 Implementation verification 產生，且不得說「BUG 已驗證修復」。

完成條件：下一個 action 唯一為結束、standard requirements、bug delivery requirements、current-run fixing、upstream reapproval 或 deferred inbox；不自動建立 Work、issue、commit、push、merge、deploy 或通知。

## 維護本 Skill

修改本 bundle 時完整讀取 [行為驗證契約](references/behavior-evaluation.md)，執行 skill quick validation、owner validator、mutation tests、全部 forward cases與 fresh read-only review。
