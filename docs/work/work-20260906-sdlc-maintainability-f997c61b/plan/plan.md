# 技術規劃：SDLC 專案可維護性、診斷與量測改善

- 狀態與核准證據：見 `handoff.json.approval`
- Candidate revision：`candidate-1`
- 日期：2026-09-06
- 來源規格：`docs/work/work-20260906-sdlc-maintainability-f997c61b/requirements.md`
- 範圍：六個工作包改善 CI、導覽、Delivery 轉換、Schema 子集合、唯讀 Doctor 及量測
- Planning baseline：repo `0c5534020993ce0e527ffefdd0bbbdf8e3e26138d3933defe22de1ed5ea2530c`；HEAD `1532391a4ea056828e30893e749fe307118a1e24`；status SHA-256 `8bfa14c5cf9c0eb041907db0876a441c207384de658b0e45ca5e3eb09606e12b`
- Primary／handoff：`docs/work/work-20260906-sdlc-maintainability-f997c61b/plan/plan.md`／`docs/work/work-20260906-sdlc-maintainability-f997c61b/plan/handoff.json`

## 1. 成果、範圍與限制

此計畫以六個依序驗證的工作包交付 CI、導覽、狀態轉換、Schema、Doctor 與量測改善，並保持既有治理及持久化契約相容。

- 範圍內：CI path filters 與 quick job、README／OPERATIONS、Delivery 內部轉換邊界、共用 validator adapter、Schema keyword audit、唯讀 `doctor`、suite metrics、20 題搜尋品質 corpus，以及現有 event history 的流程摘要。
- 範圍外：備份／還原、跨機遷移、舊紀錄批次修復、人工 Gate 重設、搜尋引擎替換、第三方 production dependency、commit／merge／deploy。

| ID | Required／Observed 限制 | SRC-* |
|---|---|---|
| CON-001 | 所有產品 mutation 仍由 Delivery phase authorization 與既有 owner Gate 控制。 | SRC-REQ-001、SRC-DELIVERY-001 |
| CON-002 | 公開 Delivery CLI、error codes、event order、歷史 Ready trust root 與 record schema 相容。 | SRC-REQ-001、SRC-DELIVERY-001、SRC-CLI-001 |
| CON-003 | Python standard library only；測試沿用 unittest 與既有 BDD scenario registry。 | SRC-REQ-001、SRC-EVIDENCE-001 |
| CON-004 | Doctor 對 repository、registry 及外部狀態零寫入；expected diagnosis 不恢復或授權。 | SRC-REQ-001、SRC-CLI-001 |
| CON-005 | Metrics sidecar 不改現有 suite stdout／stderr contract；既有效能門檻不放寬。 | SRC-REQ-001、SRC-RUNNER-001 |
| CON-006 | Historical Ready、Outcome、receipt、Wiki 與舊 record bytes 不批次遷移。 | SRC-REQ-001、SRC-DELIVERY-001 |

## 2. 證據與變更影響

| SRC ID | Kind／location／revision | 事實 | Plan refs | 直接 WP refs |
|---|---|---|---|---|
| SRC-REQ-001 | spec／approved Requirements／revision 1 | Required：FR-001..006、NFR-001..004、TR-001 與 AC-001..012。 | CON-001..006、TD-001..006、BDD-026..031 | WP-001..006 |
| SRC-EVIDENCE-001 | supporting／`source-evidence.md`／candidate-1 | Observed：base full suite green、相關入口與缺失 seam、規劃時 Git identity。 | BDD-FWK-001、BOOT、CMD-* | WP-001..006 |
| SRC-CI-001 | project／`.github/workflows/knowledge-portability.yml`／base HEAD | Observed：目前 PR paths 未涵蓋所有 docs、root guides 與 `.gitattributes`，平台 job 直接執行完整矩陣。 | TD-001、MOD-001、BDD-026 | WP-001 |
| SRC-DELIVERY-001 | project／`_delivery_record.py`／base HEAD | Observed：轉換 entrypoint 自 2881 行開始，phase 驗證、binding 與 persistence 集中於同一函式。 | TD-002、MOD-003、SEAM-003、BDD-028、BDD-030 | WP-003、WP-005 |
| SRC-CLI-001 | project／`delivery_workspace.py`／base HEAD | Observed：公開 parser 提供 probe/start/locate/authorize/transition，尚無 doctor。 | TD-004、MOD-005、SEAM-005、BDD-030 | WP-005 |
| SRC-SCHEMA-001 | project／Planning validator／base HEAD | Observed：`validate_instance` 支援有限關鍵字，但未巡覽拒絕未知 validation keyword。 | TD-003、MOD-004、SEAM-004、BDD-029 | WP-004 |
| SRC-RUNNER-001 | project／`run_full_suite.py`／base HEAD | Observed：runner 順序收集 command output，只在結束時輸出功能報告，尚無 metrics sidecar。 | TD-005、MOD-006、SEAM-006、BDD-031 | WP-006 |
| SRC-QUERY-001 | project／`knowledge_query.py`／base HEAD | Observed：查詢最多傳回五筆並執行 source snapshot validation，適合作為 Top-5 corpus seam。 | TD-006、MOD-007、SEAM-007、BDD-031 | WP-006 |

### Current → target

Current：CI 只有 platform／compare；根目錄沒有專案導覽；Delivery 的公開 facade 已拆開 Git/runtime/authorization/record 模組，但 record 轉換仍是一個長函式；Schema 驗證器為未宣告範圍的內建子集合；locate／authorize 能 fail closed，卻沒有整合診斷；full-suite 功能報告完整但缺少逐命令耗時與 not-run 狀態；retrieval 測試有 golden fixture，沒有 repository 固定 20 題品質 corpus。

Target：CI 先 quick 後跨平台；README 與 OPERATIONS 指向單一 owner authority；TransitionRequest／TransitionContext 與 phase handlers 隱藏各階段邏輯；shared validator adapter 統一 owner loading；Schema audit 對未知 validation keyword fail closed；doctor 只讀重用 probe／record verification；metrics 使用獨立 versioned sidecar；固定 corpus 輸出 Top-5 與失效來源結果。

| 影響 ID | 能力／Module | New／Modified／Preserved | 來源要求 |
|---|---|---|---|
| IMP-001 | CI 與文件入口 | Modified workflow；New README／OPERATIONS；Preserved owner authority | FR-001、FR-002 |
| IMP-002 | Delivery transition core | New internal request/context/handlers；Modified orchestration；Preserved facade | FR-003、NFR-001、TR-001 |
| IMP-003 | Schema subset | New keyword audit與文件；Modified validator；Preserved existing accepted instances | FR-004 |
| IMP-004 | Delivery Doctor | New CLI subcommand、result contract與 tests；Preserved locate/authorize | FR-005、NFR-002 |
| IMP-005 | Metrics 與搜尋品質 | New metrics writer/corpus/evaluator；Modified optional runner args；Preserved functional report | FR-006、NFR-003、NFR-004 |

## 3. 設計與決策

| Context | Observed／Required | Proposed | SRC／TD |
|---|---|---|---|
| Runtime | Python 3.13 CI、standard library、unittest | 不新增依賴；新增 module／dataclass／JSON contract | SRC-REQ-001、SRC-EVIDENCE-001 |
| State | append-only delivery record、host-temp registry、lock-held transition | handler 只計算／驗證；共同 orchestration 仍唯一寫入 | TD-002 |
| Validation | owner validator 動態載入且 Schema subset 自行實作 | adapter 集中載入；schema-aware keyword walker | TD-002、TD-003 |
| Diagnostics | locate/authorize fail closed | doctor 將 expected failures 投影成 closed diagnostics，零 mutation | TD-004 |
| Metrics | 功能報告含 raw command outputs但無 duration | sidecar 只含 command ID/status/duration/summary | TD-005 |
| Retrieval | query top five並重驗來源 | 固定 corpus 直接呼叫 public query seam，量測命中與排除 | TD-006 |

### TD-001 — CI quick gate 與文件 contract

- 需求／證據：FR-001、FR-002、AC-001、AC-002、SRC-CI-001。
- 選定方案與理由：新增 `quick` job，依序跑 syntax/schema、五個 owner contract validators、Knowledge lint 與文件契約測試；platform jobs `needs: quick`。PR paths 改為 `.agents/skills/**`、`docs/**`、`.gitattributes`、README、OPERATIONS 與 workflow 本身。
- 真實替代方案／拒絕原因：直接在每個 platform job 重複 quick 檢查會增加耗時並讓早期錯誤延後；僅擴 path filter 無法快速回報文件與契約問題。
- 影響：新增文件 link/parser contract tests；完整 Windows/Linux job內容與 comparator保持。

### TD-002 — TransitionRequest、TransitionContext 與 phase handlers

- 需求／證據：FR-003、NFR-001、AC-003..005、SRC-DELIVERY-001。
- 選定方案與理由：在 private delivery layer 建立 frozen `TransitionRequest` 收納所有 transition 參數、`TransitionContext` 收納 record/probe/knowledge gate，並以 requirements、planning、implementation、knowledge handler 函式處理 phase-owned validation/bindings。`_transition_record_unlocked` 保留 public-compatible signature，立即建構 request/context、dispatch handler，再由共同尾段追加 event、validate record 及 atomic write。
- 真實替代方案／拒絕原因：重寫成通用狀態機 DSL 會擴張風險；只把長函式切成任意 helper 仍無清楚 owner boundary。
- 影響：不改 CLI、record shape、lock scope、probe reuse、error code與 event order；先加入 architecture characterization tests，再移動邏輯。

### TD-003 — Schema-aware keyword audit

- 需求／證據：FR-004、AC-006、SRC-SCHEMA-001。
- 選定方案與理由：宣告 `SUPPORTED_VALIDATION_KEYWORDS` 與 `IGNORED_ANNOTATION_KEYWORDS`；audit walker 只在 schema object 層檢查 key，對 `properties`、`$defs`、`patternProperties` 的子值繼續巡覽而不把 map keys 視為 schema keywords。未知 key 回傳 `schema-path: unsupported keyword`，且不包含 instance value。
- 真實替代方案／拒絕原因：引入 jsonschema 套件違反依賴限制；靜態 grep 無法辨別業務 property 名稱。
- 影響：五份現有 Schema 先通過 audit；新增正負與 property-name collision cases。

### TD-004 — 唯讀 doctor 投影

- 需求／證據：FR-005、NFR-002、AC-007..009、SRC-CLI-001、SRC-DELIVERY-001。
- 選定方案與理由：新增 `doctor_workspace(repo, root, work_id)`，重用 probe、record discovery、`load_record`、`validate_record` 及 ready-generation verification，但不呼叫 write/transition/recover/Git mutation。輸出 closed `delivery-doctor/v1`：`outcome`、nullable `work`、七個 ordered checks、diagnostics、next_actions、process_metrics。多 run 只列 work IDs。
- 診斷代碼：`NO_ACTIVE_RUN`、`AMBIGUOUS_RUNS`、`RECORD_MISSING`、`INVALID_RECORD`、`IDENTITY_MISMATCH`、`ARTIFACT_DRIFT`、`EVIDENCE_MISSING`、`RECOVERY_REQUIRED`、`ENVIRONMENT_UNAVAILABLE`；未對應的既有 DeliveryError 使用其安全 code。
- 退出碼：passed=0、invalid input=2、state/evidence blocked=3、environment unavailable=4。診斷不授權任何下一階段。
- 真實替代方案／拒絕原因：包裝 locate 並輸出 exception 不能區分每項 check，也會因單筆壞紀錄遮蔽其他候選；自動 reconstruct 會違反 continuity 與核准規則。

### TD-005 — 獨立 suite metrics

- 需求／證據：FR-006、NFR-004、AC-010、SRC-RUNNER-001。
- 選定方案與理由：`run_full_suite.py` 增加 optional `--metrics-output`；以 `perf_counter` 包住每個 subprocess，預先建立完整 command inventory，結束時原子寫入 `knowledge-suite-metrics/v1`。每項只含 command ID、`passed|failed|timeout|not_run`、nullable duration；summary 含 counts 與 total duration。
- 路徑規則：接受 caller 明示路徑；parent 必須存在，拒絕目錄或 symlink／junction target；同目錄 temporary file加 `os.replace`。功能 stdout/stderr bytes與提早停止順序不變。
- 真實替代方案／拒絕原因：把 duration 加入既有功能 JSON 會破壞相容與跨平台 hash；串流進度會改 stdout contract。

### TD-006 — 固定搜尋 corpus 與流程摘要

- 需求／證據：FR-006、AC-012、SRC-QUERY-001。
- 選定方案與理由：加入 closed `search-quality-cases/v1` JSON，至少 20 題覆蓋中文、英文、混用、exact ID 與 no-valid-source；evaluator 呼叫 `query_repository`，輸出 case-level expected/observed path、Top-5 hit及 invalid-source exclusion。Doctor 從 append-only events計算 phase return counts與可閉合 duration；缺 timestamp/end event為 null並列 `unavailable_fields`。
- 真實替代方案／拒絕原因：只用合成 golden fixture無法追蹤此 repository 的實際知識；以自然語言報告無法成為 CI oracle。
- 影響：corpus 更新需 code review；invalid-source exclusion 保持強制，Top-5 hit先記錄基準且不得低於現行 retrieval threshold。

| MOD ID | 責任 | Caller-facing contract | SEAM／Adapter | 隱藏內容 | 要求 |
|---|---|---|---|---|---|
| MOD-001 | CI/docs | README 可到達入口；workflow quick→platform→compare | SEAM-001 file/CI contract | link解析與 path pattern | FR-001、FR-002 |
| MOD-002 | Validator adapter | `load_owner_validator(owner)` 回傳既有 validator interface或安全 DeliveryError | SEAM-002 in-process adapter | importlib/module cache與錯誤遮蔽 | FR-003、NFR-001 |
| MOD-003 | Transition core | 現有 `transition_record(...)` 結果、例外與 atomicity不變 | SEAM-003 public CLI＋record snapshot | request/context與phase handlers | FR-003、NFR-001 |
| MOD-004 | Schema subset | `audit_schema_keywords(schema) -> list[str]`；`validate_instance`先 audit再驗值 | SEAM-004 validator API | schema-aware traversal | FR-004 |
| MOD-005 | Delivery Doctor | `doctor_workspace(...) -> delivery-doctor/v1`；CLI依 outcome回 0/2/3/4 | SEAM-005 CLI JSON/exit | candidate scan、safe error mapping、event metrics | FR-005、NFR-002 |
| MOD-006 | Suite metrics | optional sidecar，不改功能 report | SEAM-006 runner CLI/filesystem | timers、not-run inventory、atomic writer | FR-006、NFR-004 |
| MOD-007 | Search quality | corpus＋evaluator report | SEAM-007 query public API | expected-path comparison與 exclusion | FR-006 |

主要流程：`CLI transition → lock-held orchestration → TransitionRequest/Context → phase handler → shared semantic validation → append event → record validation → atomic write`。Doctor 只走 `CLI doctor → probe/discovery/stable reads → checks/diagnostics/process metrics → JSON`，不進入 transition 流程。

## 4. 測試策略

| BDD-FWK ID | Observed／Proposed framework、版本與一手來源 | Test-only／安裝邊界 | Feature／binding／fixture | Discovery／report／zero-skip／CI |
|---|---|---|---|---|
| BDD-FWK-001 | Observed：standard-library unittest scenario registry；base BDD 24/24 green | Test-only；無安裝 | `test_behavior.py`、isolated `.knowledge-test-tmp` fixtures | CMD-BDD-DISCOVERY-001、CMD-BDD-FOCUSED-001、CMD-BDD-FULL-001；failed=0、skipped=0 |

| SEAM ID | 可觀察 Interface | 替身策略 | 測試層 |
|---|---|---|---|
| SEAM-001 | workflow paths與 README/OPERATIONS links/commands | temporary repository tree | contract／BDD |
| SEAM-002 | owner validator loading | temporary modules與 missing module | unit／contract |
| SEAM-003 | public transition CLI與 record bytes | existing isolated Git delivery fixtures | characterization／integration |
| SEAM-004 | schema audit＋instance validation | in-memory schemas/instances | unit |
| SEAM-005 | doctor JSON、exit code與 before/after snapshots | isolated valid/corrupt/multiple registries | integration／BDD |
| SEAM-006 | full-suite stdout/stderr與 metrics file | fake subprocess outcomes／temporary output | unit／integration |
| SEAM-007 | query Top-5 quality report | repository corpus＋controlled invalid page fixture | BDD／regression |

`BOOT-*`：不適用。SRC-EVIDENCE-001 證明所有被修改的 public seams與 unittest/BDD runners皆可載入；本次只新增 additive doctor／metrics/search interfaces。

| BDD ID | 要求／scenario | SEAM／fixture | Oracle／正確 red | Feature／binding | Focused CMD | WP／order |
|---|---|---|---|---|---|---|
| BDD-026 | docs/.gitattributes/root guides變更觸發 quick及platform | SEAM-001／workflow copy | baseline缺完整 paths與quick gate，assertion red | `test_behavior.py` maintenance group | CMD-BDD-FOCUSED-001 | WP-001／1 |
| BDD-027 | README可導覽且唯讀／隔離操作範例可執行 | SEAM-001／docs fixture | baseline缺root guides，link與command assertion red | 同上 | CMD-BDD-FOCUSED-001 | WP-002／1 |
| BDD-028 | transition handler refactor保持合法／非法 matrix與record bytes | SEAM-002/003／existing delivery fixtures | baseline缺 request/context/handler boundary contract，architecture assertion red | 同上 | CMD-BDD-FOCUSED-001 | WP-003／1 |
| BDD-029 | 未知 keyword失敗、property map key不誤判 | SEAM-004／in-memory schemas | baseline忽略未知keyword，negative assertion red | 同上 | CMD-BDD-FOCUSED-001 | WP-004／1 |
| BDD-030 | doctor正常、多 run、壞 record、drift與 recovery-required均零寫入 | SEAM-005／isolated registries | baseline parser無doctor，contract assertion red | 同上 | CMD-BDD-FOCUSED-001 | WP-005／1 |
| BDD-031 | metrics涵蓋pass/fail/timeout/not-run；20+ corpus輸出Top-5與invalid exclusion；events輸出return/duration/null | SEAM-005/006/007／fake subprocess、repo corpus與event variants | baseline無metrics、corpus與process summary，assertion red | 同上 | CMD-BDD-FOCUSED-001 | WP-006／1 |

| TEST ID | BDD／風險 | 層級／SEAM／fixture | Oracle／red | Focused／related CMD |
|---|---|---|---|---|
| TEST-026 | BDD-026／CI漏觸發或門檻漂移 | contract／SEAM-001 | 精確 path/job assertions；baseline red | CMD-TDD-FOCUSED-001／CMD-RELATED-001 |
| TEST-027 | BDD-027／文件連結或操作範例漂移 | contract／SEAM-001 | link、parser與隔離副作用 assertions；baseline red | CMD-TDD-FOCUSED-001／CMD-RELATED-001 |
| TEST-028 | BDD-028／重構語意或atomicity漂移 | characterization＋integration／SEAM-002/003 | before/after matrix、errors/events/bytes相等；boundary缺失先red | CMD-TDD-FOCUSED-002／CMD-RELATED-001 |
| TEST-029 | BDD-029／silent schema acceptance | unit／SEAM-004 | supported positive/negative、unknown location、property collision | CMD-TDD-FOCUSED-003／CMD-RELATED-001 |
| TEST-030 | BDD-030／doctor寫入或誤續接 | integration／SEAM-005 | tree/registry/sentinel hash相等、closed codes與exit | CMD-TDD-FOCUSED-002／CMD-RELATED-001 |
| TEST-031 | BDD-031／metrics破壞stdout、搜尋退化或事件過度推定 | unit＋regression／SEAM-005/006/007 | functional bytes相等、完整inventory、20+ cases、Top-5、invalid排除、nullable duration | CMD-TDD-FOCUSED-004／CMD-RELATED-001 |

順序：每個 WP 先取得對應 BDD 正確 red，再取得映射 TEST red；完成 minimal green 與 refactor-with-green後，跑 focused BDD與related suite。WP-003 移動每個 phase block後重跑現有 65-case Delivery matrix。全部完成後 fresh 執行 full build、BDD、test、governance與 Windows local benchmark；Linux parity由 CI artifact提供。

## 5. 工作包

### WP-001 — 基準與 CI quick gate

- 要求／結果：FR-001、NFR-003、AC-001；workflow path coverage與 quick dependency。
- Blocked by：None。
- Modules／Seams：MOD-001／SEAM-001；workflow、文件 contract tests。
- Consumes／produces：現有 platform/compare → quick→platform→compare及完整 paths。
- Slice order：BDD-026→TEST-026（CI部分）。
- 完成證據：focused green、workflow YAML parse、quick commands local green。

### WP-002 — 根目錄導覽與操作手冊

- 要求／結果：FR-002、AC-002、AC-011；README、OPERATIONS、最小 governed delivery 範例。
- Blocked by：WP-001。
- Modules／Seams：MOD-001／SEAM-001。
- Consumes／produces：owner contracts → 單一導航與不重複規則的操作入口。
- Slice order：BDD-027→TEST-027。
- 完成證據：link、command、authority引用 tests green。

### WP-003 — Transition core 與 validator adapter

- 要求／結果：FR-003、NFR-001、TR-001、AC-003..005；具名 request/context與phase handlers。
- Blocked by：WP-002。
- Modules／Seams：MOD-002、MOD-003／SEAM-002、SEAM-003。
- Consumes／produces：現有 facade/private modules → 相同 public contract與分階段內部邊界。
- Slice order：BDD-028→TEST-028；依 requirements→planning→implementation→knowledge逐塊移動並重跑 matrix。
- 完成證據：focused、65-case Delivery、related green；record snapshots與 error/event order不變。

### WP-004 — Schema 子集合 audit

- 要求／結果：FR-004、AC-006；明列支援/annotation keyword與未知規則錯誤。
- Blocked by：WP-003。
- Modules／Seams：MOD-002、MOD-004／SEAM-002、SEAM-004。
- Consumes／produces：現有 validator → keyword audit＋既有 instance validation。
- Slice order：BDD-029→TEST-029。
- 完成證據：五份 Schema、mutation tests、property collision tests green。

### WP-005 — 唯讀 Delivery Doctor

- 要求／結果：FR-005、NFR-002、AC-007..009；`delivery-doctor/v1`與操作指引。
- Blocked by：WP-004。
- Modules／Seams：MOD-003、MOD-005／SEAM-003、SEAM-005。
- Consumes／produces：probe/discovery/record validators → closed diagnostics、next actions與process metrics。
- Slice order：BDD-030→TEST-030。
- 完成證據：正常及九類診斷、exit mapping、before/after snapshots green。

### WP-006 — Suite metrics 與搜尋品質

- 要求／結果：FR-006、NFR-003、NFR-004、AC-010、AC-012；sidecar、20+ corpus、quality evaluator。
- Blocked by：WP-005。
- Modules／Seams：MOD-005..007／SEAM-005..007。
- Consumes／produces：full suite/events/query API → versioned metrics與品質報告。
- Slice order：BDD-031→TEST-031，先runner metrics，再search corpus與event summary。
- 完成證據：focused/related/full green；功能report byte-compatible；本次實際 metrics與search report可讀。

## 6. 風險與追溯

| Risk ID | 觸發條件 | 影響 | Mitigation／驗證 | Owner |
|---|---|---|---|---|
| RISK-001 | 長函式拆分改變驗證或寫入順序 | 核准繞過或部分狀態 | characterization snapshots、逐phase移動、完整 Delivery matrix | WP-003 |
| RISK-002 | Doctor 共用 helper時意外呼叫 mutation | 診斷改變現場 | dependency guard、write primitive mocks、前後tree/hash | WP-005 |
| RISK-003 | keyword audit誤判 property名稱 | 合法 Schema 被拒 | schema-position walker與collision fixtures | WP-004 |
| RISK-004 | metrics寫入改變功能輸出或洩漏 raw output | consumer不相容／敏感資訊 | sidecar closed allowlist、byte equality與sentinel tests | WP-006 |
| RISK-005 | CI quick job與平台 job規則漂移 | false green或重複耗時 | quick只調用owner命令、platform needs quick、workflow contract test | WP-001 |
| RISK-006 | repository corpus因合法知識更新而脆弱 | 不必要阻擋 | expected source以canonical identity綁定；命中率觀察與invalid exclusion分開 | WP-006 |

| SRC／要求 | TD／MOD／SEAM | BDD | TEST | WP | CMD／證據 |
|---|---|---|---|---|---|
| FR-001、AC-001 | TD-001、MOD-001、SEAM-001 | BDD-026 | TEST-026 | WP-001 | focused／related／CI |
| FR-002、AC-002/011 | TD-001、MOD-001、SEAM-001 | BDD-027 | TEST-027 | WP-002 | focused／docs contract |
| FR-003、NFR-001、TR-001 | TD-002、MOD-002/003、SEAM-002/003 | BDD-028 | TEST-028 | WP-003 | delivery focused／full |
| FR-004、AC-006 | TD-003、MOD-004、SEAM-004 | BDD-029 | TEST-029 | WP-004 | schema focused／related |
| FR-005、NFR-002 | TD-004、MOD-005、SEAM-005 | BDD-030 | TEST-030 | WP-005 | doctor focused／full |
| FR-006、NFR-003/004 | TD-005/006、MOD-006/007、SEAM-006/007 | BDD-031 | TEST-031 | WP-006 | metrics/search focused／full |

## 7. Artifacts 與 readiness

| Path | Role | 權威內容 |
|---|---|---|
| `docs/work/work-20260906-sdlc-maintainability-f997c61b/plan/plan.md` | primary | 設計、interfaces、BDD/TDD、工作包、風險與追溯 |
| `docs/work/work-20260906-sdlc-maintainability-f997c61b/plan/source-evidence.md` | supporting | base identity、全量測試與 absence evidence |
| `docs/work/work-20260906-sdlc-maintainability-f997c61b/plan/handoff.json` | handoff | ready-plan/v1 machine contract、commands、DAG、hashes與approval |

- Requirements／規劃未知／衝突：無。
- BDD framework：既有 standard-library scenario registry，無安裝或 BOOT。
- Candidate payload、artifact hashes、source mappings、commands、DAG與impact由producer validator重算。
- Linux parity 必須由本次 CI artifact證明；本機 Windows full suite不能替代。
