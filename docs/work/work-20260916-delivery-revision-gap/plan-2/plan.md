# 技術規劃：跨世代 Delivery 修訂版配置修復

- 狀態與核准證據：見 `handoff.json.approval`
- Candidate revision：candidate-2
- 日期：2026-09-17
- 來源規格：`docs/work/work-20260916-delivery-revision-gap/requirements-2.md`
- 範圍：修正 repository-local Delivery v1 在新 generation 配置 Requirements／Plan 下一個 revision 的判定，並以隔離 transition tests 證明跨世代、collision、原子性與首版相容。
LOCAL-ONLY-GATE: 本 Work 以本地 target environment 的完整驗證作為完成門檻；hosted CI 與其他平台檢查僅是可選發布後 follow-up。
- Planning baseline：repo_id `c02a0b6fa293bdbf99be435da6898d63abd509d25d61bdc9b4409ea9b8210b99`、HEAD `026a491ead8efe81797095e485cc3138824e6ec2`、status hash `deb2e253d83a308089853b8ad9981e13076d443a1f1d76b618cf4a834e7f6ed3`
- Primary／handoff：`docs/work/work-20260916-delivery-revision-gap/plan-2/plan.md`／`docs/work/work-20260916-delivery-revision-gap/plan-2/handoff.json`

## 1. 成果、範圍與限制

Delivery 將以 run record 已記錄的最高 Ready revision 作為遞增下界。候選 revision 必須嚴格大於該下界；只有下界之後的缺席且未占用路徑會阻擋跳號，較早 generation 未 materialize 的歷史路徑不再干擾有效候選。

- 範圍內：`_assert_smallest_available_revision` 的 Requirements／Plan 共用判定、跨 generation fixture、正常遞增與跳號拒絕測試、已占用中間路徑保留測試、舊版／重用／首版相容回歸。
- 範圍外：portable v2、既有 record 或 approval 改寫、歷史 artifact 補寫、migration、branch/worktree cleanup、push、PR、merge、deploy，以及被阻擋 feature 的 rebase／新 plan 核准。

| ID | Required／Observed 限制 | SRC-* |
|---|---|---|
| CON-001 | revision history 以 Delivery record 的已記錄 Ready path 為權威；新候選須嚴格高於最高值。 | SRC-001、SRC-002、SRC-003 |
| CON-002 | 高於最高值的未占用缺席中間 path 仍拒絕；已占用 path 不覆寫。 | SRC-001、SRC-003、SRC-004 |
| CON-003 | transition 驗證失敗維持 append-only 原子性，保留既有 approval、Knowledge、BUG 與錯誤類別。 | SRC-001、SRC-002、SRC-005 |
| CON-004 | v1 首版命名、既有 phase gate 與本地 Windows 完成邊界維持不變；Windows／Linux hosted evidence 屬可選發布後檢查。 | SRC-001、SRC-005、SRC-006 |

## 2. 證據與變更影響

| SRC ID | Kind／location／revision | 事實 | Plan refs | 直接 WP refs |
|---|---|---|---|---|
| SRC-001 | spec／`docs/work/work-20260916-delivery-revision-gap/requirements-2.md`／requirements-candidate-3 | Required：FR-001..005、NFR-001、TR-001 與 AC-001..007 定義 high-water、collision、原子性、首版相容及同一 Requirements Gate。 | CON-001..004、TD-001、BDD-001、BDD-002、TEST-001、TEST-002 | WP-001 |
| SRC-002 | bug／`docs/bugs/bug-delivery-plan-revision-gap/assessment-2.json`／1 | Observed：plan-2 後 generation-2 缺席較舊 `plan/`，有效 plan-3 transition 回傳 `INVALID_REVISION`；root cause 已確認。 | CON-001、CON-003、TD-001、BDD-001、TEST-001 | WP-001 |
| SRC-003 | project／`.agents/skills/delivery-orchestrator/scripts/_delivery_record.py`／026a491ead8efe81797095e485cc3138824e6ec2 | Observed：Requirements／Plan 都呼叫同一 `_assert_smallest_available_revision`，目前從 revision 1 掃描未記錄 path。 | CON-001、CON-002、TD-001、BDD-001、BDD-002、TEST-001、TEST-002 | WP-001 |
| SRC-004 | project／`.agents/skills/delivery-orchestrator/scripts/test_delivery_transitions.py`／026a491ead8efe81797095e485cc3138824e6ec2 | Observed：Delivery transition tests 使用 isolated temporary Git repositories、`unittest` fixture 與 `workspace.transition_record`；既有 cases 覆蓋 phase、approval、collision 與 atomic failure。 | CON-002、CON-003、TD-002、BDD-001、BDD-002、TEST-001、TEST-002 | WP-001 |
| SRC-005 | governance／`.agents/skills/delivery-orchestrator/references/workspace-and-run.md`／026a491ead8efe81797095e485cc3138824e6ec2 | Required：v1 revisions、phase transition、append-only history、BUG binding、Knowledge gate 與 no implicit migration 必須維持。 | CON-003、CON-004、TD-001、TD-002、BDD-001、BDD-002、TEST-001、TEST-002 | WP-001 |
| SRC-006 | project／`.github/workflows/knowledge-portability.yml`／026a491ead8efe81797095e485cc3138824e6ec2 | Observed：既有 portability workflow 以 Python 3.13、Linux／Windows matrix 執行 quick、plugin 與 full suite；跨平台證據屬 release obligation。 | CON-004、BDD-002、TEST-002 | WP-001 |

### Current → target

| 影響 ID | 能力／Module | New／Modified／Removed／Preserved | 來源要求 |
|---|---|---|---|
| IMP-001 | Delivery revision allocator | Modified：先計算 record high-water，再只檢查 high-water 之後至 candidate 前的 revision；保留既有 occupied／symlink 判定與 `INVALID_REVISION`。 | CON-001、CON-002、FR-001、FR-003、FR-004 |
| IMP-002 | Requirements／Plan transition callers | Preserved：兩個 caller 仍執行相同 helper、existing approved path 仍先拒絕、record append 與 current ref 綁定不變。 | CON-003、CON-004、TR-001 |
| IMP-003 | Delivery transition regression fixture | New：建立已核准 revision 2、重建 generation 2、移除較早未登錄 path 的 fixture，並驗證 acceptance／failure／preservation。 | AC-001..AC-006 |
| IMP-004 | Knowledge／BUG trace | Preserved：本 Work 的 Requirements、assessment JSON／Markdown、promotion receipt 與同一 approval evidence 已在 Requirements Gate 綁定；本 Plan 只新增 planned claim。 | AC-007、FR-005 |

## 3. 設計與決策

| Context | Observed／Required | Proposed | SRC／TD |
|---|---|---|---|
| Revision source of truth | Delivery record 依序保存 Ready revisions；generation 只 materialize current approved upstream。 | 從 `recorded_paths` 解析同 kind 的最高 revision 作 high-water；沒有 history 時 high-water 為 0。 | SRC-001、SRC-002、SRC-003／TD-001 |
| Gap and collision | 目前 helper 從 1 掃描，會把 lower historical absence 當成 gap；occupied plan directory／requirements path 不能被覆寫。 | 只掃描 `range(high_water + 1, revision)`；每個缺席未占用 path 仍回既有 `INVALID_REVISION`，occupied path 直接略過。 | SRC-001、SRC-003／TD-001 |
| Transition safety | Delivery transition 在 handlers 完成後才 append；failure 不應增加 event 或改 current ref。 | 先拒絕 `revision <= high_water`，所有 gap／collision checks 在 append 前完成；不調整其他 handlers。 | SRC-001、SRC-004、SRC-005／TD-002 |
| Verification boundary | 現有 repo 使用 standard-library `unittest`；portability workflow 僅作可選發布後檢查。 | 以同一 isolated fixture 走真實 `workspace.transition_record`；focused cases 先 red，再 minimal green；related／full／local commands 保留完整 inventory。 | SRC-004、SRC-006／TD-002 |

### TD-001 — 以 Delivery record high-water 配置 revision

- 需求／證據：FR-001、FR-002、FR-003、FR-004、AC-001..AC-005；SRC-001、SRC-002、SRC-003。
- 選定方案與理由：在既有 helper 內解析 `recorded_paths` 的同 kind revision，取最大值作遞增下界；候選不大於下界即以 `INVALID_REVISION` fail closed，候選前只檢查下界後的缺席 path。這讓 generation materialization 的缺席歷史不會阻擋新 revision，同時保留跳號與不覆寫防護。
- 真實替代方案／拒絕原因：補回 generation 缺席的舊 artifact 會改變既有 materialization、增加寫入與 migration 風險；完全移除 gap check 會允許跳過尚未占用的高於 high-water path，破壞最小可用 revision 規則。
- Interface、資料、相容性、測試與營運影響：helper signature 不變；只讀 record 與 worktree path，錯誤仍為 `DeliveryError(code="INVALID_REVISION")`；首版 path 與既有 approved-path reuse guard 不變。

| MOD ID | 責任 | Caller-facing contract | SEAM／Adapter | 隱藏內容 | 要求 |
|---|---|---|---|---|---|
| MOD-001 | Revision allocator | 輸入 Delivery record、kind、candidate path／revision 與 recorded paths；有效下一版正常返回；倒退、重用或高於 high-water 的缺席跳號回 `INVALID_REVISION`。 | SEAM-001：`_assert_smallest_available_revision`；無 Adapter | revision parser、high-water、occupied path 判定 | FR-001..004、AC-001..006 |
| MOD-002 | Transition coordinator | Requirements／Plan caller 維持原有 schema、BUG、Knowledge、approval、append-only transaction。 | SEAM-002：`workspace.transition_record` | handlers ordering、record append、current ref | NFR-001、TR-001、AC-007 |
| MOD-003 | Regression fixture | 以 isolated Git/worktree 生成跨世代與 occupied/missing path 狀態，輸出可判定 record／bytes／error evidence。 | SEAM-003：`DeliveryFixture`／`unittest` | generation materialization、digest snapshots、cleanup | AC-001..006、NFR-001 |

## 4. 測試策略

### BUG diagnosis 與 verification target

- Assessment JSON：`docs/bugs/bug-delivery-plan-revision-gap/assessment-2.json`，SHA-256 `3d53b636309f0b4283ae92f6f292fec5d90449d98dd79b134f5511de0eb5080e`；Markdown：`docs/bugs/bug-delivery-plan-revision-gap/assessment-2.md`，SHA-256 `bba69d63908f71a3b84e55dde5fe8116f95bf030afa0a71b5010c327cd8d9af7`。
- Verdict／severity／relation／disposition：`confirmed`／`medium`／`intake`／`delivery`。
- Reproduction／root cause：`reproduced`／`confirmed`，confidence `high`；原始症狀是 generation-2 的有效 plan-3 被錯誤拒絕。
- 單一最小 causal fix：只改 `_assert_smallest_available_revision` 的 high-water 起點與倒退 guard；不另加猜測 patch。
- `CMD-BUG-REPRO-001` 先以同一跨世代 fixture 重現原本的 `INVALID_REVISION` red，修正後重跑 plan-3／requirements-3 應通過；regression BDD／TEST refs 為 `BDD-001`／`TEST-001`。
- Verification target：`verified`；original symptom 已 reproduced，無 partial safeguards。

`BDD-FWK-001`：沿用已觀察的 Python standard-library `unittest`，不安裝第三方 framework。`BOOT-*` 不適用：`_assert_smallest_available_revision` 與 `workspace.transition_record` 已存在，新增的是既有 seam 的局部判定與 fixture cases。

| SEAM ID | 可觀察 Interface | 替身策略 | 測試層 |
|---|---|---|---|
| SEAM-001 | `_assert_smallest_available_revision(record, kind, candidate_path, revision, recorded_paths)` 的成功／`DeliveryError` | 真實 temporary worktree path 與 record revision history | unit／contract |
| SEAM-002 | `workspace.transition_record` 的 phase、current ref、event count 與 error code | 真實 `DeliveryFixture`、requirements／plan Ready handoff | integration／BDD |
| SEAM-003 | generation-2 materialization 與 occupied path bytes | isolated Git repository、`workspace.start_workspace(generation=2)`、byte snapshots | integration |

| BDD ID | 要求／scenario | SEAM／fixture | Oracle／正確 red | Feature／binding | Focused CMD | WP／order |
|---|---|---|---|---|---|---|
| BDD-001 | 已記錄 revision 2 後，新 generation 缺席較早 path 時，plan-3 與 requirements-3 都被接受並成為 current；修改前對應 transition 取得 `INVALID_REVISION` red。 | SEAM-002/003／跨世代 fixture | `phase`／current ref／record revision 為 3，且 pre-fix 的 plan-3 error 不可被誤判為 runner failure。 | AC-001、AC-002、FR-001、FR-002 | CMD-BDD-FOCUSED-001 | WP-001／1 |
| BDD-002 | plan-4 跳過高於 high-water 的缺席 plan-3 仍拒絕；已占用 plan-3 可接受且 bytes 不變；舊版／重用／首版與 failure atomicity 保持。 | SEAM-001/002/003／collision、reuse、first-revision fixtures | error code、event count、current ref、occupied bytes 與 existing approvals 完全不變或按規格追加。 | AC-003..AC-006、FR-003、FR-004、NFR-001 | CMD-BDD-FOCUSED-002 | WP-001／2 |

| TEST ID | BDD／風險 | 層級／SEAM／fixture | Oracle／red | Focused／related CMD |
|---|---|---|---|---|
| TEST-001 | BDD-001／allocator 把 lower historical absence 當成 gap，阻擋合法下一版。 | integration／SEAM-002/003／plan／requirements revision-2 + generation-2 | pre-fix 的合法 plan-3／requirements-3 應用 transition 失敗；修正後 record 只追加 revision 3，current ref 正確。 | CMD-TDD-FOCUSED-001、CMD-RELATED-001 |
| TEST-002 | BDD-002／跳號、倒退、reuse 或 occupied path 造成錯誤覆寫或部分 mutation。 | contract／SEAM-001/002/003／missing／occupied／reuse matrix | `INVALID_REVISION` 或 existing reuse error；event count、current refs、existing path bytes unchanged；occupied plan-3 可保留後接受 plan-4。 | CMD-TDD-FOCUSED-002、CMD-RELATED-001 |

| CMD ID | Purpose | Observed／Proposed | 摘要；完整 contract 在 `handoff.json` |
|---|---|---|---|
| CMD-BUG-REPRO-001 | bug-reproduction | Proposed | 執行跨世代 plan-3 regression method，修改前應重現原始 `INVALID_REVISION`。 |
| CMD-BDD-DISCOVERY-001 | bdd-discovery | Observed | `rg` 列出既有與新增 revision transition test inventory；不以 discovery 取代 focused／full execution。 |
| CMD-BDD-FOCUSED-001 | bdd-focused | Proposed | 執行 `RevisionAllocationRegressionTests` 的 plan／requirements high-water scenarios。 |
| CMD-BDD-FOCUSED-002 | bdd-focused | Proposed | 執行 collision、reuse、倒退、首版與 atomicity scenarios。 |
| CMD-TDD-FOCUSED-001 | tdd-focused | Proposed | 執行 `TEST-001`，先取得 allocator red，再以單一 high-water change 綠化。 |
| CMD-TDD-FOCUSED-002 | tdd-focused | Proposed | 執行 `TEST-002` 的 failure／occupied matrix，確認 ref、event 與 bytes。 |
| CMD-BDD-FULL-001 | bdd-full | Observed | 執行完整 `test_delivery_transitions.py`，解析完整 unittest inventory、failure、error、skip。 |
| CMD-RELATED-001 | related | Observed | 執行既有 `run_full_suite.py --scope related --profile local`，覆蓋 Delivery workspace、transition、safety、contract owners。 |
| CMD-BUILD-FULL-001 | build-full | Observed | 執行既有 `run_quick_checks.py`，編譯 Git-eligible Python、解析 schemas 並做 owner checks。 |
| CMD-TEST-FULL-001 | test-full | Observed | 執行 `run_full_suite.py --scope all --profile local`，保存完整 child inventory 與 raw evidence。 |
| CMD-GOVERNANCE-001 | governance | Observed | 執行 `knowledge_cli.py lint --repo .`，確認 Knowledge provenance／index／promotion records。 |

`validation-plan/v1`：日常 target 為 Windows 11、Python 3.13+、Git 026a491e baseline、PowerShell 7 與 ripgrep；local obligations 綁定 `CMD-BUG-REPRO-001`、BDD/TDD focused、related、full build/test 與 governance；hosted Windows／Linux reports 是可選發布後 follow-up，單一本機平台不冒充跨平台證據。Final review 只能引用本 Work ID 的 implementation Outcome、fresh review、Knowledge promotion 與 terminal evidence；不得重用未列於 terminal-only policy 的可執行輸入。

執行順序：`CMD-BDD-DISCOVERY-001` → BDD-001／`TEST-001` red → minimal high-water green → focused BDD-001；再 BDD-002／`TEST-002` red → minimal green → focused BDD-002；最後完整 related、build、test、governance 與 fresh review。任一 failure 保留 raw evidence 並依 Delivery 回報，不修改既有 record。

## 4A. 本地完成條件

### AC-008 — 本地驗證可完成 Work

本地 target environment 的 regression、related、build、test 與 governance commands 全部通過時即可完成本 Work；hosted CI 與其他平台檢查若未執行，回報中明列為可選發布後 follow-up。

## 5. 工作包

### WP-001 — High-water revision allocation 與跨世代 transition regression

- 要求／結果／impact：FR-001..005、NFR-001、TR-001、AC-001..AC-008、CON-001..004。
- Blocked by：None。
- Consumes／produces：消費 current Requirements、BUG assessment、Delivery v1 record／generation；修改 `_assert_smallest_available_revision`，新增 `RevisionAllocationRegressionTests` cases 與可重算 test evidence；不產生新的 repository schema。
- Intent：以 record high-water 取代從 1 開始的 gap scan；保留 high-water 後缺席 gap、occupied path、reuse／倒退 guard 與 transition 原子性；先以 failing integration tests 鎖定症狀，再以最小 helper change 綠化。
- Slice order：BDD-001 → TEST-001 → high-water implementation → focused BDD-001；BDD-002 → TEST-002 → atomic/collision verification；related/full/platform checks。
- Commands／完成證據：`CMD-BUG-REPRO-001`、`CMD-BDD-DISCOVERY-001`、`CMD-BDD-FOCUSED-001`、`CMD-BDD-FOCUSED-002`、`CMD-TDD-FOCUSED-001`、`CMD-TDD-FOCUSED-002`、`CMD-BDD-FULL-001`、`CMD-RELATED-001`、`CMD-BUILD-FULL-001`、`CMD-TEST-FULL-001`、`CMD-GOVERNANCE-001`；保存 red→green、完整 inventory、record／path byte snapshots 與獨立 fresh review。

## 6. 風險與追溯

### 風險與取捨

| Risk ID | 觸發條件 | 影響 | Mitigation／驗證 | Owner／決策點 |
|---|---|---|---|---|
| RISK-001 | high-water 解析錯誤或 candidate revision 倒退未攔截 | 歷史可能倒退或新增 revision 不可重算 | 共用 parser、explicit `revision <= high_water` guard、AC-005 與既有 record validator | WP-001／Delivery |
| RISK-002 | gap scan 放寬到所有缺席 path 或 occupied 判定改變 | 可能允許跳號或覆寫 path | 僅掃描 high-water 後區間；保留既有 `parent.exists`／`lexists` 語義；AC-003／AC-004 | WP-001／Delivery |
| RISK-003 | transition 在驗證失敗後部分 append | approval、current ref 或事件歷史不一致 | 真實 `workspace.transition_record`、before/after snapshots、AC-003／AC-005／AC-007 | WP-001／Delivery |
| RISK-004 | regression fixture 只測 helper 而沒有 generation materialization | 原始跨世代症狀可能回歸 | 以 generation=2 worktree 與實際 Requirements／Plan transition 驗證，另跑 related/full | WP-001／Reviewer |
| RISK-005 | 本地 Windows 通過被誤報為跨平台完成 | Linux compatibility 未證明 | 在報告中明列 hosted workflow 未執行；另有發布需求時再補做 Linux／Windows reports，不影響本地完成 | WP-001／Platform reviewer |

### 追溯矩陣

| SRC／要求 | TD／MOD／SEAM | BDD | TEST | WP | CMD／證據 |
|---|---|---|---|---|---|
| SRC-001／FR-001、FR-002／AC-001、AC-002 | TD-001／MOD-001／SEAM-001、SEAM-002 | BDD-001 | TEST-001 | WP-001 | CMD-BUG-REPRO-001、CMD-BDD-FOCUSED-001、CMD-TDD-FOCUSED-001 |
| SRC-001／FR-003、FR-004、NFR-001／AC-003..AC-006 | TD-001、TD-002／MOD-001..003／SEAM-001..003 | BDD-002 | TEST-002 | WP-001 | CMD-BDD-FOCUSED-002、CMD-TDD-FOCUSED-002、CMD-RELATED-001 |
| SRC-002／confirmed BUG／AC-001 | TD-001／MOD-003／SEAM-002 | BDD-001 | TEST-001 | WP-001 | CMD-BUG-REPRO-001 |
| SRC-003、SRC-004、SRC-005／v1 transition and append-only | TD-001、TD-002／MOD-001、MOD-002 | BDD-001、BDD-002 | TEST-001、TEST-002 | WP-001 | CMD-BDD-FULL-001、CMD-BUILD-FULL-001、CMD-TEST-FULL-001、CMD-GOVERNANCE-001 |

## 7. Artifacts 與 readiness

### Artifact manifest

完整 `role`／`approval_status`／SHA-256 manifest 以 `handoff.json` 為權威；本節只提供閱讀索引。

| Path | Role | 建立理由 | 權威內容 |
|---|---|---|---|
| `docs/work/work-20260916-delivery-revision-gap/plan-2/plan.md` | primary | 主線方案、設計、測試與工作包索引 | 本文件 |
| `docs/work/work-20260916-delivery-revision-gap/plan-2/handoff.json` | handoff | Implementation consumer 的 `ready-plan/v1` contract | 完整 machine contract、commands、sources、DAG、validation |

### Readiness

- 缺口／未知／衝突：無；bug assessment verdict／root cause／reproduction 已確認，修法維持單一 causal change。
- BDD framework／BOOT／BDD／TDD／WP／commands：完整；BOOT 明確不適用，既有 seam evidence 已列 SRC-003／SRC-004。
- `handoff.json` schema 與 cross-references：候選封存前由 Technical Planning owner validator 與 Project Knowledge planning builder 驗證。
- 品質門檻：來源、設計、測試、原子性、相容性、本地完成條件、可選發布 follow-up 與追溯矩陣均通過；本 Candidate 尚待 Plan Gate 核准。

FR-001: 修訂版候選必須從已記錄最高 revision 之後開始檢查；較早缺席路徑不阻擋有效候選。
