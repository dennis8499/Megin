# Megin 工作流程紀錄

每個工作項目使用一個目錄：`docs/work/<work-id>/`。必要的控制紀錄是 `workflow.md`；需求、計畫、
行為 feature、實作證據、審查、驗證、驗收與知識筆記放在同一目錄。這是人類可讀的紀錄，不是
隱藏的執行期資料庫，也不是歷史 delivery-run 紀錄的相容層。請先讀取
[language-policy.md](language-policy.md)，以繁體中文撰寫可讀內容並保留技術控制值。

## 必要標頭

```markdown
# Megin 工作流程：<short title>

- schema: megin-skills-workflow/v1
- work_id: work-YYYYMMDD-<lowercase-slug>
- repository: <repository root>
- base_commit: <full SHA>
- branch: <current branch or `pending-approval`>
- route: read_only | small | large | bug
- phase: requirements | planning | approval | implementation | review | verification | acceptance | delivery
- status: active | awaiting_user | awaiting_review | blocked | complete
- plan_version: <version or pending>
- last_updated: YYYY-MM-DD
```

使用穩定的小寫 Work ID。不得重用舊 Work ID 或舊核准。保留基線提交與分支，讓後續恢復時可以
偵測漂移。標頭中的 schema、鍵、狀態值與識別值維持英文，標題與說明使用繁體中文。

## 區段

每份紀錄都保留以下區段，並在原處更新內容、追加有日期的事件：

```markdown
## 目的與邊界
目標、受眾、納入範圍的行為與路徑、排除範圍、假設及風險。

## 驗收
穩定的情境 ID、可觀察的預期結果、自動命令及使用者可見的人工步驟。

## 計畫與核准
計畫版本、允許路徑、介面、依賴、測試命令、知識範圍、交付目的地、核准文字、核准回應及核准日期。

## 任務清單
| 任務 | 依賴 | 負責人 | 狀態 | 證據 |
| --- | --- | --- | --- | --- |

## 證據
原始命令輸出、審查報告、快照、feature 檔案及來源參考的路徑。專案契約要求時，記錄命令、結束
狀態、時間戳記及摘要。

## 阻礙與下一步
一個附有證據的具體阻礙，或最早的下一步及其負責人。

## 交付
驗收版本、知識結果、已暫存路徑、提交識別碼及最終狀態。

## 事件紀錄
追加 `YYYY-MM-DD HH:MM — phase — action — result — next action` 項目。不得改寫舊核准或裁決；以新的
計畫／審查版本取代，並說明原因。
```

## 狀態轉移

`requirements → planning → approval → implementation → review → verification → acceptance → delivery`

`read_only` 與 `bug` 診斷可以不進入實作而結束。審查或驗證失敗時回到受影響的實作任務，並需要
新的審查及新的驗證。範圍或驗收條件改變時建立新的計畫版本並重新核准。知識只在驗收後，且僅對
核准的來源範圍進行提升。

需求探索若發現用途、受眾、邊界、排除項目或驗收仍有重大未知，保持
`phase: requirements` 與 `status: awaiting_user`，以繁體中文提出一個問題並等待回答；未完成前
不得交接到 `planning`。
