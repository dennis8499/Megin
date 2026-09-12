# 技術規劃：BUG 結案處置規則 v2

- 狀態與核准證據：見 `handoff.json.approval`
- Candidate revision：candidate-1
- 日期：2026-09-12
- 來源規格：`docs/work/work-20260912-bug-closure-policy-dbcbce13/requirements.md`
- 範圍：建立可驗證、append-only、限時升級的 BUG status/disposition overlay，並為目前 16 項 assessment 建立證據不足的初始盤點
- Planning baseline：repo_id `c02a0b6fa293bdbf99be435da6898d63abd509d25d61bdc9b4409ea9b8210b99`、HEAD `9ca64837a9c519d324a5f36a28c3ab7eb6e479e8`、status hash `a57c92a1e2a15f8c36f175781802570721e8badfcafcb2a2a349c8073b3ae90f`
- Primary／handoff：`docs/work/work-20260912-bug-closure-policy-dbcbce13/plan/plan.md`／`docs/work/work-20260912-bug-closure-policy-dbcbce13/plan/handoff.json`

## 1. 成果、範圍與限制

本計畫將以 bug-closure-status/v1 的逐 BUG append-only record 與唯讀 report，將 verification result 與 current disposition 分離，並以 fixed-verified 的原始症狀、回歸、完整驗證與獨立 reviewer 門檻結案。

- 範圍內：新增 `bug-closure-status/v1` machine contract、只讀 owner validator／reporter、status chain 與 blocker／risk／reviewer gate；建立 16 項初始 status records 與一份可重算的 status review。
- 範圍外：不修復本次 16 個產品 BUG；不改寫既有 assessment、Outcome、Ready handoff、validation evidence、公開產品 CLI、既有 `bug-assessment/v1`／`bug-verification/v1`／`ready-plan/v1` 或 2 秒效能門檻；不自動建立 issue、通知、commit、push、merge、deploy。

| ID | Required／Observed 限制 | SRC-* |
|---|---|---|
| CON-001 | verification result 與 current disposition 必須為兩個獨立欄位；`partial` 或缺證據不得推導成 fixed-verified。 | SRC-001、SRC-002 |
| CON-002 | fixed-verified 必須有原始症狀 pre/post、regression red→green、完整驗證、適用平台與獨立 reviewer。 | SRC-001、SRC-003 |
| CON-003 | status record 以逐 BUG、逐 revision、previous hash 的 create-only chain 保存；共同 work scope 不得合併不同 BUG 結論。 | SRC-001、SRC-005 |
| CON-004 | Human Gate 維持 file-first、Summary-only Chat、exact identity；新規則不增加第三道核准 Gate。 | SRC-004、SRC-005 |
| CON-005 | 正式效能超標、失敗 raw output、recovery material 與 reviewer identity 不得被成功重跑覆蓋。 | SRC-001、SRC-006、SRC-007 |
| CON-006 | Windows／Linux 是 release evidence 的不同 obligation；單一平台只能形成平台限定或 partial evidence。 | SRC-001、SRC-009 |

## 2. 證據與變更影響

| SRC ID | Kind／location／revision | 事實 | Plan refs | 直接 WP refs |
|---|---|---|---|---|
| SRC-001 | spec／`docs/work/work-20260912-bug-closure-policy-dbcbce13/requirements.md`／accepted-requirements-20260912 | Required：BR、FR、NFR、AC 與 TP-001..005 定義 verification/disposition 分離、timebox、逐 BUG、歷史保留與跨平台門檻。 | CON-001..006、TD-001..003、BDD-001..003 | WP-001、WP-002、WP-003 |
| SRC-002 | contract／`.agents/skills/bug-diagnosis/references/assessment-contract.md`／base | Observed：assessment 是 diagnosis evidence，既有 verdict／relation／create-only revision 語義不可被 status overlay 改寫。 | CON-001、TD-001、BDD-001 | WP-001 |
| SRC-003 | contract／`.agents/skills/implementation-execution/references/reviewer-contract.md`／base | Required：fresh reviewer、原始症狀、regression、full verification、平台與 reviewer identity 需獨立證據。 | CON-002、TD-002、BDD-002 | WP-002 |
| SRC-004 | governance／`.agents/skills/project-knowledge/references/human-gate-review.md`／base | Required：完整 payload 先檔案化，Chat 只摘要與 direct links，approval 綁 exact identity。 | CON-004、TD-002、BDD-002 | WP-002 |
| SRC-005 | governance／`.agents/skills/delivery-orchestrator/references/workspace-and-run.md`／base | Observed/Required：Delivery record、phase Gate 與歷史 artifacts 為單一受治理交付入口。 | CON-003、CON-004、TD-002 | WP-002 |
| SRC-006 | project／`docs/bugs/bug-bdd016-warm-query-tail/assessment-1.json`／1 | Observed：現有效能 assessment 的正式樣本與 intermittent symptom 是初始 status evidence 的代表，不等於目前已修復。 | CON-005、TD-003、BDD-003 | WP-003 |
| SRC-007 | project／`docs/work/work-20260907-workflow-speed-d0b3946d/implementation/outcome.md`／base | Observed：驗證去重、review 前置檢查與 evidence 保存已有實作慣例，可被 status report 引用而不重複計量。 | CON-005、TD-003、BDD-003 | WP-003 |
| SRC-008 | project／`README.md`／base | Observed：repo 使用 Python standard library、Windows／POSIX shell、既有 owner checks 與 quick/full suite。 | BDD-FWK-001、CMD-* | WP-003 |
| SRC-009 | project／`.github/workflows/knowledge-portability.yml`／base | Observed：既有 release workflow 提供 Windows／Linux matrix 與 compare gate，可承接新 status validator 的跨平台 evidence。 | CON-006、CMD-CI-001 | WP-003 |

### Current → target

| 影響 ID | 能力／Module | New／Modified／Removed／Preserved | 來源要求 |
|---|---|---|---|
| IMP-001 | `bug-closure-status/v1` schema 與 owner validator | New：status record 的欄位、互斥 disposition、gate invariants；Preserved：既有 assessment／verification schema | CON-001、CON-002、CON-003 |
| IMP-002 | `bug_status.py` read-only validator／reporter | New：stable no-follow 讀取、revision chain、逐 BUG report 與 unresolved 統計；不提供未受治理的覆寫命令 | CON-003、CON-005 |
| IMP-003 | closure policy reference 與 BUG skill entry | Modified：新增 policy v2 導覽與 EVAL case；Preserved：diagnosis 不直接寫 repository | CON-001..006 |
| IMP-004 | 16 項 initial status records／status review | New：以 assessment hash 綁定、`verification_result: null`、`evidence-pending`；Preserved：歷史 assessment bytes | CON-003、CON-005 |

## 3. 設計與決策

| Context | Observed／Required | Proposed | SRC／TD |
|---|---|---|---|
| Record lifecycle | assessment／verification 各有既有 revision／result；status 尚無統一 schema。 | 每 BUG 使用 `docs/bugs/<bug-id>/status-N.json`，`previous.path`／`previous.sha256` 串接；status files 只 create-only，新結論新增 revision。 | SRC-001、SRC-002／TD-001 |
| Product vs evidence | `bug-verification/v1` 的 `verified|partial|failed` 是驗證結果，不是風險決策。 | status 同時保存 `verification.result`（可為 null）與 `current_disposition`；`partial` 只能對應 `evidence-pending` 或其他明確 blocker，不能對應 fixed-verified。 | SRC-001、SRC-003／TD-001 |
| Gate and reviewer | Human Gate／fresh review 已有精確 identity 與 evidence contract。 | fixed-verified／accepted-risk 只接受 `reviewer.identity != implementation_owner.identity`，並綁 report ref、scope、version、result；不另增 Chat Gate。 | SRC-003、SRC-004、SRC-005／TD-002 |
| Platform and performance | existing release matrix 與效能 evidence 保存可引用。 | `required_platforms` 與每平台 evidence 明列；超標 sample 以 hash manifest 保留，report 只聚合不刪除 raw evidence。 | SRC-006、SRC-007、SRC-009／TD-003 |

### TD-001 — 逐 BUG append-only status model

- 需求／證據：BR-001、FR-001、FR-002、FR-003、FR-007、FR-008、FR-011、TR-001、NFR-001、NFR-002、NFR-007；SRC-001、SRC-002。
- 選定方案與理由：以每 BUG 的 `status-N.json` child record 加 `work_scope.bug_ids` 表達共同工作範圍；每個 revision 對 assessment、verification、evidence manifest、owner、next action、due date 與 transition 作 immutable binding。這同時保留逐項隔離與不改寫歷史的能力，且 report 可重算 current state。
- 真實替代方案／拒絕原因：單一 batch JSON 會把一項 BUG 的 pass 混入另一項缺口，且單一 revision 難以對應各 BUG 的 history；直接把 disposition 加進 assessment 會破壞 `bug-assessment/v1` diagnosis 語義與 create-only bytes。
- Interface、資料、相容性、測試與營運影響：validator 讀取既有 assessment／verification 並檢查 hash；既有檔案不改；缺 status record 時 report 明確顯示 evidence unavailable，不默認 fixed。

| MOD ID | 責任 | Caller-facing contract | SEAM／Adapter | 隱藏內容 | 要求 |
|---|---|---|---|---|---|
| MOD-001 | Closure status validator | 輸入 status raw bytes、record path、repository；輸出 deterministic errors 或 valid record；拒絕 duplicate key、redirect、hash drift、缺欄位與非法組合。 | `SEAM-001`：`validate_status_record`；既有 assessment validator adapter | schema traversal、stable no-follow read、cross-field rules | BR-001、FR-001..007、NFR-001、NFR-007 |
| MOD-002 | Status chain/report | 輸入 repository 與 optional work scope；輸出每 BUG 最新合法 revision、counts、unresolved list、blocker／next action；不寫檔。 | `SEAM-002`：`validate_repository`／`render_report` | chain ordering、scope isolation、count classification | FR-007、FR-008、FR-011、NFR-002、NFR-004 |
| MOD-003 | Closure policy owner docs | 提供 policy v2 的狀態、轉換、欄位與責任規則；不改既有 contracts。 | `SEAM-003`：BUG skill reference／owner quick validation | wording guard、固定狀態表、Gate references | BG-001..005、NFR-006、NFR-007 |

### TD-002 — fixed、blocker、risk 與 reviewer gates

- fixed-verified 的必要條件是：`verification.result == verified`；原始症狀 pre 為 present、post 為 absent；regression red 與 green 均有不同 evidence；所有 required full verification 與 required platform results 為 passed；reviewer approved 且 reviewer identity 不同於 implementation owner；blocker 與 risk decision 為 null。
- `evidence-pending` 只表示目前 evidence 不足或不確定；`environment-blocked`／`contract-blocked` 必須帶 blocker class、missing capability／gap、owner、due date、alternative、escalation role 與 release-blocked。這些狀態不推導產品修復結論。
- `accepted-risk`／`deferred` 必須帶 risk decision、理由、緩解、影響範圍、expires_on、reopen condition、next review；Critical／High 需要不同角色的 Product/Risk 與 Engineering/Delivery 核准。`rejected` 需要明確 decision 與 approver。
- `confirmed-open` 需要目前版本重現、command、oracle、raw evidence 與下一步；沒有目前版本症狀或 post-fix evidence 時初始 16 項統一採 `evidence-pending`。

### TD-003 — report、timebox 與 cross-platform evidence

- `timebox` 保存 T0、T0+1 classify owner/next action、T0+3 blocker classification、T0+5 escalation 與 T0+10 decision dates；validator 檢查日期順序與每一狀態必有 owner／due date。
- report 的 `unresolved_count` 包含 `confirmed-open`、`evidence-pending`、`environment-blocked`、`contract-blocked`、`accepted-risk` 與 `deferred`；`fixed-verified` 與 `rejected` 才是 terminal dispositions。報告另分列 `verification_result`、platform、blocker 與 due date。
- 效能 evidence manifest 僅保存 ref/hash 與 report metadata；正式超標樣本永遠留在既有 validation evidence，後續通過重跑只能新增 evidence，不可清除或取代前一樣本。

## 4. 測試策略

### Framework、seams 與 bootstrap

`BDD-FWK-001` 使用目前已觀察的 Python standard-library `unittest`；不安裝第三方 dependency。`BOOT-*` 不適用：第一個實際 entrypoint 是新 read-only validator，先以 test fixture 建立可 import 的 pure contract seam；不建立 production sentinel、不寫 repository。所有新 tests 使用 isolated `tempfile` fixture，測試結束驗證 fixture cleanup。

| SEAM ID | 可觀察 Interface | 替身策略 | 測試層 |
|---|---|---|---|
| SEAM-001 | `validate_status_record(repo, record_path)` 的 errors／valid result | temp repository、真實 assessment pair、tampered bytes、redirect path | contract／unit |
| SEAM-002 | `validate_repository`／`render_report` 的 sorted status與counts | 多 BUG、revision chain、scope fixture、性能 evidence manifest | integration／BDD |
| SEAM-003 | policy reference、owner validator、既有 Gate adapter | copied skill bundle、schema mutation、同 reviewer／缺 fields matrix | owner／contract |

| BDD ID | 要求／scenario | SEAM／fixture | Oracle／正確 red | Feature／binding | Focused CMD | WP／order |
|---|---|---|---|---|---|---|
| BDD-001 | 缺原始症狀 post、regression、full、reviewer 或平台 evidence 時不得 fixed-verified；partial 只能進 evidence-pending。 | SEAM-001／status fixture | validator assertion：fixed gate error，current disposition 不可為 fixed-verified | AC-001、AC-003；`bug-closure-status/v1` | CMD-BDD-FOCUSED-001 | WP-001／1 |
| BDD-002 | environment／contract blocker、accepted-risk、deferred 與 reviewer identity reuse 均依欄位與角色 fail closed；合法資料通過。 | SEAM-001/003／role/timebox fixture | missing owner/due/escalation/dual approval/same reviewer assertion red | AC-004..006、AC-008 | CMD-BDD-FOCUSED-002 | WP-002／1 |
| BDD-003 | 多 BUG status chain 逐項隔離；16 項 initial report 顯示 evidence-pending/unresolved；performance outlier 保留且成功重跑不覆蓋。 | SEAM-002／16-record fixture | sorted report count、previous hash、scope membership、raw hash preservation | AC-007、AC-009、AC-010 | CMD-BDD-FOCUSED-003 | WP-003／1 |

| TEST ID | BDD／風險 | 層級／SEAM／fixture | Oracle／red | Focused／related CMD |
|---|---|---|---|---|
| TEST-001 | BDD-001／結案條件被弱化或 verification/disposition 混欄 | unit／SEAM-001／minimal records | enum、null verification、closure evidence、platform/reviewer gate；先取得 fixed false-positive red | CMD-TDD-FOCUSED-001、CMD-RELATED-001 |
| TEST-002 | BDD-002／阻塞永久化、High risk 單人自核、same reviewer | contract／SEAM-001/003／role/timebox matrix | blocker fields、date order、distinct approver/reviewer、canonical wording | CMD-TDD-FOCUSED-002、CMD-RELATED-001 |
| TEST-003 | BDD-003／revision gap、scope contamination、outlier overwrite | integration／SEAM-002／temp repo + 16 synthetic/current records | chain hash、per-BUG result、counts、raw sample hash stable、cleanup | CMD-TDD-FOCUSED-003、CMD-RELATED-001 |

| CMD ID | Purpose | Observed／Proposed | 摘要；完整 contract 在 handoff.json |
|---|---|---|---|
| CMD-BDD-DISCOVERY-001 | bdd-discovery | Proposed | 列出 `test_closure_status.py` 完整 scenario inventory。 |
| CMD-BDD-FOCUSED-001..003 | bdd-focused | Proposed | 依 WP-001..003 執行單一 BDD slice；failed／skipped／not_run 均保留。 |
| CMD-TDD-FOCUSED-001..003 | tdd-focused | Proposed | 執行對應 inner contract tests；每個 BDD 先 red，再 minimal green。 |
| CMD-BDD-FULL-001 | bdd-full | Proposed | 執行完整 closure status BDD／contract test file。 |
| CMD-RELATED-001 | related | Proposed | `bug_status.py report --repo .` 並檢查目前 16 項 status review。 |
| CMD-BUILD-FULL-001 | build-full | Observed | 既有 project-knowledge syntax／schema scan。 |
| CMD-TEST-FULL-001 | test-full | Observed | 既有 `run_quick_checks.py` 全 owner／documentation／knowledge lint gate。 |
| CMD-GOVERNANCE-001 | governance | Observed | 既有 `knowledge_cli.py lint --repo .`，確認 policy page／provenance 不漂移。 |
| CMD-CI-001 | ci | Proposed | 在既有 Windows／Linux portability workflow 執行 closure tests並比較結果。 |

`validation-plan/v1` 的 local target 是本次 Windows 11／Python 3.14.5／Git 2.51.0／ripgrep 15.2.0；release requirements 維持 Windows／Linux hosted matrix。required obligations 與 command refs 在 `handoff.json` 完整列出。所有 Proposed 新入口都附 planning-baseline absence evidence；command 不直接寫 tracked product，status records／report 只在 implementation 的受治理 artifact 寫入步驟產生。Final review 只能引用本 Work ID 的 implementation Outcome、Knowledge postimages 與 terminal evidence；既有失敗／超標 raw output 是 executable input，不列為可任意 reuse。

執行順序：BDD-001 → TEST-001 → minimal green/refactor → focused；再 BDD-002 → TEST-002；再 BDD-003 → TEST-003；最後 fresh full build、test、BDD、governance、report 與 Windows／Linux CI evidence。任一 blocker 保留原始 evidence 並依 policy timebox 升級，不以重跑成功刪除失敗樣本。

## 5. 工作包

完整 DAG、files、consumed／produced contracts 與完成證據見 `work-packages.md`；順序為 `WP-001 → WP-002 → WP-003`。

### WP-001 — Status contract 與安全 validator

- 要求／結果／impact：BR-001、FR-001..003、FR-007、FR-008、NFR-001、NFR-007、AC-001..003、AC-009。
- Blocked by：None。
- 產出：`closure-status.schema.json`、`bug_status.py` 的 strict parse／assessment binding／fixed gate 與 contract tests；不提供覆寫歷史的 command。
- 完成證據：BDD-001／TEST-001 red→green、schema mutation、duplicate key、redirect、hash drift、partial overclaim 與 fixed false-positive 全通過。

### WP-002 — Blocker、risk、reviewer 與 timebox

- 要求／結果／impact：FR-004..006、FR-010、FR-011、NFR-002、NFR-004、NFR-006、AC-004..006、AC-008。
- Blocked by：WP-001。
- 產出：blocker／risk／reviewer／platform／transition invariants、policy reference、owner contract tests；沿用 Human Gate 與 Delivery ledger，不新增 Gate。
- 完成證據：BDD-002／TEST-002、High/Critical dual approval、same reviewer rejection、日期／升級與跨平台欄位測試通過。

### WP-003 — 多 BUG report 與 16 項 initial status review

- 要求／結果／impact：FR-007..009、FR-011、TR-001、NFR-002、NFR-003、NFR-005、AC-007、AC-009、AC-010。
- Blocked by：WP-002。
- 產出：revision chain/report renderer、16 個每 BUG `status-1.json`（`evidence-pending`、`verification_result: null`）與 `docs/bugs/status-reviews/work-20260912-bug-closure-policy-dbcbce13.json/.md`；引用全部 assessment hashes，歷史 bytes 不變。
- 完成證據：BDD-003／TEST-003、current count／severity matrix、sample hash preservation、scope isolation、fixture cleanup、local quick gate 與 Windows／Linux report。

## 6. 風險與追溯

### 風險與取捨

| Risk ID | 觸發條件 | 影響 | Mitigation／驗證 | Owner／決策點 |
|---|---|---|---|---|
| RISK-001 | status record 缺欄位或把 partial 推成 fixed | 產生不可信結案 | schema additionalProperties false、fixed gate negative matrix、canonical wording guard | WP-001／Delivery-Governance |
| RISK-002 | previous chain gap／hash drift／同一 work scope 混用 BUG | 歷史不可追溯或 pass 覆蓋缺口 | stable no-follow read、contiguous revision、每 BUG report row 與 scope isolation | WP-001、WP-003 |
| RISK-003 | High/Critical accepted-risk 單一 owner 自核或 reviewer reuse | 風險接受與審查失去獨立性 | role-aware dual approval、identity inequality、fresh reviewer contract | WP-002／Product-Risk + Delivery |
| RISK-004 | Windows／Linux 能力不可得 | status 被錯誤標成產品結論 | environment-blocked 欄位、release matrix、單平台只能 partial | WP-002、WP-003／Platform |
| RISK-005 | 成功重跑取代超標 sample | 效能稽核失真 | evidence manifest hash regression、immutable raw fixture、report aggregation only | WP-003／Performance |
| RISK-006 | 新 status writer 越過 Delivery／Human Gate | 歷史或外部狀態被未授權修改 | `bug_status.py` 只讀；status/report 僅列為 implementation artifact；既有 Gate refs 與 final reviewer | WP-001..003／Delivery-Governance |

| SRC／要求 | TD／MOD／SEAM | BDD | TEST | WP | CMD／證據 |
|---|---|---|---|---|---|
| BR-001、FR-001..003、FR-007、NFR-001、NFR-007 | TD-001、MOD-001、SEAM-001 | BDD-001 | TEST-001 | WP-001 | CMD-BDD/TEST-FOCUSED-001、CMD-BDD-FULL-001 |
| FR-004..006、FR-010、NFR-004、NFR-006 | TD-002、MOD-003、SEAM-003 | BDD-002 | TEST-002 | WP-002 | CMD-BDD/TEST-FOCUSED-002、CMD-GOVERNANCE-001 |
| FR-007..009、TR-001、NFR-002/003/005 | TD-003、MOD-002、SEAM-002 | BDD-003 | TEST-003 | WP-003 | CMD-BDD/TEST-FOCUSED-003、CMD-RELATED-001、CMD-CI-001 |

## 7. Artifacts 與 readiness

| Path | Role | 建立理由 | 權威內容 |
|---|---|---|---|
| `docs/work/work-20260912-bug-closure-policy-dbcbce13/plan/plan.md` | primary | 主線設計、追溯與 Gate 邊界 | WHAT→HOW、TD、BDD、WP、風險 |
| `docs/work/work-20260912-bug-closure-policy-dbcbce13/plan/test-strategy.md` | supporting | 測試矩陣與 fixture／platform evidence 細節會妨礙 primary 主線 | BDD／TEST／CMD 詳細契約與 red→green 順序 |
| `docs/work/work-20260912-bug-closure-policy-dbcbce13/plan/work-packages.md` | supporting | 每個垂直 slice 的檔案範圍、DAG 與完成證據獨立維護 | WP DAG、consumed／produced、impact map |
| `docs/work/work-20260912-bug-closure-policy-dbcbce13/plan/handoff.json` | handoff | versioned consumer 交接 | ready-plan/v1、sources、commands、validation、hashes |

- 缺口／未知／衝突：無；實作細節以 handoff 的 Proposed command 與 test contract 限定。
- BDD framework／BOOT／BDD／TDD／WP／commands：完整，全部新增 command 的 absence evidence 已綁 baseline source。
- `handoff.json` schema、cross-references、validation-plan、DAG 與 revision impact：由 technical-planning owner validator 與 project-knowledge planning builder 驗證。
- Policy v2 knowledge page：由 planning Knowledge Candidate 以 `planned` evidence class、同一 review bundle 與 promotion receipt 產生；不新增第三道核准 Gate。
- implementation 只有在本 Candidate 經使用者核准、Planning artifact apply、Ready handoff 與 implementation authorization 後才可開始；本回合不寫產品或 status records。
