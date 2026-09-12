# 技術規劃：既有 16 個 BUG 改善、驗證與結案追蹤

- 計畫狀態：Ready
- Candidate revision：candidate-3
- 日期：2026-09-12
- 來源規格：docs/work/work-20260912-bug-remediation-0e0ea628/requirements-2.md
- 範圍：建立 16 個 BUG 的現況基準、P0/P1 安全與契約回歸、P2 效能量測，以及逐項 bug-verification/v1 結案證據
- Planning baseline：repo_id、HEAD 與 status hash 以 handoff.json 為權威
- Primary／handoff：docs/work/work-20260912-bug-remediation-0e0ea628/plan-3/plan.md／docs/work/work-20260912-bug-remediation-0e0ea628/plan-3/handoff.json

## 1. 成果、範圍與限制

本工作以目前 repository 的 17 份 assessment 去重為 16 個 BUG identity。assessment 是歷史症狀與根因證據，不直接代表目前仍存在；每項必須由現行 oracle、回歸測試、平台結果與 fresh review 重新判定。既有程式已含部分 assessment 所描述的修復，故 WP-001 先建立基準，WP-002 至 WP-004 只修改仍可重現的最小根因。

範圍內：
- 建立 docs/bugs/status-review.md，合併 knowledge-outcome-create-only-toctou 的 assessment-1 與 assessment-2，但保留兩個 revision 連結。
- 以既有 Project Knowledge BDD、owner test、validator 與 benchmark 驗證交易完整性、路徑安全、Ready/reviewer 契約與 2 秒效能門檻。
- 對每個宣告修復的 BUG 建立 docs/bugs/<bug-id>/verifications/work-20260912-bug-remediation-0e0ea628.json；無完整證據者明確保留 partial 或 insufficient-evidence。
- 保留公開 CLI、JSON schema、2 秒門檻與既有 assessment bytes；不執行 commit、merge、push、部署或外部通知。

範圍外：
- 新增功能、改變公開介面、改寫歷史 assessment、改造既有 Outcome 或以重跑成功樣本取代超標樣本。
- 將 Linux 缺少執行環境、無法重現或缺少 reviewer／平台證據的項目標為 verified-fixed。
- 以效能最佳化犧牲 atomic publish、create-only、回滾所有權或 fail-closed 安全語義。

## 2. 證據與變更影響

| ID | 目前證據 | target state | 受影響工作包 |
|---|---|---|---|
| IMP-001 | outcome、promotion 與 delivery helper 已有 identity／preimage／component 檢查；需重跑原始 oracle | 發布碰撞不覆寫、回滾只處理本 writer、復原失敗保留材料 | WP-001、WP-002 |
| IMP-002 | validator 與 review consumer 已有 Ready／closed-schema 路徑；需驗證每個入口 | 所有 consumer 使用同一權威 validator，reviewer identity 不可重用 | WP-001、WP-003 |
| IMP-003 | BDD-016、BDD-020 與 benchmark 可量測固定 workload | readiness 與正式 samples 分離，所有正式 sample 原樣保存且不超過 2 秒 | WP-001、WP-004 |
| IMP-004 | docs/bugs assessment 共 17 份、16 個 identity | status-review 可由 evidence 重算，verification create-only 並與 work/review/hash 綁定 | WP-001、WP-004 |

### 16 BUG 覆蓋與優先順序

| BUG | Severity | WP | 現況 oracle／驗收焦點 |
|---|---:|---|---|
| bug-knowledge-apply-commit-boundary-toctou | Critical | WP-002 | commit boundary 被替換時 PREIMAGE_DRIFT、無 receipt、競爭者保留 |
| bug-knowledge-apply-concurrent-state-loss | High | WP-002 | later state 不被 commit／rollback 覆寫或刪除 |
| bug-knowledge-candidate-publish-overwrite | High | WP-002 | final registry occupied 時 create-only collision、既存 entry 保留 |
| bug-knowledge-outcome-create-only-toctou | High | WP-002 | pair publish collision 與同 bytes 不同 identity 的 ownership rollback |
| bug-knowledge-promotion-retirement-read-failure | High | WP-002 | retirement read failure 恢復 preimage，或明確 RECOVERY_REQUIRED |
| bug-knowledge-candidate-ancestor-redirect | High | WP-003 | ancestor junction/symlink 與 leaf read 期間替換均拒絕 |
| bug-knowledge-promotion-registry-component-validation | High | WP-003 | registry 每一 component fail-closed、stable regular-file read |
| bug-linux-posix-path-classification | Medium | WP-003 | Linux 普通 POSIX path 通過，真 symlink 與 inspection error 拒絕 |
| bug-linux-delivery-posix-path-classification | Medium | WP-003 | Linux Delivery 普通 artifact path 與 revision diagnostic 通過 |
| bug-delivery-knowledge-formal-paths-bypass | High | WP-003 | Requirements/Planning receipt 綁定完整 canonical formal_paths |
| bug-delivery-reviewer-identity-reuse | High | WP-003 | preliminary/final 相同 agent_id fail closed |
| bug-knowledge-page-closed-contract-lint | High | WP-003 | page、claim、source nested unknown member 被 seal/lint 拒絕 |
| bug-preliminary-review-ready-validation | High | WP-003 | persistence/Outcome/Delivery 一律要求 Ready validator zero errors |
| bug-bdd016-warm-query-tail | Medium | WP-004 | 50k/5k workload 五次 warm samples 全部不超過 2 秒 |
| bug-bdd020-first-cold-tail | Medium | WP-004 | readiness 不計時，五次 fresh cold samples 全部保存並不超過 2 秒 |
| bug-bdd020-review-query-tail | High | WP-004 | reviewer 的五 cold／五 warm samples、hash、cleanup 與門檻完整 |

## 3. 設計與決策

### TD-001 — 現況先行與最小修復

每個 BUG 先從 assessment 的原始症狀建立或重跑可否證 oracle，再執行對應 BDD／TEST。現行程式已通過的案例只補 verification evidence；只有仍可重現的案例才加入最小 regression red 與單一 causal fix。若 red 顯示 assessment 根因或 Ready scope 不正確，停止該 slice，保留 evidence 並回到 upstream reapproval。

### TD-002 — P0 發布與回滾所有權

沿用 knowledge_outcome、knowledge_promotion 的 create-only／preimage／file identity 邊界。commit boundary 重新檢查 target；rollback 僅在 bytes 與 identity 都證明為本 writer 時移除。競爭者、後續寫入或 recovery collision 都不得被刪除；恢復無法安全完成時保存 journal、復原材料並回報 typed RECOVERY_REQUIRED。

### TD-003 — P1 canonical path 與 validator

所有 Candidate、promotion、Delivery 與 repository artifact consumer 透過既有 owner validator 檢查 canonical root 下的每個 component。POSIX 不把缺少 Windows st_file_attributes 誤判為 reparse；symlink、junction、path escape、lstat/read error 仍 fail closed。Ready manifest、nested page schema、preliminary review 與 reviewer identity 不另建平行語義。

### TD-004 — P2 量測邊界與資料一致性

benchmark 固定 50,000 files／5,000 pages，分開 readiness、fresh-process cold 與 warm samples；保存所有五次樣本、functional hash、fixture profile、環境與失敗結果。staged、dirty、deleted、untracked 與查詢期間變更使用既有 query/Git overlay oracle。任一正式 sample 超過 2 秒保留為 failure，不能以後續成功樣本覆蓋。

### MOD-001 — transaction and recovery boundary

- Caller-facing contract：create-only、CAS/preimage、identity-aware rollback、typed collision/recovery error。
- Preserved：public knowledge CLI、receipt schema、journal semantics。
- Required：AC-003、AC-004、NFR-001、NFR-004。

### MOD-002 — canonical path and closed-contract boundary

- Caller-facing contract：canonical root component validation、stable no-follow read、closed schema、Ready coverage 與 independent reviewer identity。
- Preserved：合法普通目錄、合法 Ready manifest 與既有 result mapping。
- Required：AC-005、AC-006、AC-007、NFR-002。

### MOD-003 — status and verification evidence boundary

- Caller-facing contract：16 unique rows、assessment revision list、status enum、evidence refs、next action、create-only verification。
- Preserved：歷史 assessment bytes；verification 不回寫 assessment 或 Outcome。
- Required：AC-001、AC-002、AC-009、FR-008。

### MOD-004 — benchmark boundary

- Caller-facing contract：固定 fixture、readiness/cold/warm 分界、完整 samples、functional hash、cleanup 與 2 秒 assertion。
- Preserved：現有 BDD-016／BDD-020 semantics 與 query results。
- Required：AC-008、NFR-003。

## 4. 測試策略

使用 repository 既有 stdlib unittest、Project Knowledge behavior runner、owner validators 與 benchmark；不新增測試 framework 或 runtime dependency。BDD contract ID 以 BDD-BUG-001..016 對應下表的既有 scenario；TEST contract ID 使用同序號對應既有 owner/inner test seam。

| BDD | 對應既有 oracle | fixture／seam | 正確 red 與 green |
|---|---|---|---|
| BDD-BUG-001..005 | BDD-013、promotion commit/recovery tests | isolated registry、journal、pair targets | competitor/later-state 被覆寫或誤刪為 red；conditional commit/rollback 後保留 |
| BDD-BUG-006..009 | BDD-017、Delivery path owner tests | registry ancestor、POSIX path、junction/symlink | ordinary POSIX 被誤拒或 redirect 被放行為 red；component validator 正確分類 |
| BDD-BUG-010..013 | BDD-006、BDD-007、BDD-008、BDD-015 | Ready handoff、page nested schema、review reports | 缺 manifest、unknown member、相同 reviewer 被接受為 red；權威 validator fail closed |
| BDD-BUG-014..016 | BDD-016、BDD-020、knowledge_benchmark | 50k files／5k pages、Git overlay | 任一正式 sample >2 sec、hash drift、fixture leak 或 overlay mismatch 為 red |

BDD framework、discovery、focused、full、TDD、related、build、test、governance、benchmark 與 Windows/Linux command 的完整 machine contract 在 handoff.json。執行順序為 WP-001 discovery/baseline → P0 WP-002 → P1 WP-003 → P2 WP-004 → full validation/fresh review。每個 WP 先取得正確 red（若目前已修復則以 historical symptom evidence + current green oracle 標示不適用 red），再重跑 focused/related/full。

## 5. 工作包

### WP-001 — 16 項現況基準與追蹤表

- 要求／結果：FR-001、FR-002、FR-007、FR-008、AC-001、AC-002、AC-009。
- Blocked by：None。
- Intent：讀取最新 assessment、合併 duplicate revision、執行適用原始 oracle與回歸，建立 status-review.md 初版；不修改產品。
- Slice order：BDD discovery → current BDD/owner baseline → 16-row status classification → evidence gap list。
- Commands／完成證據：CMD-BDD-DISCOVERY-001、CMD-BDD-FOCUSED-*、CMD-RELATED-001、CMD-GOVERNANCE-001；status-review 與保存的原始輸出。

### WP-002 — P0 交易、發布與失敗復原

- 要求／結果：FR-003、NFR-001、NFR-004、AC-003、AC-004。
- Blocked by：WP-001。
- Intent：以 BDD-013、BDD-017 與 outcome/promotion workflow tests 重現 commit-boundary、pair collision、retirement read failure 與 recovery collision；只在 red 時修改 transaction boundary。
- Slice order：commit mismatch → later-state rollback → pair ownership → candidate final-name collision → retirement recovery。
- Commands／完成證據：CMD-BDD-FOCUSED-001、CMD-TDD-FOCUSED-001、CMD-RELATED-001；每項 BUG 的 pre/post、regression 與 recovery evidence。

### WP-003 — P1 路徑、Ready 契約與 review integrity

- 要求／結果：FR-004、FR-005、NFR-002、AC-005、AC-006、AC-007。
- Blocked by：WP-002。
- Intent：驗證 candidate/promotion/delivery 三入口共用 component/path validator，Ready formal manifest、closed nested schema、preliminary review與 reviewer identity 一致；Linux 證據若無執行環境維持 partial/insufficient。
- Slice order：ordinary POSIX → leaf/ancestor redirect → read/create race → formal_paths → closed page schema → Ready coverage → reviewer identity。
- Commands／完成證據：CMD-BDD-FOCUSED-002、CMD-BDD-FOCUSED-003、CMD-TDD-FOCUSED-001、CMD-PORTABILITY-WINDOWS-001、CMD-PORTABILITY-LINUX-001。

### WP-004 — P2 效能樣本與逐項結案

- 要求／結果：FR-006、FR-007、FR-008、NFR-003、AC-008、AC-009。
- Blocked by：WP-003。
- Intent：執行 benchmark 與 BDD-016/020，保存 readiness、五 cold、五 warm、functional hash、變動情境、fixture cleanup與環境；建立 16 份 bug-verification/v1，嚴格區分 verified/partial/failed。
- Slice order：benchmark readiness → sample collection → data mutation parity → Windows release → Linux release → status/verification/fresh review。
- Commands／完成證據：CMD-BDD-FOCUSED-004、CMD-BDD-FULL-001、CMD-PERFORMANCE-001、CMD-PORTABILITY-WINDOWS-001、CMD-PORTABILITY-LINUX-001、CMD-TEST-FULL-001。

## 6. 風險與追溯

| Risk | 觸發條件 | 影響 | Mitigation／決策點 |
|---|---|---|---|
| RISK-001 | commit/rollback 期間 target 被第三方改動 | approved 或競爭者資料遺失 | identity+bytes conditional rollback；若無法恢復則 RECOVERY_REQUIRED；Owner：WP-002 |
| RISK-002 | Linux 環境不可用或 path semantics 仍不一致 | 跨平台 BUG 只能部分驗證 | 保存 Windows evidence，明列 Linux command 與責任角色；不得宣告 verified；Owner：WP-003 |
| RISK-003 | benchmark 首次 process 啟動污染 timed sample | 冷啟動尾延遲誤判 | readiness 與正式 samples 明確分界，保留全部 raw samples；Owner：WP-004 |
| RISK-004 | assessment 與現行程式狀態不一致 | 歷史數量被誤當未解 BUG | status 只能依 current oracle + review evidence 重算；Owner：WP-001 |
| RISK-005 | schema/receipt/verification 漂移 | 無法追溯或錯誤結案 | validator、hash、artifact manifest與fresh reviewer四方綁定；Owner：WP-003/WP-004 |

### 追溯矩陣

| 來源／要求 | 模組／BDD／TEST | WP | 命令 |
|---|---|---|---|
| FR-001、FR-002、AC-001、AC-002 | MOD-003、BDD-BUG-001..016、TEST-BUG-001..016 | WP-001 | CMD-BDD-DISCOVERY-001、CMD-RELATED-001 |
| FR-003、AC-003、AC-004 | MOD-001、BDD-BUG-001..005、TEST-BUG-001..005 | WP-002 | CMD-BDD-FOCUSED-001、CMD-TDD-FOCUSED-001 |
| FR-004、FR-005、AC-005..007 | MOD-002、BDD-BUG-006..013、TEST-BUG-006..013 | WP-003 | CMD-BDD-FOCUSED-002/003、CMD-PORTABILITY-* |
| FR-006、AC-008、AC-009 | MOD-004、BDD-BUG-014..016、TEST-BUG-014..016 | WP-004 | CMD-BDD-FOCUSED-004、CMD-PERFORMANCE-001、CMD-TEST-FULL-001 |
| TR-001、AC-010 | all modules and full validators | WP-001..004 | CMD-BUILD-FULL-001、CMD-GOVERNANCE-001 |

## 7. Artifacts 與 readiness

Primary artifact 是 plan/plan.md；同一 revision bundle 的 handoff.json 是 machine contract。Plan 不會新增 knowledge page；Requirements promotion 已使用 no-change decision，planning promotion 同樣只發布 formal plan bundle 與 Ready receipt。

Readiness：
- 16 BUG rows、兩個 outcome assessment revisions、P0/P1/P2 priorities 與 owner/follow-up 已明列。
- 每一項都有 BDD、TEST、WP、command 與 verification result path 的 binding。
- 正式 sample 超標、平台缺口、回復衝突與證據不足都會保留，不以成功重跑覆蓋。
- handoff.json 使用 ready-plan/v1、完整 local/release validation plan、完整 command inventory、source/contract/WP symmetry、DAG 與 revision impact。
- 本計畫授權 implementation-execution 執行工作包，不授權 commit、merge、push、部署或改寫 assessment。

