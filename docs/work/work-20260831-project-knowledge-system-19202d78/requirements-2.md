# 需求分析：單一專案可信工程知識系統

- 文件狀態：`Ready`
- 日期：2026-09-01
- 文件範圍：擴充現有 SDLC Skills，提供單一 repository 的知識檢索、萃取、晉升與維護閉環
- 需求來源：使用者決策、目前 `.agents/skills` 工作流與 Git 設定、LLM Wiki、mattpocock/skills、Superpowers、OpenSpec、Spec Kit，以及 2026-09-01 使用者明示排除 macOS 的範圍決策
- 確認者：使用者（2026-09-01 明確回覆「同意」）

## 1. 執行摘要

### 問題或機會

目前需求、計畫、實作與 BUG 流程能產生具追溯性的個別產物，但缺少跨工作累積的知識層。Agent 每次進入新工作時仍需重新搜尋、閱讀與綜整，也沒有可靠機制把已完成工作的決策、現況與經驗萃取成後續可直接利用的知識。

### 為何現在做

現有流程已具備 Ready requirements、Ready plan、Complete implementation、BUG verification 與人工核准閘門，適合在這些可信邊界加入知識檢索與晉升。越晚建立，歷史產物與術語漂移的整理成本越高。

### 預期成果

- `BG-001`：Agent 能在各 SDLC 階段快速找到與目前工作相關、可追溯且未過期的專案知識。
- `BG-002`：每個可信終態的需求、計畫、實作及 BUG 結果都會形成已核准的知識更新或明確的 no-change 證據。
- `BG-003`：知識保持可稽核、可重建、可由 Git 版本化，且不依賴外部服務、向量資料庫或中央知識平台。

## 2. 利害關係人與角色

| 角色 ID | 角色 | 需求／責任 | 決策或權限邊界 |
|---|---|---|---|
| `ACT-001` | Coding Agent | 在工作前檢索知識、形成 context pack、產生 knowledge diff 並執行 lint | 不得把未核准推論直接升格為 canonical knowledge |
| `ACT-002` | 專案擁有者／核准者 | 審查需求、計畫及 knowledge diff，裁決矛盾 | 唯一可核准 knowledge promotion 的角色 |
| `ACT-003` | SDLC Workflow | 提供 Ready／Complete 來源與階段狀態 | 既有來源產物仍是事實權威，Wiki 不取代來源 |

## 3. 範圍與優先順序

### 範圍內

- 單一 repository、local-first 的工程知識系統。
- 擴充目前 requirements、planning、implementation、BUG 與 delivery workflows。
- 三層結構：
  - repository 內正式產物及程式碼形成來源層；
  - 互相連結的工程 Wiki 形成綜整層；
  - schema、index、log 與 lint 形成治理層。
- 各 SDLC 階段開始前的自動檢索，以及明示的隨選查詢。
- Ready requirements、Ready plan、Complete implementation 與 BUG verification 的知識候選萃取。
- 人工核准後的知識晉升。
- stale、superseded、contradiction、孤兒頁、壞連結與 provenance 檢查。
- Windows、Linux。
- 繁體中文、英文與程式識別碼混合查詢。
- 將正式 SDLC 產物與知識頁納入 Git；可重建快取與暫存候選不納入。

### 範圍外

- 中央化或跨 repository 知識平台。
- 自動擷取聊天、Issue、PR、會議、郵件或外部 SaaS。
- 日常 ingestion 外部網址或檔案。
- macOS 平台的功能支援、效能量測與 release evidence。
- SQLite、向量資料庫、embedding、雲端搜尋或外部 API。
- 獨立 Web UI、Obsidian-first 體驗或常駐服務。
- 完整 Git 歷史重建。
- 自動 commit、push、merge、部署或清理 worktree。
- 未核准草稿、假設與一般查詢答案的自動晉升。

### 非目標

- Wiki 不取代 requirements、plan、implementation evidence、BUG assessment 或 verification。
- 不以「較新」自動判定來源較權威。
- 不承諾跨專案搜尋或多人權限模型。
- 不讓索引成為無法重建的唯一資料來源。

### 優先順序

可信度與追溯性優先於召回量及自動化速度；任何 stale、矛盾、來源失效或未核准內容都不得進入自動 context pack。

## 4. 使用者與業務旅程

### `J-001` — 建立初始知識基線

- 主要角色：`ACT-001`、`ACT-002`
- 觸發與前置條件：知識系統首次在現有 repository 啟用。
- 主要流程：
  1. 系統檢查目前專案的正式產物、治理文件與程式碼。
  2. 只有可證明為可信終態的來源可形成知識候選。
  3. 系統產生首批 Wiki、index、log 及完整 knowledge diff。
  4. 使用者核准後才寫入並形成基線。
- 替代、例外與復原：
  - Candidate、狀態矛盾或來源 hash 不一致的內容必須隔離並回報。
  - 不解析完整 Git 歷史。
- 完成結果：repository 具有可查詢、可追溯的初始知識基線。
- 相關需求：`FR-001`、`FR-006`、`TR-001` 至 `TR-003`
- 驗收情境：`AC-001`、`AC-009`

### `J-002` — 在 SDLC 階段檢索知識

- 主要角色：`ACT-001`
- 觸發與前置條件：開始 requirements、planning、implementation、BUG diagnosis，或使用者明示查詢。
- 主要流程：
  1. 系統讀取索引、詞彙與目前有效知識。
  2. 使用 Markdown 與 `rg` 搜尋 Wiki 及符合資格的 repository 來源。
  3. 系統產生最多五項主要結果的 context pack。
  4. Agent 依結果回讀底層正式來源並以來源作為後續文件 evidence。
- 替代、例外與復原：
  - stale、contested 或來源驗證失敗的 claim 被排除。
  - 找不到 Wiki 結果時可搜尋符合資格的 repository 原始來源。
- 完成結果：Agent 取得具來源位置、hash、locator、狀態與匹配理由的結果。
- 相關需求：`FR-002` 至 `FR-005`、`NFR-001` 至 `NFR-005`
- 驗收情境：`AC-002` 至 `AC-005`

### `J-003` — 核准需求或計畫並同步晉升知識

- 主要角色：`ACT-001`、`ACT-002`、`ACT-003`
- 觸發與前置條件：requirements 或 plan Candidate 已通過本身的品質門檻。
- 主要流程：
  1. Agent 從 Candidate bytes 產生 knowledge diff。
  2. 原始 Candidate 與 knowledge diff 使用同一道既有人工 gate 完整展示。
  3. 使用者一次核准兩者。
  4. 正式產物與知識更新以相同 approval evidence 寫入。
  5. lint 通過後才能進入下一個 SDLC 階段。
- 替代、例外與復原：
  - 使用者修改任一內容時，兩者重算並重新展示。
  - 寫入前來源或 Wiki preimage 改變時，整次 promotion 停止。
- 完成結果：正式產物與衍生知識保持一致且可追溯。
- 相關需求：`BR-001` 至 `BR-004`、`FR-006` 至 `FR-010`
- 驗收情境：`AC-006`、`AC-007`、`AC-013`

### `J-004` — 完成實作或 BUG 修復並萃取結果

- 主要角色：`ACT-001`、`ACT-002`、`ACT-003`
- 觸發與前置條件：implementation full verification 與 fresh review 已通過。
- 主要流程：
  1. 系統形成可持久保存的實作結果來源。
  2. Agent 產生反映實際行為、驗證結果、決策偏差及經驗的 knowledge diff。
  3. Delivery 進入 `knowledge-awaiting-user`。
  4. 使用者核准且 lint 通過後，delivery 才能 Complete。
- 替代、例外與復原：
  - BUG verification 為 `partial` 時，只能記錄未解事件、已知觀察、proxy evidence 與殘餘風險。
  - `partial` 不得產生「已修復」或同義 claim。
- 完成結果：產品結果與知識結果都完成驗證及核准。
- 相關需求：`FR-011` 至 `FR-014`
- 驗收情境：`AC-008`、`AC-010`、`AC-011`

### `J-005` — Lint、隔離與修復知識

- 主要角色：`ACT-001`、`ACT-002`
- 觸發與前置條件：明示執行 lint、promotion 後驗證，或查詢時發現來源漂移。
- 主要流程：
  1. 系統檢查來源 hash、claim provenance、連結、ID、索引與 log。
  2. 問題 claim 從自動 context pack 排除。
  3. 系統產生診斷與修復候選。
  4. 使用者核准後才更新 canonical knowledge。
- 替代、例外與復原：
  - 兩個有效來源矛盾時保留雙方，建立 contradiction，等待適當 SDLC gate 裁決。
- 完成結果：問題可見、未被誤用，且修復不繞過人工核准。
- 相關需求：`FR-015` 至 `FR-018`
- 驗收情境：`AC-012` 至 `AC-015`

## 5. 領域詞彙、實體與生命週期

- `TERM-001 — Raw Source`：repository 內的正式 SDLC 產物、治理文件或程式碼；其內容不由 Wiki 維護流程改寫。
- `TERM-002 — Canonical Knowledge`：已由人工核准、來源有效且 lint 通過的工程 Wiki claim。
- `TERM-003 — Context Pack`：一次查詢產生的唯讀結果集合，只作導航與上下文，不取代底層來源。
- `TERM-004 — Promotion Candidate`：尚未寫入、綁定來源與 Wiki preimage 的完整 knowledge diff。
- `TERM-005 — Stale`：claim 的 provenance 與目前來源 bytes 不一致。
- `TERM-006 — Contested`：兩個有效來源對同一語義提出不能同時成立的 claim。
- `TERM-007 — Partial Incident`：BUG 原始症狀尚未獲得 verified 結論，但已有核准 proxy evidence、風險與後續驗證要求的事件。

- `ENT-001 — Knowledge Claim`
  - 證據類別：required、planned、observed、verified、partial。
  - 生命週期：current、superseded、contested、stale。
  - 每個 claim 必須具有穩定 ID 與至少一個可驗證來源。
- `ENT-002 — Knowledge Promotion`
  - 狀態：Candidate、Approved、Applied 或 Failed。
  - 必須綁定來源 hashes、knowledge preimages、postimages、核准證據與結果。
- `ENT-003 — Knowledge Page`
  - 類型涵蓋詞彙／領域、決策、實作現況、工程實務及 incident。
  - 頁面可更新，但歷次 promotion 與 Git history 必須可稽核。

## 6. 需求

### 業務規則

- `BR-001`：只有 Ready requirements、Ready plan、Complete implementation 與合法 BUG verification 才能觸發 canonical knowledge promotion。
- `BR-002`：一般查詢答案、聊天推論、Draft、Candidate、失敗假設或未驗證實作不得直接成為 canonical knowledge。
- `BR-003`：每個 canonical claim 必須連到可重新取得並驗證 hash 的 repository 來源。
- `BR-004`：Wiki 只提供綜整與導航；後續正式產物必須引用底層來源，不得形成 Wiki 自我引用的證據循環。
- `BR-005`：來源變更後尚未重新核准的 claim 必須標為 stale，並從自動 context pack 排除。
- `BR-006`：矛盾來源必須同時保留，不得以時間或文件類型自動裁決。
- `BR-007`：`partial` BUG 只能形成 unresolved/partial incident，不得宣稱原始症狀已驗證修復。
- `BR-008`：沒有知識變更的可信終態仍必須產生可稽核的 no-change 結果，證明已執行萃取判定。

### 功能需求

- `FR-001`：系統必須能從目前可信快照建立初始 Wiki Candidate，並隔離不一致或非終態來源。
- `FR-002`：系統必須支援對 canonical Wiki 與符合資格 repository 來源的 Markdown／`rg` 查詢。
- `FR-003`：requirements、planning、implementation 與 BUG diagnosis 開始時必須自動建立相關 context pack。
- `FR-004`：系統必須提供明示的隨選查詢。
- `FR-005`：每個結果必須包含頁面或來源路徑、狀態、匹配原因、來源 hash 及可定位內容的 locator。
- `FR-006`：每個可信終態必須自動產生完整 knowledge diff 或 no-change Candidate。
- `FR-007`：使用者必須能在寫入前看到所有受影響路徑及其完整變更。
- `FR-008`：需求與計畫的 knowledge diff 必須沿用原本人工核准 gate 與 approval evidence。
- `FR-009`：未核准或核准對象已漂移時，系統不得寫入 knowledge promotion。
- `FR-010`：需求或計畫的 promotion 未成功時，workflow 不得進入下一階段。
- `FR-011`：Complete implementation 必須提供可持久引用的實作結果，包括實際變更、驗證結果、review 結論與已知偏差。
- `FR-012`：implementation fresh review 後必須進入 `knowledge-awaiting-user`，而非直接 Complete。
- `FR-013`：knowledge promotion 核准、寫入及 lint 全部成功後，delivery 才能 Complete。
- `FR-014`：BUG `verified` 與 `partial` 必須依各自語義產生不同 incident knowledge。
- `FR-015`：系統必須 lint 缺少 provenance、source hash drift、壞連結、孤兒頁、重複 ID、索引／log 不一致、非法狀態及未解矛盾。
- `FR-016`：lint 發現 stale 或 provenance 錯誤時，必須排除問題 claim 並產生修復候選。
- `FR-017`：lint 發現有效來源矛盾時，必須建立 contradiction 並要求後續人工決策。
- `FR-018`：index 必須能由 Wiki 頁面與 machine metadata 完整重建；index 遺失不得造成知識本體遺失。

### 品質需求

- `NFR-001`：所有日常查詢、lint 與 promotion 必須能完全離線執行，不依賴外部 API、embedding、向量資料庫、SQLite 或常駐服務。
- `NFR-002`：系統必須支援 Windows 與 Linux；macOS 不在本版支援與驗收範圍。
- `NFR-003`：系統必須正確處理 UTF-8 繁體中文、英文、路徑與程式識別碼。
- `NFR-004`：在最多 50,000 個 tracked files、5,000 個知識頁的驗收 fixture 中，常見查詢及結構化索引更新的目標時間必須在 2 秒內。
- `NFR-005`：至少 20 題 Golden Queries 中，正確來源進入 Top 5 的比例必須至少為 90%。
- `NFR-006`：所有自動 context pack 的來源引用有效率必須為 100%，stale 或 contested claim 的自動引用數必須為 0。
- `NFR-007`：唯讀查詢與 lint 不得修改 tracked repository bytes。
- `NFR-008`：寫入必須限制在已核准路徑；path traversal、symlink／reparse redirect、preimage drift、部分 promotion 或秘密內容必須 fail closed。
- `NFR-009`：正式產物與 canonical knowledge 必須可由 Git 版本化；工具不得自動 stage、commit、push、merge 或 cleanup。
- `NFR-010`：索引與 machine metadata 的結果必須具確定性，同一組來源 bytes 必須產生相同結構化結果。

### 移轉與過渡需求

- `TR-001`：啟用時必須將新的正式 SDLC 路徑及 knowledge 路徑納入 Git，並保持快取、host-temp Candidate 與執行 evidence 不被追蹤。
- `TR-002`：初始回填只處理目前可信快照，不解析完整 Git 歷史。
- `TR-003`：目前 legacy planning bundle 的 machine sidecar 與 Markdown 狀態不一致，因此不得自動晉升；bootstrap 必須回報並隔離。
- `TR-004`：既有 delivery records 與 Ready artifacts 不得因新契約無法讀取；新 knowledge gate 適用於新建或明確升級的 delivery run。

## 7. 驗收情境

### `AC-001` — 初始回填

- Given：repository 同時含可信終態、Candidate 與狀態矛盾的產物
- When：執行 bootstrap
- Then：只有可信終態形成 knowledge Candidate，其餘內容被隔離並附原因，且核准前 filesystem 不變
- 驗證需求：`FR-001`、`TR-002`、`TR-003`

### `AC-002` — 需求開始前檢索

- Given：Wiki 具有與新需求相關的詞彙、決策與 incident
- When：requirements discovery 開始
- Then：Agent 取得最多五項主要結果及其底層來源，並在提出第一個問題前讀取適用來源
- 驗證需求：`FR-002`、`FR-003`、`FR-005`

### `AC-003` — 各階段自動檢索

- Given：需求、計畫、實作或 BUG workflow 即將開始
- When：該階段執行 evidence preflight
- Then：系統建立該階段的唯讀 context pack，且不修改 repository
- 驗證需求：`FR-003`、`NFR-007`

### `AC-004` — 隨選查詢

- Given：使用者明示詢問專案詞彙、決策、行為或過往 BUG
- When：Agent 執行知識查詢
- Then：回傳符合狀態與 provenance 規則的結果，查詢答案不自動寫回
- 驗證需求：`BR-002`、`FR-004`

### `AC-005` — Golden Query 品質

- Given：至少 20 題涵蓋需求、決策、實作與 BUG 的固定題庫
- When：執行完整 retrieval evaluation
- Then：至少 90% 題目的正確來源位於 Top 5，且每個結果引用可驗證
- 驗證需求：`NFR-005`、`NFR-006`

### `AC-006` — 需求 promotion

- Given：requirements Candidate 與 knowledge diff 均已完整展示
- When：使用者核准
- Then：兩者以相同 approval evidence 寫入；promotion 與 lint 成功後才進 planning
- 驗證需求：`FR-006` 至 `FR-010`

### `AC-007` — 計畫 promotion

- Given：Ready-plan Candidate 與 planned knowledge diff 均已完整展示
- When：使用者核准
- Then：plan 與 knowledge 一致寫入；planned claim 不得被標示為 observed
- 驗證需求：`BR-003`、`FR-006` 至 `FR-010`

### `AC-008` — 實作完成前 knowledge gate

- Given：implementation full verification 與 fresh review 已通過
- When：delivery 嘗試 Complete
- Then：先進入 `knowledge-awaiting-user`；只有實作結果 knowledge 核准且 lint 通過後才 Complete
- 驗證需求：`FR-011` 至 `FR-013`

### `AC-009` — Bootstrap 狀態矛盾

- Given：同一 planning bundle 的 JSON 表示 Ready，但 Markdown 表示 Candidate
- When：bootstrap 評估該 bundle
- Then：不得產生 current/planned claim，並回報精確衝突來源
- 驗證需求：`BR-006`、`TR-003`

### `AC-010` — Verified BUG

- Given：BUG verification 結果為 `verified`
- When：形成 incident knowledge
- Then：頁面可記錄已驗證症狀、根因、修正、regression evidence 與預防知識
- 驗證需求：`FR-014`

### `AC-011` — Partial BUG

- Given：BUG verification 結果為 `partial`
- When：形成 incident knowledge
- Then：頁面標示 unresolved/partial，只保留已證實觀察、proxy evidence、殘餘風險與 follow-up，且不含已修復宣稱
- 驗證需求：`BR-007`、`FR-014`

### `AC-012` — Stale claim

- Given：knowledge provenance 中的來源 hash 已改變
- When：查詢或 lint 讀取該 claim
- Then：claim 被排除、標示 stale，並產生待核准修復候選
- 驗證需求：`BR-005`、`FR-015`、`FR-016`

### `AC-013` — Promotion preimage drift

- Given：使用者看到 Candidate 後，來源或 Wiki preimage 發生變化
- When：嘗試套用核准 promotion
- Then：整次寫入停止，不產生部分成功或完成聲明
- 驗證需求：`FR-009`、`NFR-008`

### `AC-014` — 有效來源矛盾

- Given：兩個通過 hash 驗證的來源包含不能同時成立的 current claim
- When：lint 或 promotion 發現矛盾
- Then：雙方證據保留、claim 標示 contested、排除自動引用，並要求適當 gate 裁決
- 驗證需求：`BR-006`、`FR-017`

### `AC-015` — 完整 lint

- Given：Wiki fixture 含孤兒頁、壞連結、重複 ID、缺 provenance、stale source、索引漂移及 contradiction
- When：執行 lint
- Then：每個問題都有穩定診斷；問題 claim 不進 context pack；唯讀 lint 不改 filesystem
- 驗證需求：`FR-015` 至 `FR-018`、`NFR-007`

### `AC-016` — 跨平台與效能

- Given：Windows、Linux 的一般單一 repo fixture
- When：執行查詢、索引更新與完整測試
- Then：功能結果一致，常見查詢與結構化索引更新符合 2 秒目標
- 驗證需求：`NFR-002` 至 `NFR-004`

### `AC-017` — Git 與安全邊界

- Given：fixture 含 ignored files、秘密樣式、symlink／reparse redirect、path traversal 與未核准路徑
- When：執行查詢、lint 或 promotion
- Then：只有符合資格來源可讀、只有核准路徑可寫；違規 fail closed，且不執行 Git terminal action
- 驗證需求：`NFR-008`、`NFR-009`

## 8. 成功指標

| 指標 ID | 對應成果 | 指標與計算方式 | 基準 | 目標 | 量測期間／資料來源 |
|---|---|---|---|---|---|
| `KPI-001` | `BG-001` | Golden Queries 中正確來源進入 Top 5 的題數 ÷ 總題數 | 系統建立前無統一檢索 | ≥ 90% | 每次完整 retrieval evaluation |
| `KPI-002` | `BG-001` | 有效引用數 ÷ context pack 引用總數 | 系統建立前無 context pack | 100% | 自動測試與 lint report |
| `KPI-003` | `BG-001` | stale／contested claim 自動引用數 | 系統建立前無防線 | 0 | 每次 query evaluation |
| `KPI-004` | `BG-002` | 具 Approved promotion 或 no-change 證據的可信終態數 ÷ 可信終態總數 | 0% | 100% | Delivery records |
| `KPI-005` | `BG-003` | 一般規模 fixture 的常見查詢與索引更新時間 | 實作後建立基準 | ≤ 2 秒 | Windows／Linux 測試報告 |
| `KPI-006` | `BG-003` | 未核准寫入、秘密洩漏、來源循環或 Git terminal action 數 | 0 | 0 | 安全測試與 fresh review |

## 9. 追溯矩陣

| 業務成果 | 旅程 | 需求 | 驗收情境 | 成功指標 |
|---|---|---|---|---|
| `BG-001` | `J-001`、`J-002` | `BR-003` 至 `BR-006`、`FR-001` 至 `FR-005`、`FR-015` 至 `FR-018`、`NFR-001` 至 `NFR-006` | `AC-001` 至 `AC-005`、`AC-009`、`AC-012`、`AC-014` 至 `AC-016` | `KPI-001` 至 `KPI-003`、`KPI-005` |
| `BG-002` | `J-003`、`J-004` | `BR-001`、`BR-002`、`BR-007`、`BR-008`、`FR-006` 至 `FR-014` | `AC-006` 至 `AC-008`、`AC-010`、`AC-011`、`AC-013` | `KPI-004` |
| `BG-003` | `J-001`、`J-005` | `FR-015` 至 `FR-018`、`NFR-007` 至 `NFR-010`、`TR-001` 至 `TR-004` | `AC-012` 至 `AC-017` | `KPI-005`、`KPI-006` |

## 10. 已確認決策、假設與依賴

### 已確認決策

- `D-001`：第一版以單一 repository、local-first 為邊界。
- `D-002`：主要使用者是 coding agent；人類直接閱讀 Markdown 並負責核准。
- `D-003`：日常 ingestion 只接受專案內來源。
- `D-004`：採用 LLM Wiki 的來源層、持久 Wiki 層與 schema／index／log 治理層。
- `D-005`：搜尋使用 Markdown 與 `rg`，不使用 SQLite、向量或雲端服務。
- `D-006`：各 SDLC 階段前自動檢索，並支援隨選查詢。
- `D-007`：知識更新自動形成 Candidate，但必須由人類核准。
- `D-008`：knowledge promotion 是正式完成條件；不得留下非阻擋待辦。
- `D-009`：stale 或 provenance 錯誤採 fail-closed，排除並產生修復候選。
- `D-010`：來源矛盾保留雙方並要求決策，不自動套用時間或文件優先序。
- `D-011`：臨時查詢只有進入正式核准／驗證產物後才能晉升。
- `D-012`：`partial` BUG 收錄為未解事件，不視為 verified fix。
- `D-013`：初始回填使用目前可信快照，不重建完整 Git 歷史。
- `D-014`：正式 SDLC 產物與 knowledge 進 Git；可重建資料維持不追蹤。
- `D-015`：目標為 Windows、Linux 的一般單一 repo；依 2026-09-01 使用者範圍決策，macOS 明確排除於本版支援與 release 驗收。
- `D-016`：搜尋品質使用 Golden Queries 與客觀門檻驗收。
- `D-017`：能力直接擴充目前 SDLC Skills，不另建獨立服務或產品。

### 已確認假設

- `A-001`：repository 存取權即為第一版的知識存取權，不新增獨立角色權限。
- `A-002`：外部參考專案只影響本功能設計，不成為日常 runtime ingestion 來源。

### 依賴與外部限制

- `DEP-001`：執行環境必須可使用 Git 與 `rg`。
- `DEP-002`：知識可信度依賴既有 requirements、planning、implementation、BUG 與 delivery gate 的狀態及 hash 正確性。
- `DEP-003`：目前 `.gitignore` 忽略整個 `docs/`，導入時必須調整正式產物與 knowledge 的追蹤邊界。
- `DEP-004`：目前 legacy plan bundle 存在 Markdown／machine sidecar 狀態不一致，不能作為無條件 bootstrap 來源。
- `DEP-005`：本功能參考：
  - https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f
  - https://github.com/mattpocock/skills
  - https://github.com/obra/superpowers
  - https://github.com/Fission-AI/openspec
  - https://github.com/github/spec-kit

### 延後至技術規劃的決策

- `TP-001`：Knowledge Skill 的模組、CLI、schema 與 progressive-disclosure 結構。
- `TP-002`：Knowledge Page、claim、promotion、context pack 與 implementation outcome 的 machine contract。
- `TP-003`：Markdown／`rg` 搜尋、排序、繁中 alias 與 fallback 規則。
- `TP-004`：promotion 的 preimage binding、交易寫入與 crash recovery。
- `TP-005`：implementation snapshot 與 post-review knowledge update 的隔離及驗證方式。
- `TP-006`：新 delivery run 與 legacy run 的 schema 相容策略。
- `TP-007`：Golden Query fixture、跨平台測試與效能量測方式。

## 11. 完整性與開放事項

- 阻塞性開放事項：無。
- 品質門檻：單一需求、驗收情境、品質屬性、移轉需求及雙向追溯均已通過；本成果不涉及需額外法規審查的高風險資料處理。
