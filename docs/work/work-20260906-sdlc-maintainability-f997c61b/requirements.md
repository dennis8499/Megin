# 需求分析：SDLC 專案可維護性、診斷與量測改善

- 文件狀態：Ready
- 日期：2026-09-06
- 文件範圍：改善本 repository 的導覽、CI 覆蓋、Delivery 狀態轉換可維護性、Schema 驗證、唯讀診斷及量測能力
- 需求來源：使用者 2026-09-06 明示要求實作六個工作包；現行 Delivery、Requirements、Planning、Implementation 與 Project Knowledge 契約；base `1532391a4ea056828e30893e749fe307118a1e24` 的未修改全量測試
- 確認者：user；approval evidence `conversation:requirements-work-20260906-sdlc-maintainability-f997c61b-candidate-1`

## 1. 執行摘要

### 問題或機會

本專案已有嚴格的工作區、階段授權、人工核准、知識 promotion 與回歸保護，但新維護者缺少單一導覽入口；重要狀態轉換集中於大型函式；CI 未由全部治理文件變更觸發；受限 Schema 驗證器未明示未知關鍵字政策；registry 或證據異常時也缺少整合的唯讀診斷。長時間全量 runner 只在結束時輸出結果，難以辨認耗時來源。

### 為何現在做

本次未修改基準完整通過：Knowledge BDD 24/24、Delivery 整合測試 65/65、Requirements／Planning／Implementation／BUG／Delivery owner contracts 全部通過，並成功檢查 37 個 Python 檔案與 5 份 JSON Schema。這提供可比較的安全基準，可在保留既有行為下改善維護與操作體驗。

### 預期成果

- BG-001：Maintainer 能從單一入口理解、驗證、診斷及安全續接 governed SDLC 工作，並以機器可讀證據判斷相容性、效能與搜尋品質。

本成果必須在不弱化既有人工 Gate、階段授權、雜湊綁定與原子寫入保證下，改善專案導覽、CI 覆蓋、核心可維護性、Schema 驗證、唯讀診斷及量測能力。

## 2. 利害關係人與角色

| 角色 ID | 角色 | 需求／責任 | 決策或權限邊界 |
|---|---|---|---|
| ACT-001 | Repository maintainer | 理解架構、執行驗證、診斷 run 並維護核心邏輯 | 只有既有 Gate 與 phase authorization 可授權正式寫入或轉換 |
| ACT-002 | Contributor／AI agent | 依公開入口開始、續跑與交付工作 | 不得由診斷結果推定寫入權或沿用失效核准 |
| ACT-003 | CI reviewer | 取得快速與跨平台驗證證據 | 不得把缺少、未執行或 timeout 的結果視為成功 |

## 3. 範圍與優先順序

### 範圍內

- 根目錄專案導覽、操作手冊與最小 governed delivery 範例。
- CI 路徑覆蓋、快速驗證工作及既有 Windows／Linux完整矩陣。
- Delivery 轉換職責拆分及跨 Skill validator 載入介面收斂。
- 受限 JSON Schema 子集合的明確支援與未知關鍵字拒絕。
- 新增唯讀 `doctor` 診斷介面與安全重建指引。
- 全量 runner 的獨立耗時報告、搜尋品質基準與可取得的流程指標。

### 範圍外

- 自動備份／還原、跨機遷移、registry 搬移與舊核准還原。
- 人工 Gate 次數、風險分級、發布流程或搜尋引擎的重新設計。
- 歷史 Ready、Outcome、receipt、canonical Wiki 原文或舊 record 的批次遷移。

### 非目標

- 不以減少檢查或放寬 timeout／效能門檻換取較短執行時間。
- 不新增 production 第三方依賴，也不建立第二套治理真相來源。

### 優先順序

所有安全、相容與來源完整性要求均為 Must；導覽、診斷及量測成果亦為本次 Must。工作順序必須先建立基準與 CI 保護，再改動核心轉換與驗證介面。

## 4. 使用者與業務旅程

### J-001 — 新維護者理解並驗證專案

- 主要角色：ACT-001
- 觸發與前置條件：維護者首次進入乾淨 repository，具備 Python、Git 與 ripgrep
- 主要流程：由根目錄導覽了解架構與治理邊界，選擇唯讀命令或測試入口，執行快速檢查，再依需要執行完整跨平台驗證
- 替代、例外與復原：依操作手冊辨認環境不足、Gate 等待、Blocked 或 Complete 狀態；缺少證據時保持失敗
- 完成結果：維護者能找到權威契約、操作入口及驗證結果
- 相關需求：FR-001、FR-002、NFR-003
- 驗收情境：AC-001、AC-002、AC-011

### J-002 — 安全修改 Delivery 與 Schema 契約

- 主要角色：ACT-001、ACT-002
- 觸發與前置條件：已建立相同 base 的 green 測試基準
- 主要流程：修改者沿明確的階段處理與 validator adapter 介面變更行為，執行 focused 及完整回歸
- 替代、例外與復原：未知 Schema 關鍵字或相容性漂移直接失敗並回報位置，不進入後續交付
- 完成結果：核心邏輯較易審閱，既有合法與非法轉換結果不變
- 相關需求：FR-003、FR-004、NFR-001、TR-001
- 驗收情境：AC-003、AC-004、AC-005、AC-006

### J-003 — 診斷無法續接的 run 並觀察品質

- 主要角色：ACT-001、ACT-003
- 觸發與前置條件：使用者指定 repository，可選擇提供 Work ID
- 主要流程：執行唯讀 doctor，取得穩定問題代碼及下一步；執行全量與搜尋基準取得獨立 metrics
- 替代、例外與復原：多筆 active run 只列候選；紀錄、來源或核准遺失時不猜測 continuity；交易復原仍由既有 recovery owner 處理
- 完成結果：維護者知道安全的續跑、復原或另開工作路徑，CI reviewer 能辨認耗時與搜尋品質
- 相關需求：FR-005、FR-006、NFR-002、NFR-004
- 驗收情境：AC-007、AC-008、AC-009、AC-010、AC-012

## 5. 需求

### FR-001 — CI 覆蓋完整治理變更

- 需求：CI 必須在 Skills、`docs/**`、`.gitattributes`、根目錄導覽與操作文件變更時執行快速契約／來源檢查，通過後保留既有 Windows／Linux 完整矩陣與報告。
- 理由與來源：`.github/workflows/knowledge-portability.yml:4-17` 現行 path filter 未涵蓋全部上述來源；BG-001、J-001。
- 優先順序：Must。
- 驗收：AC-001、AC-002。

### FR-002 — 單一專案導覽與操作入口

- 需求：Repository 必須從根目錄提供專案定位、環境需求、流程、唯讀命令、測試入口、治理邊界、常見狀態與安全復原指引，並連到現行 owner contracts 而不複製其權威規則。
- 理由與來源：根目錄目前沒有 README 或操作手冊；BG-001、J-001。
- 優先順序：Must。
- 驗收：AC-002、AC-011。

### FR-003 — 可維護的 Delivery 轉換邊界

- 需求：Maintainer 必須能依 phase 辨認狀態轉換的驗證與處理責任；公開 CLI 與既有持久化行為必須維持相容。
- 理由與來源：`.agents/skills/delivery-orchestrator/scripts/_delivery_record.py:2881-3837` 的主要轉換集中於單一大型函式；J-002。
- 優先順序：Must。
- 驗收：AC-003、AC-004、AC-005。

### FR-004 — 明確的 Schema 子集合

- 需求：契約驗證必須明列支援的 JSON Schema 驗證關鍵字及可忽略註解，並對 Schema 位置中的未知驗證關鍵字回報明確錯誤，且不得把 `properties` 下的業務欄位名稱誤判為關鍵字。
- 理由與來源：`.agents/skills/technical-planning/scripts/validate_contracts.py:178-271` 實作受限子集合但沒有未知關鍵字拒絕契約；J-002。
- 優先順序：Must。
- 驗收：AC-006。

### FR-005 — 唯讀 Delivery doctor

- 需求：Delivery CLI 必須提供 `doctor --repo <path> [--work-id <id>]`，檢查 repository／worktree identity、registry、record、generation、正式 artifact hashes 及已綁定證據，輸出版本化 checks、diagnostics 與 next actions，且不得建立、修改、復原或授權任何狀態。
- 理由與來源：`.agents/skills/delivery-orchestrator/references/workspace-and-run.md:60-90` 定義嚴格 continuity 與 fail-closed resume，但現行公開 CLI 沒有整合診斷介面；J-003。
- 優先順序：Must。
- 驗收：AC-007、AC-008、AC-009。

### FR-006 — 可觀察的測試與搜尋品質

- 需求：全量 runner 必須可選擇輸出不改變既有 stdout contract 的獨立 metrics，記錄每項命令的狀態、耗時、timeout 與未執行項目；專案另須以至少 20 個固定案例量測 Top-5 搜尋命中及失效來源排除，並由現有 event 資料計算可取得的階段時間與回流次數。
- 理由與來源：`.agents/skills/project-knowledge/scripts/run_full_suite.py:104-161` 現行只在逐項完成後累積結果並於最後輸出；`knowledge_query.py:1639-1705` 固定最多五項結果；J-003。
- 優先順序：Must。
- 驗收：AC-010、AC-012。

### NFR-001 — 行為及資料相容性

- 需求：變更後既有 CLI 參數、成功輸出、錯誤碼、合法／非法 phase transition、事件順序、歷史 Ready 信任根、legacy record 與 required knowledge overlay 必須通過現有回歸；不得新增既有 record 必填欄位。
- 理由與來源：使用者明示相容性原則；`.agents/skills/delivery-orchestrator/references/workspace-and-run.md:51-85`。
- 優先順序：Must。
- 驗收：AC-003、AC-004、AC-005。

### NFR-002 — 診斷零寫入與失敗封閉

- 需求：Doctor 的成功、輸入錯誤、狀態阻擋及環境不足結果都必須保持 repository、registry 與外部 sentinel 位元組不變；缺失或損壞資料不得被推定為有效，也不得重用舊核准。
- 理由與來源：現行 authorize／locate 的 read-only boundary 與 resume fail-closed 契約；J-003。
- 優先順序：Must。
- 驗收：AC-007、AC-008、AC-009。

### NFR-003 — 跨平台與效能門檻

- 需求：Windows 與 Linux 的功能結果必須等價；現行 50k repository probe／transition 與 Knowledge cold／warm 查詢門檻不得放寬。
- 理由與來源：`.github/workflows/knowledge-portability.yml:19-65`、現行基準測試；J-001、J-002。
- 優先順序：Must。
- 驗收：AC-001、AC-005、AC-010。

### NFR-004 — 秘密與證據最小化

- 需求：Doctor、metrics、搜尋基準與錯誤訊息不得保存原始秘密、原始 Git 輸出或任意 artifact 內容；只輸出 allowlisted identity、代碼、狀態、digest、byte count 與安全 next action。
- 理由與來源：`.agents/skills/delivery-orchestrator/references/workspace-and-run.md` 的 evidence 與秘密處理契約；J-003。
- 優先順序：Must。
- 驗收：AC-008、AC-010、AC-012。

### TR-001 — 非破壞性過渡

- 需求：升級必須保留歷史 Ready、Outcome、receipt、canonical Wiki 與舊 record bytes；不執行批次遷移，新增介面採 additive versioned contract。
- 理由與來源：使用者明示範圍；現有 append-only 與 historical trust-root 契約。
- 優先順序：Must。
- 驗收：AC-004、AC-005。

## 6. 驗收情境

### AC-001 — 文件變更觸發完整 CI
- Given：PR 只修改 `docs/**`、`.gitattributes`、README 或 OPERATIONS
- When：CI 判斷 workflow paths
- Then：快速檢查被觸發，通過後 Windows／Linux 完整矩陣產生可下載報告
- 驗證需求：FR-001、NFR-003

### AC-002 — 新維護者可由根目錄完成導覽
- Given：維護者只從 repository 根目錄開始
- When：依文件尋找架構、唯讀命令、測試與治理規則
- Then：所有連結有效，唯讀範例可執行，有副作用範例明示隔離與人工 Gate
- 驗證需求：FR-001、FR-002

### AC-003 — 各 phase 合法轉換保持相同
- Given：現行 standard／BUG、legacy／required overlay 合法 fixtures
- When：由重構後的公開 CLI 執行轉換
- Then：輸出、event order、核准與 current refs 與基準相同
- 驗證需求：FR-003、NFR-001

### AC-004 — 非法轉換持續 fail closed
- Given：錯 phase、錯 worktree、過期核准、hash drift、missing evidence 或 Complete record
- When：嘗試 authorize、resume 或 transition
- Then：回傳既有錯誤分類，repository 與 record 沒有非預期寫入
- 驗證需求：FR-003、NFR-001、TR-001

### AC-005 — 鎖定、原子性與效能不退化
- Given：並行寫入、路徑碰撞與 50k repository fixtures
- When：執行 transition 與完整回歸
- Then：只有一個合法 writer、無部分寫入，既有效能門檻保持通過
- 驗證需求：FR-003、NFR-001、NFR-003、TR-001

### AC-006 — 未知 Schema 規則被安全拒絕
- Given：現有合法 fixtures、支援規則的正負案例、未知驗證關鍵字及名為相同字串的業務 property
- When：執行契約驗證
- Then：合法案例通過、無效案例在精確 schema location 失敗、業務 property 不被誤判，訊息不反射資料值
- 驗證需求：FR-004

### AC-007 — Doctor 正常診斷保持零寫入
- Given：唯一 active 且完整的 run
- When：執行 `doctor`，可選擇提供正確 Work ID
- Then：輸出 `delivery-doctor/v1`、完整 checks 與安全 resume action，所有受觀察位置前後 bytes 相同
- 驗證需求：FR-005、NFR-002

### AC-008 — Doctor 區分阻擋原因
- Given：多筆 active、無 run、record 遺失／損壞、identity mismatch、artifact drift、evidence missing 或 recovery required fixtures
- When：執行 doctor
- Then：回傳穩定診斷代碼、適當退出碼及具體 next action，不選錯 run、不回復或沿用核准、不輸出敏感值
- 驗證需求：FR-005、NFR-002、NFR-004

### AC-009 — 安全重建保留現場
- Given：continuity 已無法證明但 worktree 含既有進度
- When：維護者依操作手冊處理
- Then：舊工作區與未提交修改被保留；新工作重新驗證來源且不自動複製差異或繼承舊核准
- 驗證需求：FR-005、NFR-002

### AC-010 — 獨立 metrics 不改功能契約
- Given：全量 runner 成功、子命令失敗及 timeout fixtures
- When：指定 `--metrics-output`
- Then：既有 stdout report 保持相容；獨立 `knowledge-suite-metrics/v1` 完整列出成功、失敗、timeout 與未執行項目，且不含原始秘密輸出
- 驗證需求：FR-006、NFR-003、NFR-004

### AC-011 — 操作文件與權威契約一致
- Given：README、OPERATIONS 與 owner contracts
- When：執行文件 link／command contract 檢查
- Then：入口文件只導向權威規則，命令與實際 parser 一致，沒有第二套核准或復原語意
- 驗證需求：FR-002

### AC-012 — 搜尋與流程品質可量測
- Given：至少 20 個中、英、中英混用、exact ID 與 no-valid-source 固定案例，以及可用與不完整 event history
- When：執行品質基準
- Then：報告 Top-5 命中與失效來源排除結果；可取得的階段時間／回流次數有值，缺少資料明示不可計算
- 驗證需求：FR-006、NFR-004

## 7. 成功指標

| 指標 ID | 對應成果 | 指標與計算方式 | 基準 | 目標 | 量測期間／資料來源 |
|---|---|---|---|---|---|
| KPI-001 | BG-001 | 根目錄可到達的主要操作與測試入口比例 | 無根目錄導覽 | 本次定義的入口 100% 可由 README 到達且連結有效 | 每次 CI 文件檢查 |
| KPI-002 | BG-001 | 既有全量回歸通過率 | base 上本次 full suite 全部通過 | 最終 full suite 與 Windows／Linux parity 100% 通過 | 本次交付及後續 PR CI |
| KPI-003 | BG-001 | Doctor 零寫入情境通過率 | 無 doctor | 正常與全部計畫失敗類別 100% 前後 bytes 相同 | focused tests 與 final suite |
| KPI-004 | BG-001 | 固定搜尋案例 Top-5 命中率與無效來源排除 | 實作時由固定 corpus 首次建立 | 命中率至少維持既有 retrieval 基準，無效來源排除 100% | 每次 Knowledge full suite |
| KPI-005 | BG-001 | 測試命令耗時可觀測率 | runner 沒有獨立逐命令 metrics | 已排程與未執行命令 100% 有狀態，已執行命令 100% 有 duration | 每次指定 metrics 的 full suite |

## 8. 追溯矩陣

| 業務成果 | 旅程 | 需求 | 驗收情境 | 成功指標 |
|---|---|---|---|---|
| BG-001 | J-001 | FR-001、FR-002、NFR-003 | AC-001、AC-002、AC-011 | KPI-001、KPI-002 |
| BG-001 | J-002 | FR-003、FR-004、NFR-001、TR-001 | AC-003..AC-006 | KPI-002 |
| BG-001 | J-003 | FR-005、FR-006、NFR-002、NFR-004 | AC-007..AC-010、AC-012 | KPI-003..KPI-005 |

## 9. 已確認決策、假設與依賴

### 已確認決策

- D-001：採六個工作包的分階段完整改善，保留既有人工 Gate 與階段授權；決策者為使用者。
- D-002：復原限於唯讀診斷與安全重建指引，不包含備份還原或跨機遷移；決策者為使用者。
- D-003：沿用 Python standard library 與現有測試架構；不新增 production 第三方依賴。
- D-004：完整性與相容性優先於縮短檢查時間；既有門檻不得放寬。

### 已確認假設

- A-001：本次主要讀者為 repository maintainer、contributor／AI agent 與 CI reviewer；依使用者要求及現行 Skills 的 owner 分工確認。
- A-002：GitHub Actions 是跨平台 release evidence 的現行執行環境；由 `.github/workflows/knowledge-portability.yml` 確認。

### 依賴與外部限制

- DEP-001：執行需要 Python 3.13、Git、ripgrep 及 Windows／Linux GitHub-hosted runner；CI owner 負責可用性。
- DEP-002：現行 owner validators、`delivery-run/v1`、Knowledge contracts 與 Human Gate contract 為相容性真相來源。

### 延後至技術規劃的決策

- TP-001：狀態處理器與具名內部資料型別的精確模組切分。
- TP-002：共享 validator adapter 的載入與快取邊界。
- TP-003：`delivery-doctor/v1` 的 closed JSON 欄位與穩定診斷代碼集合。
- TP-004：metrics 檔案的原子寫入策略及搜尋 corpus 的存放格式。

## 10. 完整性與開放事項

- 阻塞性開放事項：無。
- 品質門檻：每項需求具單一義務、來源、驗收與追溯；安全、相容、復原、效能、跨平台及秘密處理均有可觀察 pass/fail。範圍外與 HOW 決策已明確交由技術規劃。
