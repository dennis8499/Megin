# 技術規劃：本地 AI SDLC 驗證與審查加速

- 狀態與核准證據：見 `handoff.json.approval`
- Candidate revision：`candidate-1`
- 日期：2026-09-07
- 來源規格：`docs/work/work-20260907-workflow-speed-d0b3946d/requirements.md`
- 範圍：五個工作包交付 validation profile、命令覆蓋、證據保存與引用、審查前置檢查、文件 render、archive／metrics、中文檢索及安全平行化
- Planning baseline：repo `0c5534020993ce0e527ffefdd0bbbdf8e3e26138d3933defe22de1ed5ea2530c`；HEAD `4e9558da8ac59db6fff32340d0fcc3504610143c`；status SHA-256 `31206f6bb0ba5bc541019277938b9827bdda674e38a0a64642cd9c82e9be51de`
- Primary／handoff：`docs/work/work-20260907-workflow-speed-d0b3946d/plan/plan.md`／`docs/work/work-20260907-workflow-speed-d0b3946d/plan/handoff.json`

## 1. 成果、範圍與限制

本計畫以單次實際執行覆蓋多項驗證義務，並以可驗證引用取代 Final Reviewer 的重複全量執行。

本次成果讓新工作明確選擇 local 或 release profile。Local workflow 中，主代理與 preliminary Reviewer 各執行一次完整 suite；final Reviewer 在 executable input identity 未變且僅新增已驗證 terminal evidence 時引用 preliminary execution。Runner 以一個原子 bundle 保存可重驗的原始證據，並由同一資料產生摘要、archive 與時間報告。

- 範圍內：Ready-plan additive validation block、coverage planner、suite evidence、executed／referenced outcomes、precheck、final reuse、deterministic render、archive verify/export/import、五類流程時間、中文 CJK query、Git test profiling與隔離 worker。
- 範圍外：移除人工 Gate 或 Reviewer、改寫舊 artifacts、跨機共享 cache、daemon、production dependency、部署／merge／push，以及自動觸發 hosted release。

| ID | Required／Observed 限制 | SRC-* |
|---|---|---|
| CON-001 | 舊 `ready-plan/v1`、execution records 與 run 缺少新 capability 時仍依 legacy contract 有效。 | SRC-REQ-001、SRC-READY-001、SRC-EXECUTION-001 |
| CON-002 | 每個 covered obligation 只有在 producer 子命令、inventory、raw outputs、input 與 environment identity 全部可重驗時成立。 | SRC-REQ-001、SRC-RUNNER-001 |
| CON-003 | Preliminary 與 Final 維持不同 fresh read-only session；Final 只重用 execution，不重用判定。 | SRC-REQ-001、SRC-REVIEW-001 |
| CON-004 | Skill、Schema、契約、測試、未分類 Markdown 與環境都屬 executable input；只允許同 Work ID 的 Outcome／snapshot／sealed Candidate descriptor 作 terminal-only additions。 | SRC-REQ-001、SRC-REVIEW-001、SRC-EXECUTION-001 |
| CON-005 | 所有檔案寫入 create-only 或同父目錄原子 rename，拒絕 symlink／junction、escape、collision、partial archive 與秘密值。 | SRC-REQ-001、SRC-RUNNER-001 |
| CON-006 | Release profile 沿用跨平台 CI；local pass 不投影成 release pass。 | SRC-REQ-001、SRC-CI-001 |

## 2. 證據與變更影響

| SRC ID | Kind／location／revision | 事實 | Plan refs | 直接 WP refs |
|---|---|---|---|---|
| SRC-REQ-001 | spec／approved Requirements／requirements-1 | Required：FR-001..010、NFR-001..005、TR-001、AC-001..017。 | CON-001..006、TD-001..006、BDD-101..501 | WP-001..005 |
| SRC-EVIDENCE-001 | supporting／`source-evidence.md`／candidate-1 | Observed：848.248 秒基準、重複命令、缺失 seams、目標工具版本與 absence probes。 | BDD-FWK-001、BOOT、CMD-* | WP-001..005 |
| SRC-READY-001 | contract／ready-plan schema／4e9558da8ac59db6fff32340d0fcc3504610143c | Observed：command contracts互不表達 coverage 或 profile。 | TD-001、MOD-001、SEAM-001 | WP-001 |
| SRC-RUNNER-001 | project／`run_full_suite.py`／4e9558da8ac59db6fff32340d0fcc3504610143c | Observed：順序執行、fail-fast、可選 metrics，完整 functional output只在 stdout。 | TD-002、TD-006、MOD-002、SEAM-002 | WP-001、WP-005 |
| SRC-REVIEW-001 | contract／reviewer contract／4e9558da8ac59db6fff32340d0fcc3504610143c | Observed：三個角色都要求 fresh full execution，且每個 command raw ref 必須獨立。 | TD-003、MOD-003、SEAM-003 | WP-002 |
| SRC-EXECUTION-001 | contract／execution records／4e9558da8ac59db6fff32340d0fcc3504610143c | Observed：outcome沒有 provenance、producer或 precheck/reuse binding。 | TD-003、TD-004、MOD-003、MOD-004 | WP-002、WP-003 |
| SRC-DOCTOR-001 | project／delivery doctor／4e9558da8ac59db6fff32340d0fcc3504610143c | Observed：只彙整 phase duration/returns。 | TD-004、MOD-004、SEAM-004 | WP-003 |
| SRC-QUERY-001 | project／knowledge query／4e9558da8ac59db6fff32340d0fcc3504610143c | Observed：連續中文成為單一 token，raw owner contract分數低於 canonical summaries。 | TD-005、MOD-005、SEAM-005 | WP-004 |
| SRC-DELIVERY-TEST-001 | project／Delivery fixture＋aggregator／4e9558da8ac59db6fff32340d0fcc3504610143c | Observed：integration/performance tests共用聚合入口，沒有 worker temp isolation或三段 timing。 | TD-006、MOD-006、SEAM-006 | WP-005 |
| SRC-CI-001 | project／knowledge portability workflow／4e9558da8ac59db6fff32340d0fcc3504610143c | Observed：Windows/Linux platform與 compare jobs提供 release evidence。 | TD-001、MOD-001 | WP-001 |

### Current → target

Current：Ready commands 是平面清單；full suite 重複包含 BDD/build/governance；metrics 沒有原始檔、identity 或 inventory；Reviewer 在昂貴命令後才可能發現靜態 blocker；final report無法表達引用；中文問題不會拆詞；Delivery Git tests不可安全分片；host-temp evidence沒有獨立 archive contract。

Target：`validation-plan/v1` capability 建立 local/release profile、obligation 與 coverage edge；`validation-evidence/v1` 保存唯一物理執行及其 children；`validation-reference/v1` fail closed驗證引用；`review-precheck/v1` 先判定便宜 blocker；render/archive/process metrics共同消費 hash-verified index；CJK terms 與 owner-contract ranking有固定 corpus；非效能 test shards只在 worker roots、TEMP與registry都隔離時平行執行。

| 影響 ID | 能力／Module | New／Modified／Preserved | 來源要求 |
|---|---|---|---|
| IMP-001 | Ready validation contract與suite evidence | New additive capability、planner、bundle；Modified runner/schema；Preserved legacy load與functional report | FR-001、FR-002、FR-005、FR-006、NFR-001/002/004/005 |
| IMP-002 | Review pipeline | New precheck/reuse bindings；Modified report semantics；Preserved two fresh Reviewers與breaker | FR-003、FR-004、NFR-001/002 |
| IMP-003 | Evidence operations與metrics | New render/archive/import/compare；Modified doctor metrics | FR-007、FR-010、NFR-003/005 |
| IMP-004 | Chinese retrieval | Modified tokenizer/ranking/corpus；Preserved eligibility/conflict/source validation | FR-008 |
| IMP-005 | Git fixture execution | New shard isolation與profiling；Modified suite scheduler；Preserved performance tests sequential | FR-009、NFR-003 |

## 3. 設計與決策

| Context | Observed／Required | Proposed | SRC／TD |
|---|---|---|---|
| Runtime | Windows、Python 3.14.6、Git 2.51、rg 15.2；stdlib only | threads只排程 subprocess；每個 child 使用獨立 TEMP/fixture root | TD-002、TD-006 |
| Plan compatibility | `ready-plan/v1` additionalProperties=false | optional完整 `validation` block；producer guidance要求新 plan 寫入，absence走 legacy | TD-001 |
| Evidence | metrics與functional output分離且不具引用 identity | create-only bundle＋canonical digests；functional stdout維持 | TD-002 |
| Review | preliminary/final都全跑 | cheap precheck；final驗證 reference 或 fresh execute | TD-003 |
| Recovery | run evidence依 host temp存活 | explicit archive manifest、verify、export、quarantine import、retention | TD-004 |
| Retrieval | Unicode word regex | bounded CJK segmentation＋owner contract reason/score | TD-005 |

### TD-001 — Additive validation-plan capability

- 需求／證據：FR-001、FR-005、NFR-004、TR-001、SRC-READY-001、SRC-CI-001。
- 選定方案：在 `ready-plan/v1` 新增 optional `validation` object；一旦存在即要求完整 `schema: validation-plan/v1`、`profile`、target environment、required obligations、coverage edges、release requirements及 reuse policy。Coverage edge固定 producer command、covered command、required child IDs及 inventory criteria；graph無環且只能從同一 Ready bundle的 command refs建立。
- 相容：舊 handoff沒有 `validation` 時完全走現有 validator；更新後由 Technical Planning SKILL 明定所有新 Candidate必須包含完整 block。Local profile綁本機 OS/runtime/tool versions；release profile明列平台/hosted evidence且不由 local outcome滿足。
- 替代方案：建立 `ready-plan/v2` 會同時修改所有 delivery/implementation consumer並迫使舊資料遷移，因此本輪拒絕。

### TD-002 — 唯一物理執行、原子 evidence 與 coverage planner

- 需求／證據：FR-001、FR-002、FR-006、NFR-001/002/005、AC-001..004、AC-010/011。
- 選定方案：新增 `validation_evidence.py`。`plan_executions` 先以完整 command identity 去除精確重複，再只在 coverage edge的 producer實際 children全數 passed、inventory完整、輸入及環境 identity相同時滿足 covered command。部分 coverage僅去掉已證明項目。
- Bundle：`validation-evidence/v1` index列 profile、execution input、environment、Ready payload、每個 child command contract digest、status/exit/timeout/duration、failure/skip counts、inventory及 stdout/stderr path/hash/byte count；not-run保留原因。Runner先寫安全 sibling staging directory、fsync後 create-only rename，成功／失敗／timeout都產生完整 index。
- Identity：execution input包含 HEAD、binary tracked diff、全部未忽略非terminal檔案 hash、Ready command bytes與所有 Skill/Schema/contract/Markdown；environment包含 OS、Python、Git及明示 prerequisites。未知 path歸 executable input。已知秘密只接受具名 env allowlist並精確遮蔽，名稱和值都不寫入。
- `validation-reference/v1` 保存 producer index、producer command/output refs及六個 digests；verify缺檔、redirect、hash drift、timeout、not-run或 identity不同即退出3並要求 fresh execution。

### TD-003 — Reviewer precheck 與 Final execution reuse

- 需求／證據：FR-003、FR-004、NFR-001/002、SRC-REVIEW-001、SRC-EXECUTION-001。
- 選定方案：execution schema additive加入 optional `review_stage`、`precheck`及 command provenance。新報告整組使用：preliminary outcome只能 `executed`；final可 `referenced`，但須有本輪 verifier output及 producer review/index/output bindings。Legacy欄位缺失維持既有語義。
- Precheck：Reviewer在命令前驗證完整 source/requirement coverage、base-to-working-tree diff與untracked manifest、BDD/TDD oracle red/green evidence、Ready/evidence完整性、snapshot及environment。`review-precheck/v1`為 `passed|blocked`；blocked時一次彙整 blocking findings，昂貴 commands全部 `not_run`且 reason固定 `precheck_blocked`，verdict為 CHANGES_REQUIRED/BLOCKED。
- Final reuse：不同 fresh final Reviewer自行讀取完整產品、Outcome、Candidate與preliminary raw evidence。只有 executable input identity相同，且差異精確為同 Work ID 的連續 Outcome、snapshot descriptor、sealed Candidate descriptor與本輪 verifier outputs時可引用；產品、測試、Skill、Schema、環境、command或未分類 path改變即 fresh full execution。
- Reviewer仍各自形成 requirement coverage、findings與 verdict；引用不等於沿用 preliminary verdict。

### TD-004 — Deterministic render、archive 與五類時間

- 需求／證據：FR-007、FR-010、NFR-003/005、AC-012、AC-015/016、SRC-DOCTOR-001。
- 選定方案：同一 CLI 提供 `verify`、`render`、`archive export|verify|import`及 `benchmark compare`。Render只讀 schema-valid handoff/index，依 ID/path排序輸出 command摘要、SRC→BDD→TEST→WP追溯與 evidence overview，內容不含執行時間戳。
- Archive：`evidence-archive/v1` manifest含 run/repo/worktree identity、relative paths、hash與byte count；export使用 deterministic ZIP entries且拒絕redirect/secret sentinel。Import只進 create-only quarantine `<host-temp>/implementation-execution/imports/<archive-id>`，驗證完整後回傳 resume evidence，不改 live run、產品或 approval。
- Retention：active/blocked/awaiting runs不自動刪除；Complete後至少30天；prune只能明示執行且先產生manifest。無daemon或自動清除。
- Metrics：doctor additive輸出 `activity_durations_seconds`：commands/review取 evidence timestamps或duration，human_wait取 awaiting_user區間，interruption取 blocked區間，active_work為可證明 active interval扣除不重疊 command/review；無法證明者為null並列 reason。Comparator要求三個 baseline與三個 optimized local samples、相同 environment/input class，median改善小於30%退出1。

### TD-005 — Bounded CJK terms 與 owner-contract answer source

- 需求／證據：FR-008、AC-013、SRC-QUERY-001。
- 選定方案：保留 ASCII token規則；對每個 CJK run加入完整 run、2/3字 n-grams及小型版本化 domain aliases，去重並限制總terms。Raw `.agents/skills/*/references/*.md` 若有唯一 authority marker，加入 `owner-contract` reason及固定 bonus，使直接 owner contract可進Top-5，同時仍執行 eligibility、hash與conflict檢查。
- Corpus新增「整段流程的速度」與「實作完成後為什麼需要兩次審查」，預期 Top-5 source_ref為 validation/reviewer owner contract；mutation、drift與invalid source仍不得命中。

### TD-006 — Worker isolation、fixture profiling 與效能取樣

- 需求／證據：FR-009、NFR-003、AC-014/016、SRC-RUNNER-001、SRC-DELIVERY-TEST-001。
- 選定方案：runner將 child標為 `parallel_safe`或`sequential_performance`。每個 parallel child取得 create-only worker root、fixture root、registry與 TMP/TEMP/TMPDIR；最多 `--jobs` 個 stdlib thread等待獨立 subprocess。Fail-fast停止排新工作，已啟動者收完證據，其餘 not_run。
- Delivery fixture量測 repository setup helpers、test body與cleanup，輸出獨立 profile sidecar；performance class固定在全部平行工作結束後單獨執行。Worker cleanup逐一驗證沒有 registry/worktree residue。
- Benchmark：任何產品修改前重複執行 Observed baseline三次並保存metrics；完成後在同機以相同 local profile執行 optimized三次。`benchmark compare`只接受六份hash-valid samples；report明列中位數、改善率及五類時間。

| MOD ID | 責任 | Caller-facing contract | SEAM／Adapter | 隱藏內容 | 要求 |
|---|---|---|---|---|---|
| MOD-001 | Validation plan | additive `validation-plan/v1` block與coverage DAG | SEAM-001 Ready validator | legacy branching、cross refs | FR-001、FR-005 |
| MOD-002 | Validation evidence | runner flags、planner、bundle verify/reference | SEAM-002 CLI＋index filesystem | staging、hash、redaction、scheduler | FR-001/002/006 |
| MOD-003 | Review pipeline | precheck與executed/referenced outcomes | SEAM-003 review schema/validator | producer chain與terminal allowlist | FR-003/004 |
| MOD-004 | Evidence operations | render/archive/benchmark與doctor activity metrics | SEAM-004 CLI/read-only doctor | ZIP safety、retention、interval math | FR-007/010、NFR-003 |
| MOD-005 | Knowledge retrieval | query_repository Top-5 owner sources | SEAM-005 public query CLI/API | CJK segmentation與ranking | FR-008 |
| MOD-006 | Delivery test runtime | isolated shards與setup/body/cleanup report | SEAM-006 full runner/test CLI | worker env與performance serialization | FR-009 |

## 4. 測試策略

| BDD-FWK ID | Observed／Proposed framework、版本與來源 | Test-only／安裝邊界 | Feature／binding／fixture | Discovery／report／zero-skip |
|---|---|---|---|---|
| BDD-FWK-001 | Observed standard-library unittest scenario registry；`test_behavior.py` | stdlib only；無安裝 | Proposed `workflow-speed` group；isolated worker fixtures | CMD-BDD-DISCOVERY-001、CMD-BDD-FOCUSED-001、CMD-FULL-LOCAL-001；failed=0、skipped=0、not_run=0 |

| SEAM ID | 可觀察 Interface | 替身策略 | 測試層 |
|---|---|---|---|
| SEAM-001 | Ready validation capability/cross refs | in-memory legacy/new handoffs | schema/contract |
| SEAM-002 | suite planner/index/files | fake child processes＋temporary Git repo；一個 real related run | unit/integration/BDD |
| SEAM-003 | precheck/reference/review report | real hashes＋tampered copies | contract/integration |
| SEAM-004 | render/archive/metrics/compare | temp archives、event/evidence fixtures | unit/integration |
| SEAM-005 | query CLI/API | repository corpus＋invalid source fixture | BDD/regression |
| SEAM-006 | sharded Delivery tests | subprocess worker roots＋sentinels | integration/performance |

`BOOT-*`：不適用。SRC-EVIDENCE-001證明 Ready validator、runner、review validator、query及Delivery test入口皆已存在且可載入；本次只新增 additive seams。

| BDD ID | 要求／scenario | SEAM／fixture | Oracle／正確 red | Focused CMD | WP/order |
|---|---|---|---|---|---|
| BDD-101 | full suite覆蓋BDD/build/governance且每個child只執行一次 | SEAM-001/002／fake counter | baseline無coverage block，重複counter assertion red | CMD-BDD-FOCUSED-001 | WP-001/1 |
| BDD-102 | partial coverage只執行缺項；local/release狀態分離 | SEAM-001/002／mixed graph | baseline無planner/profile，selected set assertion red | CMD-BDD-FOCUSED-001 | WP-001/2 |
| BDD-103 | pass/fail/timeout產生原子完整bundle，缺檔/漂移/redirect不可引用 | SEAM-002／temp repo | baseline無bundle/ref verifier，contract assertion red | CMD-BDD-FOCUSED-001 | WP-001/3 |
| BDD-201 | blocking precheck彙整退件且昂貴命令precheck_blocked | SEAM-003／invalid coverage/oracle | baseline先執行命令且無precheck欄位 | CMD-BDD-FOCUSED-001 | WP-002/1 |
| BDD-202 | precheck通過後preliminary fresh執行；final只在terminal additions時引用 | SEAM-003／two review snapshots | baseline final必重跑，referenced assertion red | CMD-BDD-FOCUSED-001 | WP-002/2 |
| BDD-203 | product/test/Skill/Schema/environment/unknown input漂移觸發fresh execution | SEAM-002/003／one mutation each | baseline無reuse identity，rejection assertion red | CMD-BDD-FOCUSED-001 | WP-002/3 |
| BDD-301 | handoff/index render deterministic；archive round-trip完整、invalid零mutation | SEAM-004／temp bundle/archive | baseline無CLI，output/atomicity assertion red | CMD-BDD-FOCUSED-001 | WP-003/1 |
| BDD-302 | doctor輸出五類時間或具名不可得；六樣本比較30% | SEAM-004／events/samples | baseline只phase durations，category assertion red | CMD-BDD-FOCUSED-001 | WP-003/2 |
| BDD-401 | 兩個中文自然問題Top-5含owner contract且invalid source排除 | SEAM-005／repo corpus | baseline零結果，source-ref assertion red | CMD-BDD-FOCUSED-001 | WP-004/1 |
| BDD-501 | isolated functional shards等價無殘留；performance sequential且三段計時 | SEAM-006／worker sentinels | baseline無jobs/profile，isolation assertion red | CMD-BDD-FOCUSED-001 | WP-005/1 |

| TEST ID | BDD／風險 | 層級／SEAM／fixture | Oracle／red | Focused／related CMD |
|---|---|---|---|---|
| TEST-101 | BDD-101／錯誤coverage假通過 | unit／SEAM-001/002 | child IDs、inventory及counter；缺graph先red | CMD-TDD-FOCUSED-001/002、CMD-RELATED-001 |
| TEST-102 | BDD-102／缺項被錯刪或profile混淆 | schema＋unit | selected command set與release state | CMD-TDD-FOCUSED-001/002、CMD-RELATED-001 |
| TEST-103 | BDD-103／evidence遺失或path攻擊 | filesystem integration | all hashes、create-only、tamper matrix | CMD-TDD-FOCUSED-001、CMD-RELATED-001 |
| TEST-201 | BDD-201／退件仍先跑昂貴命令 | contract／SEAM-003 | precheck blocked與全not_run固定原因 | CMD-TDD-FOCUSED-002、CMD-RELATED-001 |
| TEST-202 | BDD-202／引用冒充執行 | contract/integration | provenance、producer/verifier chain與fresh attestation | CMD-TDD-FOCUSED-001/002、CMD-RELATED-001 |
| TEST-203 | BDD-203／terminal allowlist過寬 | mutation matrix | 七類input逐項拒絕，合法Outcome/Candidate接受 | CMD-TDD-FOCUSED-001/002、CMD-RELATED-001 |
| TEST-301 | BDD-301／render漂移或archive partial write | unit/filesystem | byte equality、ZIP traversal/redirect/collision | CMD-TDD-FOCUSED-001、CMD-RELATED-001 |
| TEST-302 | BDD-302／時間重疊或假達標 | unit | interval categories、null reasons、median comparator | CMD-TDD-FOCUSED-003、CMD-RELATED-001 |
| TEST-401 | BDD-401／過度token或authority繞過 | query regression | bounded terms、Top-5、drift/conflict exclusion | CMD-TDD-FOCUSED-003、CMD-RELATED-001 |
| TEST-501 | BDD-501／worker collision/flaky perf | subprocess integration | env/root uniqueness、result parity、profile fields | CMD-TDD-FOCUSED-004、CMD-RELATED-001 |

順序：每個 scenario先取得因目標能力缺失造成的BDD assertion red，再取得映射inner test red；minimal green、refactor-with-green後重跑 focused與related。WP-001任何產品修改前先執行三次 CMD-BASELINE-001..003。所有WP完成後執行三次 CMD-OPTIMIZED-001..003並以CMD-BENCHMARK-001判定；主代理 terminal build/test/BDD/governance四項全部由一次CMD-FULL-LOCAL-001的verified coverage滿足。Preliminary Reviewer再獨立執行一次；Final依TD-003引用或fresh執行。

## 5. 工作包

### WP-001 — Validation capability、coverage planner與evidence bundle

- 要求／結果：FR-001/002/005/006、NFR-001/002/004/005、TR-001、AC-001..004、AC-009..011/017。
- Blocked by：None。
- Modules／Seams／files：MOD-001/002、SEAM-001/002；Planning schema/contract/validator/tests、new validation evidence library/tests、full runner與BDD group。
- Consumes／produces：legacy Ready commands＋runner → optional validation-plan、unique execution plan、validation-evidence/reference。
- Slice order：三次Observed baseline → BDD-101→TEST-101 → BDD-102→TEST-102 → BDD-103→TEST-103。
- 完成證據：focused/related green；legacy fixtures byte-compatible；success/failure/timeout/tamper cases；local/release state分離。

### WP-002 — Cheap precheck與Reviewer execution reuse

- 要求／結果：FR-003/004、NFR-001/002、AC-005..008。
- Blocked by：WP-001。
- Modules／Seams／files：MOD-003、SEAM-003；execution schema/validator/tests、reviewer contract、preflight/delivery references。
- Consumes／produces：validation evidence＋product snapshot → precheck report、executed/referenced review outcomes。
- Slice order：BDD-201→TEST-201 → BDD-202→TEST-202 → BDD-203→TEST-203。
- 完成證據：legacy report仍通過；new preliminary/final matrices與drift cases green；blocking precheck未啟動fake expensive command。

### WP-003 — Render、archive、續跑與流程時間

- 要求／結果：FR-007/010、NFR-003/005、AC-012、AC-015/016。
- Blocked by：WP-002。
- Modules／Seams／files：MOD-004、SEAM-004；validation evidence CLI/contracts/tests、delivery doctor與operator docs。
- Consumes／produces：handoff/evidence/delivery events → deterministic Markdown、verified quarantine archive、activity metrics、benchmark report。
- Slice order：BDD-301→TEST-301 → BDD-302→TEST-302。
- 完成證據：round-trip/tamper/path tests、zero live mutation、五類欄位、median comparator green。

### WP-004 — 中文自然問題檢索

- 要求／結果：FR-008、AC-013。
- Blocked by：WP-003。
- Modules／Seams／files：MOD-005、SEAM-005；knowledge query、search-quality corpus/evaluator/tests、owner evidence contract。
- Consumes／produces：CJK question＋eligible repo → bounded terms與Top-5 owner source refs。
- Slice order：BDD-401→TEST-401。
- 完成證據：指定兩題100% Top-5命中；現有corpus門檻與invalid/drift/conflict tests全綠。

### WP-005 — Git fixture profiling、安全分片與效能驗收

- 要求／結果：FR-009、NFR-003、AC-014/016。
- Blocked by：WP-004。
- Modules／Seams／files：MOD-002/006、SEAM-002/006；Delivery fixture/aggregator、runner scheduler、tests/docs。
- Consumes／produces：sequential aggregate tests → isolated functional shards＋sequential performance＋setup/body/cleanup evidence。
- Slice order：BDD-501→TEST-501 → 三次 optimized full samples → benchmark compare。
- 完成證據：jobs=1與jobs=4 inventory/result parity、無殘留、performance獨立；六份同環境sample median至少改善30%，否則維持Fixing不宣稱達標。

## 6. 風險與追溯

| Risk ID | 觸發條件 | 影響 | Mitigation／驗證 | Owner |
|---|---|---|---|---|
| RISK-001 | coverage edge或inventory誤判 | required command被漏跑 | child allowlist、acyclic graph、partial/missing/tamper tests | WP-001 |
| RISK-002 | terminal allowlist排除可執行Markdown | stale evidence被引用 | Work-ID＋schema＋path＋hash封閉分類；unknown全部invalidating | WP-002 |
| RISK-003 | parallel Git processes共享temp/registry | collision、flaky、刪除他人資料 | worker TMP/fixture/registry全隔離；performance serialized；residue assertion | WP-005 |
| RISK-004 | evidence/archives含秘密或redirect | 資料外洩／path escape | exact-value redaction、lstat chain、create-only staging、malicious ZIP tests | WP-001/003 |
| RISK-005 | owner-contract bonus壓過可靠canonical結果 | retrieval品質退化 | 僅authority marker＋eligible/hash-valid raw；既有20+ corpus regression | WP-004 |
| RISK-006 | benchmark環境或sample不一致 | 30%宣稱不可信 | environment/input digest equality、三樣本、median與fail-closed comparator | WP-005 |

| SRC／要求 | TD／MOD／SEAM | BDD | TEST | WP | CMD／證據 |
|---|---|---|---|---|---|
| FR-001/002/005/006、NFR-001/002/004/005、TR-001 | TD-001/002、MOD-001/002、SEAM-001/002 | BDD-101..103 | TEST-101..103 | WP-001 | focused/related/full evidence |
| FR-003/004、AC-005..008 | TD-003、MOD-003、SEAM-003 | BDD-201..203 | TEST-201..203 | WP-002 | precheck/reference/review reports |
| FR-007/010、NFR-003/005 | TD-004、MOD-004、SEAM-004 | BDD-301/302 | TEST-301/302 | WP-003 | render/archive/doctor/benchmark |
| FR-008、AC-013 | TD-005、MOD-005、SEAM-005 | BDD-401 | TEST-401 | WP-004 | query corpus report |
| FR-009、AC-014/016 | TD-006、MOD-006、SEAM-006 | BDD-501 | TEST-501 | WP-005 | shard profile＋six samples |

## 7. Artifacts 與 readiness

| Path | Role | 權威內容 |
|---|---|---|
| `docs/work/work-20260907-workflow-speed-d0b3946d/plan/plan.md` | primary | 設計、BDD/TDD、工作包、風險與追溯 |
| `docs/work/work-20260907-workflow-speed-d0b3946d/plan/source-evidence.md` | supporting | baseline、工具版本、absence與相容證據 |
| `docs/work/work-20260907-workflow-speed-d0b3946d/plan/handoff.json` | handoff | ready-plan/v1 commands、sources、DAG、hashes與approval identity |

- Requirements、技術未知與衝突：無。
- BDD framework：現有 stdlib unittest registry；無安裝、無BOOT。
- 本工作 target profile：local／Windows／Python 3.14.6；release CI維持獨立狀態。
- Full build、test、BDD與governance command contracts刻意指向同一 physical runner invocation；實作後只有 verified coverage edge可令同一 evidence滿足四項義務。
- Candidate payload、artifact/source hashes、DAG、cross references與Proposed absence evidence由owner validator重算。
