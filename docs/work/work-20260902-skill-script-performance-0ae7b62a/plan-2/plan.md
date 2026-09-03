# 技術規劃：Skills Script 執行效率改善

- 狀態與核准證據：見 `handoff.json.approval`
- Candidate revision：`candidate-20260902-delivery-02`
- 日期：2026-09-02
- 來源規格：`docs/work/work-20260902-skill-script-performance-0ae7b62a/requirements.md`
- 範圍：Project Knowledge query、Delivery transition、knowledge scale benchmark
- Planning baseline：repo `0c5534020993ce0e527ffefdd0bbbdf8e3e26138d3933defe22de1ed5ea2530c`；HEAD `fc3a4ed45fb3ef70378413214b7983b062016c17`；status `db4a239c052bdc188c90a94711975fea2a49e8b2be6f4931cbd95866bf4b65d1`
- Primary／handoff：`docs/work/work-20260902-skill-script-performance-0ae7b62a/plan-2/plan.md`／`docs/work/work-20260902-skill-script-performance-0ae7b62a/plan-2/handoff.json`

## 1. 成果、範圍與限制

成果是三個可獨立驗證的效能 slice：query-scoped search session、lock-aware Delivery probe reuse、cold／warm benchmark。先以 child-process budget 和行為等價防止少做安全檢查，再量實際 wall time。

本計畫採用 invocation-scoped query snapshot、lock-aware Delivery evidence 與 additive cold/warm benchmark，以 deterministic process budgets 驗證行為等價。

> Revision 2：Implementation Preflight 實測 baseline inventory 為 17；本修訂只讓 Observed command criteria 同時適用現況與完成狀態，並讓 CI 依當前 report schema 驗證。需求、TD、Module、BDD／TEST、WP 與演算法均不變。

- 範圍內：`knowledge_query.py`、`knowledge_benchmark.py`、`compare_portability_reports.py`、Delivery Git/workspace/record probe 與其 owner tests／CI。
- 範圍外：tokenizer／ranking 行為、persistent cache／daemon、新 dependency、未證實的 `git fast-import`、其他非瓶頸 scripts。

| ID | Required／Observed 限制 | SRC-* |
|---|---|---|
| CON-001 | public result/error/security contracts preserved；benchmark 只加 additive fields。 | SRC-SPEC、SRC-PK-QUERY、SRC-DEL-CONTRACT |
| CON-002 | query snapshot 不跨 invocation；pre/post drift 仍 invalidates/fails closed。 | SRC-SPEC、SRC-PK-QUERY |
| CON-003 | Delivery evidence 只能在同 canonical worktree、HEAD 與 lock epoch 重用。 | SRC-SPEC、SRC-DEL-GIT、SRC-DEL-RECORD |
| CON-004 | 無 network／新 runtime dependency／persistent state；temp data 必須清除。 | SRC-SPEC、SRC-PK-BENCH |

## 2. 證據與變更影響

| SRC ID | Kind／location／revision | 事實 | Plan refs | 直接 WP refs |
|---|---|---|---|---|
| SRC-SPEC | spec／canonical requirements／Ready | 核准的 BG／BR／FR／NFR／TR、AC、基準與範圍。 | BR-001、FR-001..004、NFR-001..003、TR-001、AC-001..007 | WP-001、WP-002、WP-003 |
| SRC-PK-QUERY／SRC-PK-BDD | project／contract／HEAD | query 重複 fingerprint/search；既有 cache、drift、redirect、ranking coverage。 | TD-001、TD-002、BDD-018 | WP-001、003 |
| SRC-PK-BENCH／SRC-PK-COMPARE／SRC-CI | project／platform／HEAD | 只量 warm、逐檔 mkdir、CI 比較 warm ceiling/hash。 | TD-004、BDD-020 | WP-003 |
| SRC-DEL-GIT／SRC-DEL-WS／SRC-DEL-RECORD | project／HEAD | full probe 約 10 Git calls；Ready path 可重複三次。 | TD-003、BDD-019 | WP-002 |
| SRC-DEL-TEST／SRC-DEL-CONTRACT | contract／HEAD | worktree、submodule、filter、hook、trust、redirect 與 terminal invariants。 | CON-001、CON-003、TEST-019 | WP-002 |

### Current → target

| 影響 ID | 能力／Module | New／Modified／Removed／Preserved | 來源要求 |
|---|---|---|---|
| IMP-001 | Query execution | New invocation session；Modified search fan-out；Preserved JSON/error/order/security。 | BR-001、FR-001、NFR-001、NFR-003 |
| IMP-002 | Delivery probe | New identity/state evidence；Modified wrappers/Ready reuse；Preserved all gates。 | BR-001、FR-002、NFR-002、NFR-003 |
| IMP-003 | Benchmark/CI | New cold samples + fixture timing；Modified parent creation/comparator；Preserved warm key/hash。 | BR-001、FR-003、FR-004、NFR-001、TR-001 |

## 3. 設計與決策

### TD-001 — Query-scoped snapshot

- 需求／證據：BR-001、FR-001、NFR-001、NFR-003、AC-001、AC-002、SRC-PK-QUERY。
- 選定方案：entry 建立 immutable `QuerySearchSession`，只 capture 一次 pre fingerprint；eligibility、sidecar、content searches 共用 root、tracked view 與 runner；return 前只做一次 post fingerprint。不同即走現有 drift/invalidation 路徑。
- 替代方案：persistent daemon/index 會增加跨 process invalidation 與治理面；global memoization 可能隱藏 drift，兩者排除。
- 影響：public CLI 不變；command-recording seam 固化結果 parity 與 ≤10 child processes。

### TD-002 — Fixed-pattern multi-search

- 需求／證據：BR-001、FR-001、NFR-001、NFR-003、AC-001、AC-002、SRC-PK-QUERY。
- 選定方案：安全 normalized paths 以 stdin pattern set 交給 `rg -F -f - --max-count 1`，利用 ripgrep multi-pattern automaton，保留 deterministic parse/dedupe/order。
- 替代方案：自建 Aho–Corasick 增加 dependency；大型 regex 有 escaping/complexity 風險。
- 影響：含 CR/LF/NUL 或超出 stdin contract 的 pattern 使用既有分批 fallback；rg error mapping 不變。

### TD-003 — Delivery identity/state probe

- 需求／證據：BR-001、FR-002、NFR-002、NFR-003、AC-003、AC-004、SRC-DEL-GIT、SRC-DEL-WS、SRC-DEL-RECORD。
- 選定方案：`RepositoryIdentity` 保存 common-dir/repo-id/worktree/HEAD；`RepositoryStateEvidence` 保存 status/worktrees/submodules/filters/hooks/trust/merge-base 與 lock epoch。lock 前只取定位 identity；lock 後建立一次 fresh state。Ready validator 只有在 canonical path、HEAD、identity、epoch 全相同才消費 evidence，否則重新 probe/fail closed。
- 替代方案：盲目平行 Git processes 不消除重複 probe且增加 contention；完全移除 pre-lock identity 會失去 run 定位。
- 影響：可安全合併的 `rev-parse`/status metadata 批次取得；public JSON 不暴露 internal token。

### TD-004 — Cold/warm benchmark 與 fixture plan

- 需求／證據：FR-003、FR-004、NFR-001、TR-001、AC-005、AC-006、AC-007、SRC-PK-BENCH、SRC-PK-COMPARE、SRC-CI。
- 選定方案：保留 `durations_seconds.queries` 的五個 warm samples；新增 fresh Python processes 的五個 `cold_queries`、fixture timing；comparator 同時檢查 cold/warm ≤2 秒與 functional hash。fixture 先算 unique parent set、每個 parent 只 mkdir 一次。
- 替代方案：`git fast-import` 可能更快，但會改變 object/index 建立路徑；只有 AC-006 未達標才另案評估。
- 影響：warm consumer 相容；新 report/CI 要求 cold fields；Windows/Linux 都執行。

| MOD ID | 責任 | Caller-facing contract | SEAM | 隱藏內容 | 要求 |
|---|---|---|---|---|---|
| MOD-001 | QuerySearchSession／fixed lookup | query JSON/error/order 不變 | SEAM-001、002 | fingerprint cache、rg argv/fallback | BR-001、FR-001、NFR-001、NFR-003 |
| MOD-002 | RepositoryProbe | identity + lock → fresh state evidence | SEAM-003、004 | Git batching/provenance | FR-002、NFR-002、NFR-003 |
| MOD-003 | BenchmarkReport | fixture → cold/warm/timing/hash | SEAM-005 | child runner、parent plan、median | BR-001、FR-003、FR-004、NFR-001、TR-001 |

流程：query capture → shared searches → post-validate → return；Delivery lightweight locate → lock → fresh state → transition/Ready reuse。任何 path/HEAD/epoch mismatch 都重探或拒絕。

## 4. 測試策略

| BDD-FWK ID | Framework／版本 | Boundary／fixture | Discovery／zero-skip |
|---|---|---|---|
| BDD-FWK-001 | existing custom scenarios + `unittest`；Python 3.13 CI | stdlib；`.knowledge-test-tmp/` | CMD-BDD-DISCOVERY-001；full inventory nonzero/zero skip |
| BDD-FWK-002 | existing Delivery `unittest` owner surface | stdlib；OS temp Git repos | CMD-BDD-DISCOVERY-002；aggregated full zero skip |

| SEAM ID | 可觀察 Interface | 替身策略 | 層級 |
|---|---|---|---|
| SEAM-001 | `knowledge_cli query` JSON/exit | real temp Git + golden | BDD/integration |
| SEAM-002 | query runner/rg argv | recording spy | unit |
| SEAM-003 | Delivery public JSON | real temp Git | BDD/integration |
| SEAM-004 | `_git` runner/evidence epoch | recording spy + drift | unit |
| SEAM-005 | benchmark JSON/comparator | fake clock/child + scale fixture | unit/CI |

`BOOT-*`：不適用；SRC-PK-BDD、SRC-DEL-TEST 顯示 frameworks、fixtures 與 owner entry points 已存在。

| BDD ID | Scenario／正確 red | SEAM | Focused CMD | WP |
|---|---|---|---|---|
| BDD-018 | audit query parity + ≤10 processes；現況 22-call budget red，cache/drift/redirect/fallback 不可退化。 | SEAM-001、002 | CMD-BDD-FOCUSED-001 | WP-001 |
| BDD-019 | full probe ≤6、Ready ≤8 且 post-lock fresh；現況約 10/31 red，全部 safety gates 仍 fail closed。 | SEAM-003、004 | CMD-BDD-FOCUSED-002 | WP-002 |
| BDD-020 | 五 cold + 五 warm ≤2 秒、unique-parent mkdir、setup median +15%、hash/cleanup；現況缺 cold 且逐檔 mkdir red。 | SEAM-005 | CMD-BDD-FOCUSED-001 | WP-003 |

| TEST ID | BDD／inner oracle | Focused／related CMD |
|---|---|---|
| TEST-018 | BDD-018：pre capture=1、post validate=1、safe fixed search=1；pathological fallback/output parity。 | CMD-TDD-FOCUSED-001／CMD-RELATED-001 |
| TEST-019 | BDD-019：same path/HEAD/epoch reuse；任一 drift 重探；Git argv budget及 security parsers。 | CMD-TDD-FOCUSED-002／CMD-RELATED-002 |
| TEST-020 | BDD-020：warm key preserved、missing cold red、mkdir count=unique parents、cleanup-on-failure、median/hash。 | CMD-TDD-FOCUSED-001／CMD-CI-001 |

| CMD family | Observed／Proposed | 用途 |
|---|---|---|
| CMD-BDD-DISCOVERY-001／002 | Observed／Proposed | Knowledge scenario list／Delivery pure test list |
| CMD-BDD-FOCUSED-001／002 | Proposed | Knowledge performance group／Delivery probe budget |
| CMD-BDD-FULL-001／002 | Observed | 兩套 owner behavior full |
| CMD-TDD-FOCUSED-001／002 | Proposed | Knowledge performance units／Delivery evidence unit |
| CMD-RELATED-001／002 | Observed | Knowledge related／Delivery safety |
| CMD-BUILD-FULL-001／002 | Observed | 兩個 Skill validators |
| CMD-TEST-FULL-001／002 | Observed | 兩個 full owner suites |
| CMD-CI-001 | Observed command、modified contract | 50k/5k Windows/Linux benchmark |

順序：BDD budget/parity red → TEST red → minimal green → refactor-with-green → focused/related green。全部 WP 後 fresh full build/test/BDD/CI；零 unexpected skip。

## 5. 工作包

### WP-001 — Query-scoped search session

- 要求／impact：BR-001、FR-001、NFR-001、NFR-003；AC-001、AC-002、AC-007；IMP-001；MOD-001。
- Blocked by：None。
- Contracts：BDD-FWK-001、BDD-018、TEST-018。
- Intent／order：先錄 22-call red 與 output parity，再做 session capture，最後 fixed-pattern lookup/fallback。
- 完成：≤10 processes；五次 cold median改善 ≥25%；focused/related/full/build/test 全綠。

### WP-002 — Lock-aware Delivery probe reuse

- 要求／impact：BR-001、FR-002、NFR-002、NFR-003；AC-003、AC-004、AC-007；IMP-002；MOD-002。
- Blocked by：None。
- Contracts：BDD-FWK-002、BDD-019、TEST-019。
- Intent／order：先固定 10/31-call red，再拆 identity/state、batch metadata、加入 evidence provenance與 mismatch re-probe。
- 完成：full ≤6、Ready ≤8；transition median改善 ≥25%；safety/owner/full 全綠。

### WP-003 — Cold/warm benchmark 與全量證明

- 要求／impact：BR-001、FR-003、FR-004、NFR-001、TR-001；AC-005、AC-006、AC-007；IMP-003；MOD-003。
- Blocked by：WP-001、WP-002。
- Contracts：BDD-FWK-001、BDD-020、TEST-020。
- Intent／order：先加 cold report red，再 child runner/comparator；接著 unique-parent fixture plan與 cleanup；最後 cross-platform fresh verification。
- 完成：cold/warm ≤2 秒；setup median改善 ≥15%；functional hash 相同；repo clean。

## 6. 風險與追溯

| Risk | 影響 | Mitigation／decision |
|---|---|---|
| RISK-001 stale query snapshot | 漏 drift／回舊 cache | invocation-only + pre/post fingerprint + drift BDD；WP-001 |
| RISK-002 pattern encoding/pathology | false/missed match | safe predicate + fallback + Windows/Linux parity；WP-001 |
| RISK-003 evidence 跨 lock/worktree 誤用 | 繞過 Delivery gate | path/HEAD/identity/epoch provenance；mismatch fresh probe；WP-002 |
| RISK-004 Git batching 改 error mapping | public contract drift | parser unit + public JSON parity；WP-002 |
| RISK-005 cold noise／fixture主要成本其實是 git add | flaky 或未達 15% | raw five samples；AC-006 stop/measure gate；fast-import 另案；WP-003 |
| RISK-006 full suites 數百秒 | feedback 慢 | WP 內 focused/related，package/final 才 full；不減 coverage |

| SRC／Requirement | TD／SEAM | BDD／TEST | WP／Evidence |
|---|---|---|---|
| SRC-PK-QUERY／BR-001、FR-001、NFR-001、NFR-003 | TD-001、002／SEAM-001、002 | BDD-018／TEST-018 | WP-001／process budget + parity |
| SRC-DEL-*／FR-002、NFR-002、NFR-003 | TD-003／SEAM-003、004 | BDD-019／TEST-019 | WP-002／Git budget + safety |
| SRC-PK-BENCH、CI／BR-001、FR-003、FR-004、NFR-001、TR-001 | TD-004／SEAM-005 | BDD-020／TEST-020 | WP-003／median + portability |

## 7. Artifacts 與 readiness

| Path | Role | 權威內容 |
|---|---|---|
| `docs/work/work-20260902-skill-script-performance-0ae7b62a/plan-2/plan.md` | primary | 設計、測試、WP、風險、追溯 |
| `docs/work/work-20260902-skill-script-performance-0ae7b62a/plan-2/handoff.json` | handoff | `ready-plan/v1` manifests/contracts/commands |

- 缺口：無阻止 Candidate 審核的缺口；實際改善由 red→green/fresh gates 決定。
- BDD framework、BOOT disposition、BDD、inner tests、WP DAG、commands 已映射。
- schema/cross-reference：以 Technical Planning owner validator 驗證 exact bytes、digest、source hashes 與 cross-references。
- 狀態：Ready 身分與正式證據見 `handoff.json`／knowledge receipt；只授權進入 `implementation-execution`，不授權 commit、merge 或部署。
