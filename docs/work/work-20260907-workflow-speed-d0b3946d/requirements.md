# 需求分析：本地 AI SDLC 端到端速度改善

- 文件狀態：Ready
- 日期：2026-09-07
- 文件範圍：降低本地 AI Driven SDLC 的驗證、審查、文件整理、知識檢索、Git fixture 與中斷續跑成本
- 需求來源：使用者提供並要求實作的流程優化計畫；現行 Delivery、Requirements、Planning、Implementation 與 Project Knowledge 契約；Windows 實測與歷史 run evidence
- 確認者：user；approval evidence {APPROVAL_EVIDENCE}

## 1. 執行摘要

### 問題或機會

快速檢查約 2.6 秒，但完整 suite 約 14.1 分鐘，其中 Delivery workspace integration 與 BDD 約占 79%。Ready plan、主代理、preliminary reviewer 與 final reviewer 可能重複執行相同完整命令；昂貴驗證也可能在靜態檢查可提早發現阻擋缺陷之前執行。手動整理 command output、Outcome 與 review evidence 進一步增加 AI 工作時間。

### 為何現在做

系統已有 Work ID、隔離 worktree、階段授權、不可變 Gate bundle、雜湊綁定與完整回歸，可在不降低品質門檻的條件下建立可驗證的命令覆蓋、結果重用與分工明確的審查流程。

### 預期成果

- BG-001：無退件的本機日常交付，在相同機器與環境下三次量測的驗證時間中位數至少降低 30%，且驗證義務、失敗封閉與審查獨立性保持等價。
- BG-002：Agent 能由版本化 evidence bundle 自動建立 Outcome／review 所需輸入，減少人工複製、漏失及重新執行。
- BG-003：維護者能以中文自然問題取得相關原始契約，並能量測 Git fixture 與端到端階段時間。

本成果必須在保留現有人工核准、獨立審查、階段授權與證據完整性的前提下，縮短本地 AI SDLC 從需求到完成的總時間，並使每一項驗證義務只在輸入未漂移且證據可驗證時重用。

## 2. 利害關係人與角色

| 角色 ID | 角色 | 需求／責任 | 決策或權限邊界 |
|---|---|---|---|
| ACT-001 | Repository maintainer／使用者 | 取得較快的本地端到端交付與清楚的效能歸因 | 保留 Requirements、Plan、Knowledge 三道人工作業核准 |
| ACT-002 | 主實作 Agent | 執行 BDD／TDD、完整本機驗證並保存可信證據 | 不得把 stale、失敗、缺失或輸入不符的結果當作通過 |
| ACT-003 | Preliminary reviewer | 先做低成本完整性檢查，再對可能通過的 snapshot 執行獨立完整驗證 | 必須使用 fresh、唯讀 session |
| ACT-004 | Final reviewer | 核對 Outcome、Candidate、證據綁定與新增內容 | 只有重用契約成立時可引用 preliminary execution；否則重跑 |
| ACT-005 | Release operator | 在需求要求或發布前取得跨平台／GitHub evidence | 日常本機完成不等待發布級 evidence |

## 3. 範圍與優先順序

### 範圍內

- 本機日常完成與發布驗證兩種 validation profile。
- 命令覆蓋關係、executed／referenced provenance、輸入 identity 與 drift 判定。
- Preliminary review 的低成本前置檢查及 Final review 的差異化責任。
- Runner 自動保存完整 stdout／stderr、exit code、耗時、輸入 identity、digest 與測試 inventory。
- 由結構化 handoff／evidence 產生人類可讀追溯與命令摘要。
- 中文知識查詢、真實問題 corpus 與 answer-source 命中。
- Git test fixture 分段量測及可安全隔離的測試平行化。
- Host-temp run／Ledger／review evidence 的保存、匯出、驗證與復原指引。
- Active work、commands、review、human wait 與 interruption 可觀測性。

### 範圍外

- 減少三道人工作業核准、移除兩位獨立 Reviewer 或降低必要驗證義務。
- 自動部署、merge、push、通知或跨機遠端同步。
- 批次改寫舊 Ready plan、Outcome、delivery record 或 canonical knowledge。
- Production 第三方 dependency、daemon 或不受 snapshot 約束的跨工作快取。

### 非目標

- 不放寬 assertion、timeout、安全檢查或 source／preimage 驗證。
- 不把 Markdown 一律視為非執行輸入；Skill、契約、Schema、測試與 Agent 可讀治理內容都可能使 evidence 失效。

### 優先順序

P1 依序為驗證去重、審查前置檢查、Reviewer 分工、證據自動化、validation profile、結構化文件與中文檢索；P2 為 fixture 平行化與長期續跑。正確性、安全及相容性優先於效能目標。

## 4. 使用者與業務旅程

### J-001 — 完成本機日常交付

- 主要角色：ACT-001..004
- 觸發與前置條件：新工作有 Ready plan，目標本機環境可用
- 主要流程：主代理執行 focused red／green 與具命令覆蓋的完整驗證；preliminary reviewer 先做靜態前置檢查，再獨立完整驗證；final reviewer 驗證新增 Outcome／Candidate 與 reuse binding
- 替代、例外與復原：blocker 一次彙整退件；輸入或環境漂移使引用失效並要求 fresh execution
- 完成結果：本機 evidence、兩份獨立 review 與三道人工作業核准完整，跨平台發布證據不阻擋日常完成
- 相關需求：FR-001..006、NFR-001..004
- 驗收情境：AC-001..009

### J-002 — 取得發布證據

- 主要角色：ACT-005
- 觸發與前置條件：需求明示跨平台行為，或工作進入發布驗證
- 主要流程：執行 Windows／Linux 與 GitHub release profile
- 替代、例外與復原：缺平台或 hosted evidence 時保持 release validation 未完成，但不改寫先前本機完成事實
- 完成結果：release evidence 與本機 evidence 分開標示且可追溯
- 相關需求：FR-005、TR-001
- 驗收情境：AC-009

### J-003 — 診斷流程耗時與安全續跑

- 主要角色：ACT-001、ACT-002
- 觸發與前置條件：工作、測試或審查中斷，或維護者詢問流程速度
- 主要流程：查看版本化時間事件、command metrics 與 evidence archive；以中文問題查到相關契約；驗證 archive 後續跑
- 替代、例外與復原：archive 缺檔、hash drift、redirect 或版本不相容時 fail closed並保留現場
- 完成結果：耗時可歸因，中斷不必無條件重做仍可信的工作
- 相關需求：FR-007..010、NFR-002..005
- 驗收情境：AC-010..017

## 5. 需求

### FR-001 — 命令覆蓋與去重

- 需求：Ready plan 必須能宣告一個命令的成功結果覆蓋哪些 validation obligation 或子命令；runner 與 reviewer 必須以實際執行的子命令結果及測試 inventory 驗證覆蓋，避免再次執行已被完整包含的 BDD、build 或 governance command。
- 理由與來源：完整 suite 已包含 BDD-FULL、BUILD-FULL 與 GOVERNANCE，但近期 Ready plan 另列相同完整命令。
- 優先順序：Must。
- 驗收：AC-001、AC-002。

### FR-002 — 執行與引用 provenance

- 需求：每項 command outcome 必須標示 executed 或 referenced；引用必須綁定 producer outcome、raw output、command contract、input snapshot、environment identity、test inventory 與 digest，且不得呈現為本次重新執行。
- 理由與來源：BG-001、BG-002。
- 優先順序：Must。
- 驗收：AC-002..004。

### FR-003 — 低成本審查前置檢查

- 需求：Reviewer 必須在昂貴命令前檢查來源／需求覆蓋、完整 diff、test oracle、Ready command/evidence 完整性與環境；若存在 blocking finding，必須彙整可判定的 blockers、將未執行命令標示原因並退件。
- 理由與來源：近期 preliminary review 在完整命令通過後仍發現六項 blocking 缺陷。
- 優先順序：Must。
- 驗收：AC-005、AC-006。

### FR-004 — Preliminary 與 Final review 分工

- 需求：主代理與 fresh preliminary reviewer 各保留一次完整本機驗證；fresh final reviewer聚焦 Outcome、Candidate、dual snapshot、evidence binding 與 preliminary 後新增內容，只有 reuse contract 成立時引用 preliminary execution。
- 理由與來源：現行三方重跑放大完整 suite 成本。
- 優先順序：Must。
- 驗收：AC-003、AC-007、AC-008。

### FR-005 — 本機與發布 validation profile

- 需求：新 Ready plan 必須明列 validation profile 與 target environment；預設 local profile 以該本機環境完成日常交付，release profile 才要求跨平台／GitHub evidence；來源需求明示跨平台行為時必須納入指定平台。
- 理由與來源：使用者選定本機驗證作為日常完成標準。
- 優先順序：Must。
- 驗收：AC-009。

### FR-006 — 自動保存驗證證據

- 需求：Full runner 必須可選擇建立版本化 evidence bundle，自動保存完整 stdout／stderr、exit code、failure／skip、耗時、command／environment／input identity、raw output digest、test inventory 與 Outcome／review 可消費的 index。
- 理由與來源：BG-002。
- 優先順序：Must。
- 驗收：AC-010、AC-011。

### FR-007 — 結構化資料產生人類檢視內容

- 需求：工具必須能由 ready-plan handoff 與 verification index 產生 deterministic、唯讀的人類可讀命令摘要、追溯表及 evidence overview；決策理由仍由作者撰寫。
- 優先順序：Should。
- 驗收：AC-012。

### FR-008 — 中文知識檢索

- 需求：Project Knowledge query 必須對中文自然問題產生可用 terms，並以真實中文問題 corpus 驗證 Top-5 結果包含能回答問題的原始契約來源。
- 理由與來源：指定的兩個中文問題曾回傳零結果。
- 優先順序：Must。
- 驗收：AC-013。

### FR-009 — Git fixture 成本與安全平行化

- 需求：Delivery tests 必須分別量測 repository setup、test body 與 cleanup；只有 fixture root、registry、worktree、environment 及 performance resources 完全隔離的非效能測試可平行執行，效能基準保持單獨執行。
- 優先順序：Should。
- 驗收：AC-014。

### FR-010 — Evidence 保存與續跑

- 需求：系統必須提供 host-temp implementation run 的版本化 manifest、唯讀 verify、明示 export/import 與 retention policy；復原只接受 identity 與全部 hash 相符的 archive，不自動繼承核准或修改產品。
- 優先順序：Should。
- 驗收：AC-015。

### NFR-001 — 義務與品質等價

- 需求：去重前後 required validation obligations、test inventory、failure／skip 判定及兩位 Reviewer 的獨立判定必須等價。
- 優先順序：Must。
- 驗收：AC-001..008。

### NFR-002 — 漂移失敗封閉

- 需求：產品、測試、Skill、契約、Schema、環境、command 或未分類輸入任一漂移，均使相關引用失效；缺失、失敗、timeout、not-run 或 digest 不符不能支持 APPROVED。
- 優先順序：Must。
- 驗收：AC-003、AC-004、AC-008、AC-011、AC-015。

### NFR-003 — 效能目標

- 需求：在同機同環境、三次無退件 local profile 中，驗證時間中位數相較基準至少降低 30%；效能報告分開列出 active work、commands、review、human wait 與 interruption。
- 優先順序：Must。
- 驗收：AC-016。

### NFR-004 — 相容與移轉

- 需求：舊 Ready plan、command outcome、已核准 artifact 與既有 run 保持有效且不批次改寫；新欄位採 additive/versioned 契約，新 workflow 僅套用到新工作。
- 優先順序：Must。
- 驗收：AC-017。

### NFR-005 — 安全與最小狀態

- 需求：不得保存秘密值或未遮蔽外部輸出；archive／evidence path 必須防 redirect、escape、collision、partial write 與來源漂移，且沒有 daemon、network 或不受控 persistent cache。
- 優先順序：Must。
- 驗收：AC-010、AC-011、AC-015。

### TR-001 — 發布驗證分離

- 需求：CI 保留跨平台 release gate；local completion 與 release readiness 使用不同狀態／evidence，不把 local 通過宣稱為跨平台通過。
- 優先順序：Must。
- 驗收：AC-009、AC-017。

## 6. 驗收情境

### AC-001 — 包含關係避免重跑
- Given：full suite 明列並成功執行 BDD、build 與 governance 子命令及完整 inventory
- When：驗證相同 snapshot 的 covered obligations
- Then：各義務通過且底層命令只執行一次
- 驗證需求：FR-001、NFR-001

### AC-002 — 部分覆蓋仍執行缺項
- Given：suite 只覆蓋部分 required obligations
- When：runner 建立 execution plan
- Then：只去除已證明涵蓋的命令，其餘仍執行
- 驗證需求：FR-001、FR-002

### AC-003 — 引用可驗證
- Given：preliminary outcome 的 snapshot、environment、command contract、inventory 與 raw outputs 完整
- When：final reviewer 引用該結果
- Then：outcome 標示 referenced、鏈結 producer evidence，且不重新執行相同昂貴命令
- 驗證需求：FR-002、FR-004、NFR-002

### AC-004 — 引用漂移失效
- Given：產品、測試、Skill、Schema、環境、command 或未知輸入任一改變
- When：嘗試引用舊結果
- Then：引用被拒絕並要求 fresh execution
- 驗證需求：FR-002、NFR-002

### AC-005 — 前置檢查提早退件
- Given：完整命令未執行且 diff 存在可靜態判定的 blocking 缺陷
- When：preliminary reviewer 執行 precheck
- Then：彙整 blockers，昂貴命令標示 not_run 與 precheck_blocked
- 驗證需求：FR-003

### AC-006 — 前置通過後才跑完整命令
- Given：precheck 沒有 blocker
- When：preliminary review 繼續
- Then：required full commands fresh 執行且 snapshot 前後相同
- 驗證需求：FR-003、NFR-001

### AC-007 — 僅新增 terminal evidence
- Given：preliminary 核准後只新增有效 Outcome、Candidate、snapshot 與 evidence index
- When：final review
- Then：final reviewer 驗證新增內容並安全引用 preliminary full commands
- 驗證需求：FR-004

### AC-008 — 實質內容改變觸發重跑
- Given：preliminary 後修改產品、測試、Skill、Schema 或 command input
- When：final review
- Then：reuse validation 失敗並 fresh 重跑 required commands
- 驗證需求：FR-004、NFR-002

### AC-009 — Local 與 release 分流
- Given：一般本機工作或明示跨平台要求的工作
- When：形成新 Ready plan
- Then：前者可由 local profile 完成；後者要求指定平台 evidence；狀態不混淆
- 驗證需求：FR-005、TR-001

### AC-010 — Evidence bundle 完整且原子
- Given：command 成功、失敗與 timeout
- When：runner 指定 evidence bundle
- Then：index 與 stdout／stderr 原子保存，狀態、耗時、digest 與 identity 完整且不含秘密
- 驗證需求：FR-006、NFR-005

### AC-011 — Evidence 缺失不能引用
- Given：raw output 缺失、digest 不符、path redirect 或 identity 不合
- When：consumer 驗證 evidence bundle
- Then：fail closed 且不產生通過的 Outcome／review input
- 驗證需求：FR-006、NFR-002、NFR-005

### AC-012 — 自動產生檢視
- Given：schema-valid handoff 與 verification index
- When：執行唯讀 render
- Then：同一輸入產生相同命令摘要、追溯表與 evidence overview
- 驗證需求：FR-007

### AC-013 — 中文自然問題命中
- Given：真實中文流程問題與現有契約
- When：執行 knowledge query
- Then：Top-5 包含能回答問題的 owner contract source_ref，無效來源仍排除
- 驗證需求：FR-008

### AC-014 — Fixture 分段量測與隔離
- Given：Windows Delivery tests 與獨立 worker roots
- When：執行 profiling 與可平行群組
- Then：報告 setup/body/cleanup；結果等價、無 collision／殘留，performance tests 單獨執行
- 驗證需求：FR-009

### AC-015 — Archive 驗證與續跑
- Given：完整 archive 或缺檔／漂移／錯 run archive
- When：verify／import
- Then：完整者恢復同一 run evidence；無效者零 mutation 失敗且不繼承 approval
- 驗證需求：FR-010、NFR-002、NFR-005

### AC-016 — 30% 中位數改善
- Given：相同機器、環境、snapshot 與三次無退件 baseline／optimized local runs
- When：比較 validation wall time
- Then：optimized 中位數至少降低 30%，五類流程時間均有值或 unavailable reason
- 驗證需求：NFR-003

### AC-017 — 舊契約相容
- Given：現有 Ready plans、reports、Outcomes、records 與 CI
- When：載入及驗證
- Then：舊資料無需改寫仍可讀；release CI 保持既有跨平台權威
- 驗證需求：NFR-004、TR-001

## 7. 成功指標

| 指標 ID | 對應成果 | 指標與計算方式 | 基準 | 目標 | 量測期間／資料來源 |
|---|---|---|---|---|---|
| KPI-001 | BG-001 | 三次 local 無退件 validation wall time 中位數 | 三角色完整驗證加額外 BDD 約 54 分鐘 | 降低至少 30% | 同機 benchmark report |
| KPI-002 | BG-001 | 相同 snapshot 中 covered command 的執行次數 | full suite 外另跑 BDD/build/governance | 每角色每底層命令最多一次 | execution plan |
| KPI-003 | BG-002 | Required command 有完整自動 evidence 比例 | 需手動整理 | 100% | verification index |
| KPI-004 | BG-003 | 中文真實問題 Top-5 answer-source 命中率 | 指定兩題為 0% | corpus 100% | search-quality report |
| KPI-005 | BG-003 | 長測試可歸因比例 | command aggregate | setup/body/cleanup 100% 可量測 | fixture metrics |
| KPI-006 | BG-003 | 流程時間分類覆蓋 | phase wall time混合工作與等待 | 五類均明示數值或 unavailable reason | process metrics |

## 8. 追溯矩陣

| 業務成果 | 旅程 | 需求 | 驗收情境 | 成功指標 |
|---|---|---|---|---|
| BG-001 | J-001、J-002 | FR-001..005、NFR-001..004、TR-001 | AC-001..009、AC-016、AC-017 | KPI-001、KPI-002 |
| BG-002 | J-001、J-003 | FR-006、FR-007、NFR-002、NFR-005 | AC-010..012 | KPI-003 |
| BG-003 | J-003 | FR-008..010、NFR-003、NFR-005 | AC-013..016 | KPI-004..006 |

## 9. 已確認決策、假設與依賴

### 已確認決策

- D-001：整筆工作總時間是首要速度目標；決策者為使用者。
- D-002：可調整流程，但保留可追溯 evidence、獨立品質檢查及三道人工作業核准；決策者為使用者。
- D-003：日常完成預設使用 local profile；跨平台與 GitHub evidence 留在 release validation，除非來源需求明示跨平台；決策者為使用者。
- D-004：主代理與 preliminary reviewer 各執行一次完整本機驗證；final reviewer只在嚴格 reuse 契約成立時引用 preliminary commands。
- D-005：第一輪效能目標為同機同環境三次中位數降低至少 30%。

### 已確認假設

- A-001：Python standard library、Git 與 ripgrep 維持現有 runtime/toolchain。
- A-002：本成果沒有外部使用者資料、UI、身分、金融／醫療／法規或遠端服務，高風險面不適用。
- A-003：Markdown 可改變 Agent 行為，必須納入輸入分類與 drift 判斷。

### 依賴與外部限制

- DEP-001：delivery-run/v1、ready-plan/v1、execution records、Knowledge Candidate 與 Human Gate contracts 是相容性權威。
- DEP-002：Windows 效能受檔案系統與防毒影響；比較必須同機同環境。
- DEP-003：跨平台 release evidence 仍由既有 GitHub workflow 或等價 release command 提供。

### 延後至技術規劃的決策

- TP-001：Coverage graph、execution plan 與 reuse identity 的 versioned schema。
- TP-002：Precheck report 與 final review reuse 的 closed interface。
- TP-003：Evidence archive、render CLI、retention 與 import/export 邊界。
- TP-004：中文 tokenization／query expansion 的 deterministic 規則。
- TP-005：可平行 Delivery test 分組與 worker isolation 實作。

## 10. 完整性與開放事項

- 阻塞性開放事項：無。
- 品質門檻：需求涵蓋目標、角色、scope、旅程、功能、效能、相容、安全、失敗、復原、移轉與可判定驗收；高風險面依 A-002 不適用。
