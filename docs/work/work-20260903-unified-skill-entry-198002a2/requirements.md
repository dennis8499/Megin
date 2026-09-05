# 需求分析：統一 Skill 入口與流程授權

- 文件狀態：Ready
- 日期：2026-09-03
- 文件範圍：統一本 repository 的 governed SDLC 交付入口，限制 Requirements、Planning 與 Implementation child skills 只能在有效流程階段內改變狀態，同時保留明確的唯讀、治理、恢復與測試例外
- 需求來源：使用者 2026-09-03 對統一入口、自動流程與人工 Gate 的明示需求及後續確認；現行 Delivery、Requirements、Planning、Implementation、Project Knowledge 與 Skill authoring 契約
- 確認者：user；approval evidence `conversation:requirements-work-20260903-unified-skill-entry-198002a2-candidate-1`

## 1. 執行摘要

### 問題或機會

現行 `delivery-orchestrator` 已擁有 worktree、delivery state、phase routing 與人工核准，但 Requirements、Technical Planning 與 Implementation 仍各自以可被獨立發現的入口描述存在，Implementation 亦明確保留 standalone execution。使用者或代理若直接選取 child skill，可能繞過統一 identity、phase、approval、resume 與 audit 路徑，並把正確流程順序留給人類記憶。

### 為何現在做

目前流程已具備 `delivery-run/v1`、原子 transition、兩次上游人工核准、fresh review 與 knowledge promotion gate，適合把「正確路由」提升為可驗證的入口授權，而不需重建整套交付機制。若維持多個等價公開入口，新增的安全與稽核契約仍可能被 standalone 路徑繞過。

### 預期成果

- BG-001：Repository maintainer 只需提出工作意圖，系統即可選擇正確 SDLC 路徑，並確保所有 governed 狀態變更都受同一份可驗證流程 identity、人工 Gate 與稽核紀錄約束。

## 2. 利害關係人與角色

| 角色 ID | 角色 | 需求／責任 | 決策或權限邊界 |
|---|---|---|---|
| ACT-001 | Repository maintainer／使用者 | 從單一入口提出新工作、續接工作或直接點名 stage skill | 核准 Requirements、Plan 與既有 knowledge promotion Gate；不需記憶 child skill 順序 |
| ACT-002 | Delivery orchestrator | 分類意圖、建立或續接 run、授權目前 phase、保存 transition 與自動前進／回流 | 唯一可改變 delivery phase；不得代替人工核准 |
| ACT-003 | Stage child skill | 在被授權的 phase 內產生其擁有的內容與結果 | Requirements、Planning、Implementation 不得自行建立流程 identity、跳階段或在未授權時寫入 |
| ACT-004 | Read-only／governance operator | 執行診斷、查詢、審查、治理與恢復 | 僅能走明列例外；任何產品或正式 stage artifact 寫入仍受其 owner Gate 約束 |
| ACT-005 | Reviewer／maintainer | 驗證 routing、zero-write、相容性與完整流程 | 只接受可重現的 static、unit、integration 與 forward evidence |

## 3. 範圍與優先順序

### 範圍內

- 沿用 `delivery-orchestrator` 作為 governed SDLC 狀態變更的統一公開入口。
- 新建與續接 standard／BUG delivery 的 intent routing、workspace identity、phase authorization、人工 Gate、自動前進、回流、Blocked 與 resume 行為。
- `requirements-discovery`、`technical-planning`、`implementation-execution` 的直接呼叫邊界、失敗結果、UI 提示與 owner／integration validators。
- 以 machine-verifiable `delivery-run/v1`、repo／worktree／generation、current phase/status 與 current refs 作為 child 寫入前置授權。
- 保留並明確分類唯讀 diagnosis／query／review、Project Knowledge 治理／恢復、isolated maintenance evaluator 與非 governed 微小文字／格式處理。
- 現有 active delivery record、歷史 Ready artifacts、BUG overlay、knowledge overlay 與安全不變量的相容性。

### 範圍外

- 建立新的外部服務、daemon、網路依賴、帳號權限系統或通用 workflow engine。
- 重新命名 skill folder、`delivery-run/v1` discriminator、既有 Work ID、artifact path 或歷史 record。
- 改變 Requirements、Plan、fresh review 或 knowledge promotion 的內容品質與核准標準。
- 把純解說、一般問答或完全不涉及 repository／SDLC 的工作強制納入 delivery run。
- 以隱藏 skill、移除所有 child 可測性或把全部階段合併成單一巨型 `SKILL.md` 取代流程授權。
- 自動 commit、push、merge、deploy 或 cleanup。

### 非目標

- 不宣稱 Skill metadata 本身是安全邊界；真正的寫入權必須由可重算的流程狀態決定。
- 不禁止 maintainer 在隔離 fixture 中直接執行 child validators、unit tests 或 forward evaluators。
- 不新增每個 stage 都需人工確認的額外 Gate。

### 優先順序

Must 順序為：禁止未授權狀態變更、保留人工決策、相容與可恢復、自動路由、降低使用者認知負擔。便利性不得弱化 fail-closed、approval binding、秘密處理或 Git 邊界。

## 4. 使用者與業務旅程

### J-001 — 從意圖完成 governed delivery

- 主要角色：ACT-001、ACT-002、ACT-003
- 觸發與前置條件：使用者提出新功能、修錯、實質重構或介面／資料／依賴行為變更，或續接既有 Work ID。
- 主要流程：統一入口分類請求；建立或定位合法 delivery run；依 current phase 只載入一個 child；Requirements 與 Plan 分別完整展示並取得人工核准；Plan Ready 後自動進入 Implementation；結果經 fresh review 與既有 knowledge Gate 後完成。
- 替代、例外與復原：需求缺口回 Requirements；implementation upstream gap 回 Planning；invalid／drifted context 無副作用停止；Blocked 解除後從同 phase resume。
- 完成結果：delivery record、正式 artifacts、review evidence 與實際 workspace 可互相重算，未授權 child 沒有寫入。
- 相關需求：FR-001、FR-002、FR-003、FR-004、FR-005、NFR-001
- 驗收情境：AC-001、AC-002、AC-003、AC-004、AC-005

### J-002 — 直接點名 child skill

- 主要角色：ACT-001、ACT-003
- 觸發與前置條件：使用者或代理直接要求 Requirements、Planning 或 Implementation，且可能沒有合法 current delivery context。
- 主要流程：child 在任何 artifact／產品／外部寫入前驗證流程授權；合法且 phase 相符時執行目前 stage；缺少、錯誤或過期時回傳 routing-required 結果並交回統一入口。
- 替代、例外與復原：存在多個 active run 時只列安全的 Work IDs 並等待選擇；record drift 時進 Blocked，不依 branch 名或相似 path 猜測。
- 完成結果：直接呼叫不能形成第二條 standalone 狀態變更路徑。
- 相關需求：FR-002、FR-003、FR-006、NFR-002
- 驗收情境：AC-002、AC-003、AC-006

### J-003 — 使用明列的非變更例外

- 主要角色：ACT-001、ACT-004
- 觸發與前置條件：請求是唯讀 BUG diagnosis、knowledge query、唯讀 review、治理／恢復、隔離 evaluator，或不屬於 governed delivery 的微小文字／格式工作。
- 主要流程：統一 routing boundary 將請求送入明列例外，不建立不必要 delivery run；例外 owner 仍執行自己的零寫入或人工核准契約。
- 替代、例外與復原：一旦請求需要產品或正式 stage artifact 寫入，重新進入或續接 governed delivery；Project Knowledge apply 仍需 exact sealed payload 的獨立人工核准。
- 完成結果：可組合性、診斷與恢復能力保留，但不能作為繞過 delivery Gate 的旁路。
- 相關需求：FR-007、FR-008、NFR-003
- 驗收情境：AC-007、AC-008

## 5. 需求

### BR-001 — 統一 governed entry

- 需求：所有新的 governed SDLC 狀態變更必須先由 `delivery-orchestrator` 建立或續接可驗證的流程上下文；Requirements、Planning 與 Implementation child skill 在缺少正確 phase 授權時不得寫入或推進狀態。
- 理由與來源：BG-001、J-001、J-002；使用者 2026-09-03 明示同意「唯一公開入口＋受流程約束的內部 Skills」；`.agents/skills/delivery-orchestrator/SKILL.md:10` 已定義 orchestrator／child ownership。
- 優先順序：Must；這是本成果的核心安全與可預測性邊界。
- 驗收：AC-001、AC-002、AC-003

### FR-001 — 意圖路由

- 需求：系統必須把新功能、已完成分診的修錯、實質重構及介面／資料／依賴行為變更路由到 `delivery-orchestrator`，並從合法 record 的最早未完成 phase 自動繼續。
- 理由與來源：BR-001、J-001；`.agents/skills/delivery-orchestrator/SKILL.md:14-22` 與 `references/stage-routing.md:7-20`。
- 優先順序：Must。
- 驗收：AC-001、AC-005

### FR-002 — Child phase authorization

- 需求：Requirements、Planning 與 Implementation child 必須在任何 repository artifact、產品、測試、設定、依賴或外部狀態寫入前，驗證 caller 所提供的 current `delivery-run/v1`、repo／worktree、Work ID、generation、phase與status；只有 exact current phase 的 `active` context 可以授權該 child 執行。
- 理由與來源：BR-001、J-002；現行 Implementation 只在 caller 明示提供 record 時載入 orchestrated gate，並仍保留 standalone 路徑（`.agents/skills/implementation-execution/references/orchestrated-delivery.md:5-17`）。
- 優先順序：Must。
- 驗收：AC-002、AC-003、AC-004

### FR-003 — 無副作用拒絕與回路

- 需求：child 遇到缺少、schema-invalid、identity mismatch、非 current phase、非 `active`、hash drift 或無法唯一定位的流程 context 時，必須在零 repository／registry／branch／worktree／外部狀態 mutation 下產生明確 routing-required 或 Blocked 結果，並由統一入口決定 new、resume、選擇或 recovery。
- 理由與來源：J-002；`.agents/skills/delivery-orchestrator/references/workspace-and-run.md:70-76` 要求 continuity 不可由 branch 名或相似文字猜測。
- 優先順序：Must。
- 驗收：AC-002、AC-003、AC-006

### FR-004 — 單一 transition owner

- 需求：只有 `delivery-orchestrator` 可以根據已持久化的 child 結果執行全域 phase／status transition；child 不得自行跳過、重做或宣稱未被 record 接受的下游 phase。
- 理由與來源：BR-001、J-001；`.agents/skills/delivery-orchestrator/SKILL.md:47-62` 已定義 child 先持久化、orchestrator 再原子 transition。
- 優先順序：Must。
- 驗收：AC-004、AC-005

### FR-005 — 自動前進與人工 Gate

- 需求：系統必須在合法 child 結果後依既有 state machine 自動前進或回流；Requirements Candidate、Plan Candidate 與 required knowledge promotion 仍必須完整展示並取得各自既有人工核准，第二道 Plan 核准後不得再詢問是否開始 Implementation。
- 理由與來源：J-001；`.agents/skills/delivery-orchestrator/SKILL.md:28`、`references/stage-routing.md:9-20`。
- 優先順序：Must。
- 驗收：AC-001、AC-005

### FR-006 — 直接點名的可預測結果

- 需求：使用者明示 `$requirements-discovery`、`$technical-planning` 或 `$implementation-execution` 時，系統必須先套用相同 phase authorization；有效 context 繼續該 phase，無效 context 回到 `delivery-orchestrator`，不得因明示 skill 名稱而取得額外寫入權。
- 理由與來源：J-002；`.agents/skills/writing-great-skills/SKILL.md:15-18` 說明 model-invoked skill 同時保留 human reach，因此不能只靠 invocation metadata 排除直接使用。
- 優先順序：Must。
- 驗收：AC-002、AC-003

### FR-007 — 唯讀與治理例外

- 需求：系統必須保留 standalone 的唯讀 BUG diagnosis、Project Knowledge query／diagnostic lint、唯讀 review，以及明示的 Project Knowledge candidate／apply／recover 治理流程；這些例外不得修改產品或正式 Requirements／Plan／Implementation artifacts，且其既有人工核准與 safety contract 不變。
- 理由與來源：J-003；`.agents/skills/bug-diagnosis/SKILL.md:10-24`、`.agents/skills/project-knowledge/SKILL.md:9-19`。
- 優先順序：Must；避免統一入口成為診斷或 recovery 的單點阻塞。
- 驗收：AC-007、AC-008

### FR-008 — Maintenance 與非 governed 例外

- 需求：系統必須允許 isolated validators、unit／integration tests、forward evaluators 與 skill maintenance 直接載入 child contracts；純解說及不改變行為、介面、資料、依賴或正式 stage artifact 的微小文字／格式工作不得建立 delivery run。
- 理由與來源：J-003；`.agents/skills/delivery-orchestrator/references/behavior-evaluation.md:21-23`、`:55-65`。
- 優先順序：Must。
- 驗收：AC-007

### TR-001 — 現有流程相容

- 需求：改進後系統必須繼續接受 schema-valid 的既有 active delivery records、standard／BUG overlays、required／legacy knowledge policy 與歷史 Ready artifacts；不得重新命名或隱式遷移既有 identity、paths、records 或 schema discriminator。
- 理由與來源：J-001；`.agents/skills/delivery-orchestrator/references/workspace-and-run.md:43-68` 明列 legacy 與 optional overlays。
- 優先順序：Must。
- 驗收：AC-005、AC-009

### NFR-001 — Deterministic fail-closed

- 需求：在相同 repository bytes、record bytes 與 invocation input 下，phase authorization 必須產生相同 allow／routing-required／blocked 結果；任何未知欄位、缺失 binding 或 drift 一律不得取得寫入權。
- 理由與來源：BG-001；`.agents/skills/delivery-orchestrator/references/workspace-and-run.md:48-68`。
- 優先順序：Must。
- 驗收：AC-003、AC-004、AC-006

### NFR-002 — 安全、秘密與 Git 邊界

- 需求：統一入口與 child gate 不得降低現有 secret redaction、no-follow path、strict-clean、hook／filter、Git trust、append-only、create-only 或禁止 stage／commit／push／merge／deploy／cleanup 的契約。
- 理由與來源：J-001、J-002；`.agents/skills/delivery-orchestrator/SKILL.md:24-31`、`references/workspace-creation.md:19-42`。
- 優先順序：Must。
- 驗收：AC-006、AC-009

### NFR-003 — 可維護與可發現

- 需求：改進後必須維持 child skill 的單一內容 ownership、progressive disclosure 與獨立測試能力；公開描述與 UI prompt 必須使一般 governed 變更優先發現統一入口，並使 child 描述只在合法 routed phase 或明列例外時成立。
- 理由與來源：BG-001、J-002、J-003；`.agents/skills/writing-great-skills/SKILL.md:10-18`、`:39-52` 與 `.agents/skills/delivery-orchestrator/SKILL.md:10`。
- 優先順序：Must。
- 驗收：AC-001、AC-002、AC-007

### NFR-004 — 效能與依賴相容

- 需求：改進後不得新增 runtime dependency、network requirement、persistent service 或跨 invocation cache，且必須維持現有 50k repository 的 Delivery probe／transition 小於兩秒效能 Gate。
- 理由與來源：既有 canonical implementation claim `docs/knowledge/topics/work-20260902-skill-script-performance-0ae7b62a-implementation.md:5-7`。
- 優先順序：Must。
- 驗收：AC-009

## 6. 驗收情境

### AC-001 — 新 governed 變更自動走統一入口

- Given：strict-clean attached primary，沒有可續接 active run，使用者提出新的行為或架構變更
- When：agent 選擇工作流程
- Then：只由 `delivery-orchestrator` 建立一個 Work ID／branch／worktree／record，進入 Requirements；沒有 child 建立第二份 identity
- 驗證需求：BR-001、FR-001、FR-005、NFR-003

### AC-002 — 無 context 直接叫 Requirements 或 Planning

- Given：沒有合法 current delivery record，或 record phase 不等於所點名 child
- When：使用者直接明示 `$requirements-discovery` 或 `$technical-planning`
- Then：回傳 routing-required 並交回統一入口；repository、registry、branch、worktree 與外部狀態 hashes 完全不變
- 驗證需求：BR-001、FR-002、FR-003、FR-006

### AC-003 — 無 context 直接叫 Implementation

- Given：有一份 Ready plan，但沒有合法 `implementation/active` delivery context，或 context 的 Work ID／workspace／generation／requirements／handoff／approval 任一 mismatch
- When：使用者或代理直接明示 `$implementation-execution`
- Then：不得建立新的 execution run或修改產品；結果為 routing-required 或 Blocked，並指出需由統一入口 new／resume／recover
- 驗證需求：BR-001、FR-002、FR-003、FR-006、NFR-001

### AC-004 — 有效 current phase 授權 child

- Given：schema-valid `delivery-run/v1` 的 repo、worktree、Work ID、generation、phase、status、current refs 與 actual bytes 全部相符
- When：orchestrator 路由到唯一 current child
- Then：只有該 child 取得其 owner 契約允許的寫入權；其他 phase child 與 child 自行 transition 均被拒絕
- 驗證需求：FR-002、FR-004、NFR-001

### AC-005 — Gate、自動前進、回流與 resume

- Given：合法 delivery 依序產生 Requirements Candidate、Ready Requirements、Plan Candidate、Ready Plan、Implementation 或 upstream gap
- When：使用者核准或拒絕 Candidate，或 child 回傳 persisted outcome
- Then：核准前不進下游；Requirements 核准後自動進 Planning；Plan 核准後自動進 Implementation；gap 只沿合法回流；resume 不重做已持久化核准
- 驗證需求：FR-001、FR-004、FR-005、TR-001

### AC-006 — Tamper 與多 active run fail closed

- Given：分別提供 unknown schema field、record hash drift、錯誤 branch／worktree、非 active status、錯誤 phase，以及多個無法唯一選擇的 active runs
- When：入口或 child 嘗試取得執行權
- Then：每個不合法案例在零未記錄 mutation 下拒絕；多 run 只列 Work IDs，不能猜測；秘密與 raw Git output 不出現在錯誤訊息
- 驗證需求：FR-003、NFR-001、NFR-002

### AC-007 — 唯讀與 maintenance 例外仍可用

- Given：乾淨 session 中分別提出 BUG diagnosis、knowledge query、唯讀 review、isolated validator／evaluator、純解說及微小文字／格式請求
- When：統一 routing boundary 分類請求
- Then：不建立不必要 delivery run；唯讀分支的 repository／外部 bytes 不變；maintenance fixture 不污染實際 workspace
- 驗證需求：FR-007、FR-008、NFR-003

### AC-008 — Governance mutation 不成為旁路

- Given：Project Knowledge candidate／apply／recover 請求，或唯讀分支途中發現需要產品／正式 stage artifact 變更
- When：操作者嘗試寫入
- Then：Knowledge mutation 仍要求 exact sealed payload 的既有獨立人工 approval；產品／stage artifact 變更回到 governed delivery，不能借例外寫入
- 驗證需求：FR-007

### AC-009 — 相容、安全與效能完整回歸

- Given：既有 standard／BUG、required／legacy fixtures、50k performance fixture與完整 owner suites
- When：執行 static、unit、integration、forward、full build／test 與跨平台契約驗證
- Then：既有合法 record／artifact 可續接；全部適用案例 100% pass；沒有新 dependency／network；現有安全矩陣與小於兩秒 Gate 通過
- 驗證需求：TR-001、NFR-002、NFR-004

## 7. 成功指標

| 指標 ID | 對應成果 | 指標與計算方式 | 基準 | 目標 | 量測期間／資料來源 |
|---|---|---|---|---|---|
| KPI-001 | BG-001 | 未授權 Requirements／Planning／Implementation forward cases 中零寫入通過數 ÷ 適用案例數 | 現行 child skills 仍允許 standalone 路徑 | 100%，且未授權寫入事件為 0 | 每次 full behavior evaluation；前後 repository／registry／branch／worktree／external sentinel hashes |
| KPI-002 | BG-001 | Governed end-to-end、回流、resume、BUG、knowledge 與 legacy cases 通過數 ÷ 適用案例數 | 現行 owner suites 已建立 | 100% | 每次 owner／integration suite 與 fresh review |
| KPI-003 | BG-001 | 正常 governed 意圖需由使用者明示的 child skill 名稱數 | 使用者可直接面對多個 stage entry | 0；只需描述意圖或 Work ID | Forward routing evaluator |
| KPI-004 | BG-001 | 50k fixture 的既有 Delivery probe／transition gate | 已核准基準皆小於 2 秒 | 每個既有樣本仍小於 2 秒 | 完整 performance suite |

## 8. 追溯矩陣

| 業務成果 | 旅程 | 需求 | 驗收情境 | 成功指標 |
|---|---|---|---|---|
| BG-001 | J-001 | BR-001、FR-001、FR-004、FR-005、TR-001、NFR-001、NFR-002、NFR-004 | AC-001、AC-004、AC-005、AC-006、AC-009 | KPI-001、KPI-002、KPI-004 |
| BG-001 | J-002 | FR-002、FR-003、FR-006、NFR-001、NFR-003 | AC-002、AC-003、AC-004、AC-006 | KPI-001、KPI-003 |
| BG-001 | J-003 | FR-007、FR-008、NFR-003 | AC-007、AC-008 | KPI-002、KPI-003 |

## 9. 已確認決策、假設與依賴

### 已確認決策

- D-001：沿用 `delivery-orchestrator` 作為 governed 狀態變更的統一公開入口，不新增第二層 umbrella skill；理由是現有 Skill 已擁有 workspace、state、routing 與 transition authority。
- D-002：「不能單獨呼叫」定義為 child 在缺少合法流程授權時不能改變 repository、delivery 或外部狀態；不以無法測試、無法載入或單靠 prompt 隱藏作為完成標準。
- D-003：Requirements、Planning 與 Implementation 是受限制 child；BUG diagnosis、knowledge query、唯讀 review、governance／recovery 與 isolated maintenance 是明列例外。
- D-004：保留現有 Requirements、Plan、fresh review 與 knowledge promotion Gate，不新增每 stage 額外人工中斷點。
- D-005：child 保持各自內容品質的唯一 owner，orchestrator 保持全域流程與 transition 的唯一 owner。
- D-006：純解說及不影響行為／正式 artifact 的微小文字／格式工作不建立 delivery run；一旦範圍擴成 governed change，即重新分類。

### 已確認假設

- A-001：本次「Skills」指 repository 內 `.agents/skills` 的 SDLC bundle；依目前 workspace 與對話主題確認。
- A-002：使用者接受前一輪建議中的唯讀、治理、恢復與測試例外；來源為 2026-09-03 回覆「好，請幫我改進」。

### 依賴與外部限制

- DEP-001：`delivery-run/v1`、workspace helper 與 transition validator 必須持續提供 exact identity、phase、status、hash 與 append-only evidence。
- DEP-002：Skill invocation metadata 只有 discoverability／UI 效果，不能獨自保證 authorization；child owner contracts 與 deterministic validators 必須共同成立。
- DEP-003：Project Knowledge required overlay 使 Requirements、Plan 與最終 implementation knowledge 各自受 exact Candidate／receipt／lint contract 約束。

### 延後至技術規劃的決策

- TP-001：phase authorization 採擴充現有 `locate`／record validator、建立薄 gate seam，或由各 owner consumer 重用既有 validation primitive。
- TP-002：child description、`agents/openai.yaml`、SKILL body、delivery protocol 與 validators 的最小修改集合。
- TP-003：如何區分 direct user invocation、orchestrator route 與 isolated maintenance fixture，而不新增可偽造的 conversational flag。
- TP-004：standalone Implementation 移除後，是否需要針對已存在 host-temp standalone execution run 的 create-only compatibility marker；不得用未驗證猜測擴大相容面。

## 10. 完整性與開放事項

- 阻塞性開放事項：無。
- 品質門檻：13 個覆蓋面均已分類；本成果不涉及法規、醫療、金融、個資處理或其他高風險 domain。每個需求均有來源、單一可觀察義務、正常／拒絕／回流／恢復／相容驗收與成功指標；純實作選擇已移至 TP-001..004。需求品質契約通過。
