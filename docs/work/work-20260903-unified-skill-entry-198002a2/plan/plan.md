# 技術規劃：統一 Skill 入口與流程授權

- 狀態與核准證據：見 `handoff.json.approval`
- Candidate revision：`candidate-20260903-unified-entry-01`
- 日期：2026-09-03
- 來源規格：`docs/work/work-20260903-unified-skill-entry-198002a2/requirements.md`
- Planning baseline：repo `0c5534020993ce0e527ffefdd0bbbdf8e3e26138d3933defe22de1ed5ea2530c`；HEAD `ef4747d89d83ef7fcd4136d7da30126c49b5c6c9`；status `c715615c8c02737d91ace08f7b68cc008f606ec78bc875b8848a9de3d35c02e1`
- Primary／handoff：`docs/work/work-20260903-unified-skill-entry-198002a2/plan/plan.md`／`docs/work/work-20260903-unified-skill-entry-198002a2/plan/handoff.json`

## 1. 成果、範圍與限制

成果是一條可機器驗證的 governed SDLC 入口：`delivery-orchestrator` 仍是唯一全域流程 owner；`requirements-discovery`、`technical-planning`、`implementation-execution` 只在目前 `delivery-run/v1` 的 exact active phase 內擁有其內容寫入權。使用者直接點名 child skill 時也先執行同一授權，不產生第二條 standalone mutation 路徑。

- 範圍內：Delivery 唯讀 phase authorization、統一 routing 契約、三個 child 的 entry／UI／owner validation、Implementation standalone disposition、跨 skill behavior 與完整回歸。
- 範圍外：新 workflow engine、daemon、network／runtime dependency、schema discriminator／folder／artifact rename、自動 commit／push／merge／deploy／cleanup，以及 Requirements／Plan／fresh review／knowledge Gate 品質標準變更。
- 明列例外：唯讀 BUG diagnosis、Knowledge query／diagnostic lint／read-only review、明示 Knowledge candidate／apply／recover、isolated validators／tests／evaluators，以及不改變行為或正式 stage artifact 的微小文字／格式工作。
- 權限原則：metadata 與 prompt 只負責 discoverability；寫入授權只來自可重算的 persisted run 與實際 repository／worktree bytes。

| ID | Required／Observed 限制 | 來源 |
|---|---|---|
| CON-001 | 只有 orchestrator 可建立／續接 identity 與改變 global phase／status。 | SRC-SPEC、SRC-ORCH-SKILL、SRC-ORCH-ROUTE |
| CON-002 | Child 在任何 repository／artifact／產品／外部寫入前取得 exact phase authorization；無授權即零寫入。 | SRC-SPEC、SRC-REQ-SKILL、SRC-PLAN-SKILL、SRC-EXEC-SKILL |
| CON-003 | Requirements、Plan、fresh review、Knowledge approval Gate 與自動前進／回流維持既有語義。 | SRC-SPEC、SRC-ORCH-ROUTE、SRC-ORCH-BEHAVIOR |
| CON-004 | `allow_implicit_invocation: true` 保留 child 可由 router reach；直接點名不增加權限。 | SRC-SPEC、SRC-SKILL-GUIDE、SRC-REQ-YAML、SRC-PLAN-YAML、SRC-EXEC-YAML |
| CON-005 | 現有合法 active record／overlay／歷史 Ready artifact 可讀可續接；既有 standalone ledger 不刪除、不遷移，但不得再授權產品寫入。 | SRC-SPEC、SRC-EXEC-ROUTE、SRC-ORCH-BEHAVIOR |
| CON-006 | 現有 Git trust、secret redaction、no-follow、strict-clean、append／create-only 與 <2 秒 performance gates 不弱化。 | SRC-SPEC、SRC-ORCH-FACADE、SRC-ORCH-VALIDATOR |

## 2. 證據與變更影響

| 來源群 | 已觀察事實 | 直接工作包 |
|---|---|---|
| SRC-SPEC | Ready requirements 固定 BR／FR／TR／NFR、AC-001..009 與例外。 | WP-001..005 |
| SRC-ORCH-* | Orchestrator 已擁有 worktree、record、routing 與 transition；public CLI 只有 probe／start／locate／transition，`locate` 已驗證 schema、latest generation 與 approved upstream。 | WP-001、WP-005 |
| SRC-REQ-* | Requirements 可被獨立發現，owner validator 尚未要求 routed context。 | WP-002 |
| SRC-PLAN-* | Planning 可被獨立發現，owner validator 尚未要求 routed context。 | WP-003 |
| SRC-EXEC-* | Implementation 只有 caller 明示 record 才載入 orchestration gate，並明確允許 standalone execution。 | WP-004 |
| SRC-SKILL-GUIDE | Model-invoked child 必須保持 router reach；因此不能靠 invocation metadata 當授權。 | WP-002、WP-003、WP-004 |

### Current → target

| Impact ID | 能力 | 變更 | 需求 |
|---|---|---|---|
| IMP-001 | Delivery public facade | New `authorize` command／function；refactor locate 共享同一 probe；preserve 既有四個 command JSON。 | FR-002、FR-003、NFR-001、NFR-002、NFR-004 |
| IMP-002 | Requirements entry | Modified entry／UI／validator／behavior：只接受 `requirements/active`；否則 route back。 | BR-001、FR-002、FR-003、FR-006、NFR-003 |
| IMP-003 | Planning entry | Modified entry／UI／validator／behavior：只接受 `planning/active`；plan-only read-only 解說仍不建立 run。 | BR-001、FR-002、FR-003、FR-006、FR-008 |
| IMP-004 | Implementation entry | Removed new standalone mutation；Modified preflight／UI／validator／behavior；preserve historical bytes。 | FR-002、FR-003、FR-006、TR-001 |
| IMP-005 | Unified routing | Modified Delivery routing／behavior／integration tests，保留 Gate、自動前進、回流、例外與效能。 | FR-001、FR-004、FR-005、FR-007、FR-008、AC-005..009 |

## 3. 設計與決策

### TD-001 — Persisted phase authorization seam

- 需求／證據：BR-001、FR-002、FR-003、FR-006、NFR-001、AC-002..004、AC-006；SRC-ORCH-FACADE、SRC-ORCH-VALIDATOR。
- 選定方案與理由：在現有 Delivery facade 新增唯讀 `authorize` seam，以持久化 run 與實際 Git／worktree 證據授權單一 active phase；child metadata 只改善發現性，不作為安全邊界。
- Public API：`authorize_stage(repo, expected_phase, *, root=None, work_id=None) -> dict`；CLI：`authorize --repo <path> --phase requirements|planning|implementation [--work-id <id>] [--registry-root <path>]`。
- 驗證順序：以 hardened Git probe 取得 canonical repo／worktree → 依 repo ID 與 optional Work ID 定位唯一 record → owner validator 驗證 `delivery-run/v1`、latest generation 與 approved upstream materialization → 比對 requested canonical worktree、phase 與 `active` status → 回傳 binding。
- 成功結果：`outcome: authorized`，包含 schema、Work ID、generation、phase、status、canonical worktree、base、artifact root 與 record path；child 只消費此結果，不自行 transition。
- 拒絕結果：無 record、錯 worktree、錯 phase 或非 active 回 `outcome: routing_required` 與固定 reason enum；ambiguous、schema-invalid、hash／workspace drift 沿既有 redacted `DeliveryError` fail closed。兩類都不得寫 registry、repo、branch、worktree 或外部狀態。
- 實作 seam：將 `locate_workspace` 的 probe 後邏輯抽成 private helper，讓 locate／authorize 共用同一 observation，避免重複 Git probe並保持 <2 秒 gate。
- 排除方案：不新增 caller token、`--orchestrated` flag、環境變數或對話標記，因其可偽造；不把 child 改成 user-only，因 router 會失去 reach。

### TD-002 — Single-source stage policy

- 需求／證據：FR-001、FR-004、FR-005、FR-006、NFR-003；SRC-ORCH-SKILL、SRC-ORCH-ROUTE、SRC-SKILL-GUIDE。
- 新增 `delivery-orchestrator/references/stage-authorization.md` 作為唯一授權語義 owner，列出受限制 phases、結果分類、零寫入邊界、例外與 child call protocol。
- Delivery `SKILL.md`／UI 以「governed 變更統一入口」為 discoverability leading words；三個 child 的 description／UI 保持 model-invoked，但只描述「由 Delivery 路由的 current phase」。
- Child body 第一個 state-changing completion criterion 固定為：讀取中央契約、執行 `authorize`、確認 phase-specific authorized binding；失敗即停止並交回 orchestrator。
- 只有 Delivery 可呼叫 `transition`; child 可產生其 owner artifact／outcome，但不擁有全域 state mutation。

### TD-003 — Implementation standalone disposition

- 需求／證據：FR-002、FR-003、FR-006、TR-001、AC-003、AC-009；SRC-EXEC-SKILL、SRC-EXEC-ROUTE、SRC-EXEC-BEHAVIOR。
- 新 invocation：Implementation Preflight 在建立 execution run、ledger、integrity artifact 或產品 diff 前必須先取得 `implementation/active` authorization；僅有 Ready plan 不足以授權。
- 歷史資料：既有 host-temp standalone ledgers 與 Ready artifacts保持原 bytes、可唯讀檢查；不新增 marker、不隱式轉換、不刪除。若要繼續 mutation，統一入口須建立或續接合法 delivery context，再依既有 Ready source binding 執行。
- Maintenance：schema validator、unit／integration／forward evaluator 可在 isolated fixture 直接 import／執行 owner code；該能力不等同產品寫入權。
- 排除方案：不維護新的 standalone compatibility writer，因無既有不可偽造 policy marker可區分舊 run 與新旁路。

### TD-004 — Validator and evaluation closure

- 需求／證據：NFR-001..004、AC-006..009；各 `SRC-*-VALIDATOR` 與 `SRC-*-BEHAVIOR`。
- Delivery validator固定 `authorize` parser／public definition、中央 authority、safe result fields、零 mutation call graph與三個 child structural pointers；每個 child owner validator固定 first-gate wording、phase、central pointer、UI description與保留 implicit reach。
- Mutation tests分別刪除／改寫 `authorize`、phase、central pointer、zero-write、standalone prohibition及 exception boundary，必須使 owner validator red。
- Behavior contracts把先前「direct child／standalone implementation」正向案例改為：有效 active phase 可直接 resume，無／錯 context routing-required；forward report重新捕捉且不得回寫 production workspace外的未宣告位置。
- 完整 Delivery state-machine、BUG、Knowledge required／legacy、security與performance tests保持原 oracle。

### Modules 與 seams

| MOD ID | 責任 | Caller-facing contract | SEAM | 隱藏內容 |
|---|---|---|---|---|
| MOD-001 | DeliveryStageAuthorization | `authorize_stage`／`authorize` JSON | SEAM-001、002 | record lookup、probe sharing、reason mapping |
| MOD-002 | RequirementsRoutedEntry | `requirements/active` 才探索／產生 Candidate | SEAM-003 | frontier／quality owner內容不變 |
| MOD-003 | PlanningRoutedEntry | `planning/active` 才產生 Candidate | SEAM-004 | Ready plan owner內容不變 |
| MOD-004 | ImplementationRoutedEntry | `implementation/active` 才建 run／寫產品 | SEAM-005 | BDD／TDD／ledger／review owner內容不變 |
| MOD-005 | UnifiedRoutingContract | intent → Delivery → current child → persisted result → transition | SEAM-006 | Gate／overlay／resume state machine |

| SEAM ID | 可觀察 interface | 替身／fixture | 層級 |
|---|---|---|---|
| SEAM-001 | `delivery_workspace.py authorize` JSON／exit | real temp Git repo + isolated registry | BDD/integration |
| SEAM-002 | `authorize_stage` deterministic mapping | fixture records + before/after snapshots | unit |
| SEAM-003 | Requirements SKILL／YAML／owner validator | mutation fixture | contract/unit |
| SEAM-004 | Planning SKILL／YAML／owner validator | mutation fixture | contract/unit |
| SEAM-005 | Implementation preflight／owner validator | Ready fixture + mutation fixture | contract/integration |
| SEAM-006 | Delivery routing／behavior evaluator | standard／BUG／legacy fixtures + external sentinel | BDD/forward |

控制流：intent → Delivery locate/start → `authorize(expected phase)` → one child → persisted owner result → Delivery transition → 人工 Gate或下一 phase。任何 mismatch → routing-required／Blocked → Delivery new／select／recover；不進 child mutation branch。

## 4. 測試策略

| BDD-FWK ID | Framework／版本／來源 | Boundary／paths | Discovery／reporting |
|---|---|---|---|
| BDD-FWK-001 | 既有 Python stdlib `unittest` Delivery compatibility runner；Python 3.13 baseline；SRC-ORCH-TEST | behavior tests：`.agents/skills/delivery-orchestrator/scripts/test_delivery_worktree.py`；owner mutation suites；OS temp Git／registry fixture | 新增 runner `--list-tests`；focused/full commands；run=discovered、failed=0、unexpected skipped=0 |

`BOOT-*` 不適用：`delivery_workspace.py` public CLI、`DeliveryFixture`、owner validators與 mutation harness 已存在；第一個 red 是不存在的 `authorize` subcommand／function及尚未要求 routed context 的 owner assertions，不需建立中性 host seam。

| BDD ID | Scenario／fixture／oracle／正確 red | Focused CMD | WP |
|---|---|---|---|
| BDD-001 | Active delivery fixture 對三個 phase逐一測試：只有 requested phase + active + exact worktree 回 `authorized`；目前 parser/function 不存在而 red。 | CMD-BDD-FOCUSED-001 | WP-001 |
| BDD-002 | 無 record、primary worktree、錯 phase、awaiting_user／blocked status 回固定 `routing_required`，before/after repo／registry／branch／worktree／external sentinel hashes相同。 | CMD-BDD-FOCUSED-001 | WP-001 |
| BDD-003 | Requirements 直接點名：合法 `requirements/active` 可執行，其他 context 在 Candidate/temp/repo write前 route back；目前 entry contract未要求 gate而 red。 | CMD-BDD-FOCUSED-001 | WP-002 |
| BDD-004 | Planning 直接點名：合法 `planning/active` 可執行，其他 context零 plan／knowledge Candidate write；plan-only read-only解說仍例外；目前 entry contract未要求 gate而 red。 | CMD-BDD-FOCUSED-001 | WP-003 |
| BDD-005 | Implementation 只有 exact `implementation/active` 可建立 run／diff；Ready plan-only、mismatched Work ID／generation／refs皆零寫入；現行 standalone branch使案例 red。 | CMD-BDD-FOCUSED-001 | WP-004 |
| BDD-006 | Ambiguous active records只輸出 safe Work IDs；unknown field、record/source/hash/workspace drift fail closed且不洩漏 secret/raw Git；既有 validator無 authorize coverage而 red。 | CMD-BDD-FOCUSED-001 | WP-001 |
| BDD-007 | End-to-end standard／BUG／knowledge／resume：Requirements與Plan仍各一次人工 Gate，Plan Ready後自動 Implementation，gap合法回流，child不 transition。 | CMD-BDD-FOCUSED-001 | WP-005 |
| BDD-008 | Read-only／governance／maintenance／micro-edit例外不建 run；一旦要產品或正式 stage artifact寫入即 route Delivery；routing descriptions未統一而 red。 | CMD-BDD-FOCUSED-001 | WP-005 |
| BDD-009 | 既有 active standard／BUG、required／legacy與歷史 Ready artifacts可續接；全安全矩陣與 DeliveryPerformanceTests仍 <2 秒、無新 dependency／network。 | CMD-BDD-FULL-001、CMD-PERFORMANCE-001 | WP-005 |

| TEST ID | BDD／inner oracle | Focused／related CMD |
|---|---|---|
| TEST-001 | BDD-001／002：shared probe lookup、canonical worktree equality、phase/status reason mapping、三 phase enum。 | CMD-TDD-FOCUSED-001／CMD-RELATED-001 |
| TEST-002 | BDD-006：NOT_FOUND、AMBIGUOUS_WORK、INVALID_RECORD、WORKSPACE_DRIFT分類；success與reject路徑不呼叫write／transition primitive。 | CMD-TDD-FOCUSED-001／CMD-RELATED-001 |
| TEST-003 | BDD-003：Requirements entry／YAML含中央 pointer與`requirements` phase，mutation removal使 validator fail。 | CMD-TDD-FOCUSED-002／CMD-RELATED-001 |
| TEST-004 | BDD-004：Planning entry／YAML含中央 pointer與`planning` phase，read-only plan-only discriminator保留。 | CMD-TDD-FOCUSED-003／CMD-RELATED-001 |
| TEST-005 | BDD-005：Implementation先授权再 ledger／product write；standalone permission文字或分支回歸會被 validator／mutation test拒絕。 | CMD-TDD-FOCUSED-004／CMD-RELATED-001 |
| TEST-006 | BDD-007／008：Delivery跨 skill validator固定唯一 entry、exceptions、single transition owner與自動 flow。 | CMD-TDD-FOCUSED-005／CMD-RELATED-001 |
| TEST-007 | BDD-009：完整 owner、state-machine、BUG、knowledge、security、performance inventory zero unexpected skip。 | CMD-TEST-FULL-001／CMD-PERFORMANCE-001 |

執行順序：每個 WP 先讓其 BDD scenario因缺少目標行為正確 red，再讓對應 TEST red；minimal green後 refactor-with-green，跑 focused BDD與related green才進下一個 WP。全部 WP 後 fresh執行 discovery、full BDD、build、test、governance與performance。

## 5. Commands

| CMD | Status | 用途／side effects |
|---|---|---|
| CMD-BDD-DISCOVERY-001 | Proposed | Delivery runner純列出 scenario inventory；無寫入。 |
| CMD-BDD-FOCUSED-001 | Proposed | 統一入口 authorization behavior class；只建立並清除 OS temp fixtures。 |
| CMD-BDD-FULL-001 | Observed | 既有 Delivery compatibility full runner；OS temp fixtures自清。 |
| CMD-TDD-FOCUSED-001..005 | Proposed | core與四個 owner/integration mutation tests；OS temp mutation fixtures自清。 |
| CMD-RELATED-001 | Observed | Knowledge related runner，包含五個 owner validators；只用並清除 `.knowledge-test-tmp/`。 |
| CMD-BUILD-FULL-001 | Observed | repository Python/schema syntax與契約 inventory；無寫入。 |
| CMD-TEST-FULL-001 | Observed | 完整 Knowledge + Requirements + Planning + Implementation + BUG + Delivery suites；temp fixture自清。 |
| CMD-GOVERNANCE-001 | Observed | Project Knowledge治理 lint；無產品寫入。 |
| CMD-PERFORMANCE-001 | Observed | Delivery performance class；OS temp fixture自清，既有 <2 秒 oracle。 |

所有 commands：cwd `.`、network forbidden、無 external service；環境只需 Python 3.13+、Git、ripgrep。精確 argv、timeout、success／completeness與 absence evidence由 `handoff.json` 綁定。

## 6. 工作包

### WP-001 — Delivery phase authorization

- 要求／impact：BR-001、FR-002、FR-003、FR-006、NFR-001、NFR-002、NFR-004；AC-002、AC-004、AC-006；IMP-001；MOD-001。
- Blocked by：None。
- 檔案範圍：Delivery facade、中央 stage authorization reference、validator、worktree tests與 compatibility runner。
- Intent／order：BDD-001／002／006 red → TEST-001／002 red → shared probe lookup → safe outcome mapping → parser/API → validator mutation closure。
- 完成：exact phase才 authorized；所有 reject paths零 mutation；既有四 command行為相容；focused/related green。

### WP-002 — Requirements routed entry

- 要求／impact：BR-001、FR-002、FR-003、FR-006、NFR-003；AC-002、AC-004；IMP-002；MOD-002。
- Blocked by：WP-001。
- 檔案範圍：Requirements SKILL／YAML／behavior contract／owner validator與 tests。
- Intent／order：BDD-003 red → TEST-003 red → first-gate pointer／phase contract → discoverability text → mutation coverage。
- 完成：無授权不產生 temp／formal Candidate；合法 active phase保留 frontier與原 quality Gate；focused/related green。

### WP-003 — Planning routed entry

- 要求／impact：BR-001、FR-002、FR-003、FR-006、FR-008、NFR-003；AC-002、AC-004、AC-007；IMP-003；MOD-003。
- Blocked by：WP-001。
- 檔案範圍：Planning SKILL／YAML／behavior contract／owner validator與 tests。
- Intent／order：BDD-004 red → TEST-004 red → first-gate pointer／phase contract → preserve plan-only read-only discriminator → mutation coverage。
- 完成：無授权不產生 Plan／Knowledge Candidate；合法 active phase保留 ready-plan owner Gate；focused/related green。

### WP-004 — Implementation routed entry

- 要求／impact：FR-002、FR-003、FR-006、TR-001、NFR-001、NFR-003；AC-003、AC-004、AC-009；IMP-004；MOD-004。
- Blocked by：WP-001。
- 檔案範圍：Implementation SKILL／YAML／orchestrated-delivery／behavior contract／owner validator與 tests。
- Intent／order：BDD-005 red → TEST-005 red → authorization-first preflight → remove standalone mutation contract → historical read-only disposition → mutation coverage。
- 完成：Ready plan alone零產品／ledger write；active phase仍完整執行 outside-in BDD／TDD與fresh review；既有 bytes不遷移；focused/related green。

### WP-005 — Unified routing and full evidence

- 要求／impact：FR-001、FR-004、FR-005、FR-007、FR-008、TR-001、NFR-002..004；AC-001、AC-005、AC-007..009；IMP-005；MOD-005。
- Blocked by：WP-002、WP-003、WP-004。
- 檔案範圍：Delivery SKILL／YAML／stage-routing／behavior contracts與 reports、cross-skill validator／tests；不擴張產品 runtime。
- Intent／order：BDD-007／008／009 red → TEST-006／007 red → unified descriptions／exceptions／flow assertions → forward evidence → full fresh suites與review。
- 完成：正常意圖只需一個入口；兩人工 Gate與Knowledge Gate不變；Plan核准後自動 Implementation；全部 owner、security、legacy、BUG、performance、governance命令通過且 fresh reviewer核准。

## 7. 風險、相容與回滾

| Risk | 影響 | Mitigation／回滾 |
|---|---|---|
| RISK-001 prompt-only enforcement | 直接點名仍可繞過 | machine-readable `authorize` + owner/integration validators；回滾只撤 child text不足，需整個 WP一起反向。 |
| RISK-002 authorize重複或昂貴 probe | 破壞 <2 秒 gate | locate／authorize共用 probe後 helper；performance class為release gate。 |
| RISK-003 primary repo誤獲 child權限 | 在錯 worktree寫入 | requested canonical worktree必須等於 latest generation worktree。 |
| RISK-004 ambiguity／drift error洩密 | 安全資訊外洩 | 沿用 redacted DeliveryError；只列validated Work IDs與固定 reason enum。 |
| RISK-005 implicit invocation關閉 | router無法reach child | 保留 true；用 phase authorization而非隱藏。 |
| RISK-006 standalone implementation中斷 | 舊 host-temp run不能原路續寫 | bytes可讀；mutation需新／續接 delivery；不遷移、不刪除。 |
| RISK-007 exception成為旁路 | governance或micro-edit修改產品 | 中央契約列出精確例外；scope擴張即 route Delivery；owner Gate維持。 |
| RISK-008跨 skill文字漂移 | 規則不一致 | 單一 authority reference + validators + mutation tests。 |

回滾單位是 WP：若 WP-001 API未達安全／效能，停止下游且不變更 child；若單一 child發生問題，只回滾其 WP並保持 authorization API dormant；WP-005只在前三個全綠後啟用統一 discoverability。不得以恢復 standalone writer作臨時繞過。

## 8. 追溯與 readiness

| Requirement／AC | TD／SEAM | BDD／TEST | WP／完成證據 |
|---|---|---|---|
| BR-001、FR-002、FR-003、FR-006、NFR-001；AC-002、004、006 | TD-001／SEAM-001、002 | BDD-001、002、006／TEST-001、002 | WP-001／JSON + zero-write snapshots |
| FR-002、FR-003、FR-006、NFR-003；AC-002、004 | TD-002／SEAM-003 | BDD-003／TEST-003 | WP-002／owner mutation green |
| FR-002、FR-003、FR-006、FR-008；AC-002、004、007 | TD-002／SEAM-004 | BDD-004／TEST-004 | WP-003／owner mutation green |
| FR-002、FR-003、FR-006、TR-001；AC-003、004、009 | TD-003／SEAM-005 | BDD-005／TEST-005 | WP-004／zero ledger/product diff + owner green |
| FR-001、FR-004、FR-005、FR-007、FR-008、NFR-002..004；AC-001、005、007..009 | TD-004／SEAM-006 | BDD-007..009／TEST-006、007 | WP-005／full suites + performance + fresh review |

| Artifact | Role | 權威內容 |
|---|---|---|
| `docs/work/work-20260903-unified-skill-entry-198002a2/plan/plan.md` | primary | 設計、BDD／TDD、WP DAG、風險與追溯 |
| `docs/work/work-20260903-unified-skill-entry-198002a2/plan/handoff.json` | handoff | exact hashes、sources、contracts、commands、DAG與impact map |

- 阻塞性缺口：無；所有 TP-001..004 已有選定方案與排除理由。
- Readiness：source hashes、baseline、BDD framework、BOOT disposition、BDD／TEST、commands、五個可審查 WP與完整 traceability 已固定。
- Gate：本 Candidate 未授權任何實作、commit、merge或部署；使用者核准後只把同一 payload標為 Ready並由 Delivery原子進入 `implementation/active`，不再詢問是否開始實作。
