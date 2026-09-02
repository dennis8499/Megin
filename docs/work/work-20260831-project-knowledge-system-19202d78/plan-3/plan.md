# 技術計畫 Revision 3：單一專案可信工程知識系統

## 0. 身分、狀態與取代關係

- Work ID：`work-20260831-project-knowledge-system-19202d78`
- Candidate revision：`candidate-20260901-03`
- 狀態：`Candidate—Awaiting confirmation`
- Planning baseline：HEAD `5ddfe8a73560dd6754b00aa6ce45a333449c4f32`；repository ID `0c5534020993ce0e527ffefdd0bbbdf8e3e26138d3933defe22de1ed5ea2530c`；status SHA-256 `3162fa0e8d65110c06a47e530fb42839e7499bf76d2e9c4bf0b4887eb58d9e6c`
- Primary／handoff：`docs/work/work-20260831-project-knowledge-system-19202d78/plan-3/plan.md`／`docs/work/work-20260831-project-knowledge-system-19202d78/plan-3/handoff.json`
- 取代：核准後取代 `candidate-20260831-02`；舊 plan bundles 保留為歷史證據，不覆寫。
- 唯一 current 來源規格：`docs/work/work-20260831-project-knowledge-system-19202d78/requirements-2.md`，SHA-256 `f950021657a8a5a39e3571075840d1f0e35c3f64729fca11a0affd99e1769589`。
- 現有 `plan/source-evidence.md` 維持 supporting source，SHA-256 `12559af63c890d0c188fb1fb91fa9e683f52da8beb56a7eadc7c7a5832429c04`。

本 revision 採納 2026-09-01 已核准的範圍修訂：本版 release support 與 evidence 只涵蓋 Windows、Linux，macOS 明確排除。`requirements.md` 與 `requirements-2.md` 的行為差異只涉及範圍敘述、`NFR-002`、`AC-016`、`KPI-005`、`D-015`；查詢、治理、promotion、Outcome、review、安全與其餘 acceptance 均未改。然而 Ready handoff 必須以唯一 `kind: spec` source 綁定目前 `requirements-2.md`；更新後的 `SRC-REQ` 直接支配 WP-001～004，亦被 full commands 使用，因此依 fail-closed revision contract 屬於 `global-baseline`。既有 implementation run 保持 `Awaiting upstream reapproval`，下一 generation 必須重驗全部四個 WP，不能把舊 Verified evidence 當成新 baseline。

## 1. 不變的需求與架構

### 1.1 產品結果

建立 repository-local `project-knowledge` skill：以 Git-eligible raw files 為證據、`docs/knowledge/**/*.md` 為導航 Wiki、JSON sidecars 為 provenance/lifecycle contract、Git 為正式歷史；host-temp registry 只保存 sealed Candidate、journal、backup 與 review evidence。公開 CLI 提供 `query | bootstrap | lint | candidate | apply | recover`，不引入資料庫或 production 第三方 dependency。

### 1.2 權威與核准

1. Wiki 不取代 raw source；formal producer 必須重讀 `source_refs` 的 hash、locator 與 excerpt。
2. Requirements／planning 只在 exact full-postimage Candidate 被明確核准後共同 promotion；一般「繼續」不等於 knowledge approval。
3. Implementation／BUG 先保存 physically-bound preliminary fresh review，再 create-only 寫 Outcome，封存 knowledge Candidate，交給另一位 fresh final reviewer；只有 exact Candidate 另獲人工核准後才 apply。
4. 不執行 `git add/commit/push/merge`，不刪 worktree，不自動解決 contested claims。
5. Windows／Linux 兩份真實 portability reports 缺一即維持 release Blocked；macOS report 不屬於本版 release evidence，也不以單一 Windows PASS 冒充跨平台完成。

### 1.3 核心資料與安全不變量

- Closed contracts：`knowledge-page/v1`、`knowledge-context/v1`、`knowledge-candidate-draft/v1`、`knowledge-candidate/v1`、`knowledge-promotion/v1`、`knowledge-journal/v1`、`knowledge-lint/v1`、`implementation-outcome/v1`、`knowledge-snapshot/v1`。
- Query 最多五筆、canonical-first、deterministic ranking；stale／contested／superseded／redirected／ignored／hash-drifted／self-referential evidence 永不注入。
- Candidate 只含 normalized create/update full postimages；secret-like values、path traversal、hardlink／reparse redirects、preimage/source drift 全部 fail closed。
- Promotion receipt 最後寫入；failure rollback，process-death journal 必須 recover 後才可重試。
- Product snapshot 唯一排除 `docs/knowledge/**`；knowledge snapshot 另綁完整 eligible pre-tree、sealed operations 與 expected post-tree。

## 2. 保留的 Revision 2 修正與 Revision 3 平台差異

Revision 2 已核准並實作的四項 correctness 修正全部保留，不因平台範圍縮減而回退：

| Fix | Required behavior | Red／green owner evidence | Contract mapping |
|---|---|---|---|
| REV2-001 | `revision == base_sha` 的非 materialized local source，在 admission、resume、new generation、terminal snapshot 都以 `git cat-file blob <base>:<path>` raw bytes 驗 SHA-256；requirements／supporting／handoff 等 materialized artifact 才驗目前 bytes。 | delivery safety：合法 target diff 不得使 snapshot/source preflight失敗；錯誤 raw hash必須拒絕。 | BDD-007／TEST-007、BDD-008／TEST-008 |
| REV2-002 | Technical Planning owner validator 對每個 source 要求至少一個 direct `bdd-scenario`、一個 direct `inner-test`，且各自與 source 共享 direct WP；review coverage 不得借用別的 source IDs。 | 移除任一 direct BDD/TEST/WP mapping 時 validator red；完整 fixture green。 | BDD-007／TEST-007 |
| REV2-003 | Cache hit 回傳前重讀 selected canonical sidecar raw hash，再驗 content、source hash、locator、excerpt；sidecar `current→stale` race 回 `SOURCE_DRIFT`。 | `test_cache_hit_rejects_sidecar_drift_before_return` red→green。 | BDD-004／TEST-004 |
| REV2-004 | Apply 取得 repository promotion lock 後重新驗 finalizers、source snapshot、operations、stage semantics、receipt absence與preimages；任何其間 create/update race 在 journal與repo writes前回 `PREIMAGE_DRIFT`並保留 concurrent bytes。 | `test_apply_revalidates_preimages_after_operation_validation` red→green。 | BDD-013／TEST-013 |

Raw base manifest normalization（完整值在 handoff）：`.gitignore`、`_delivery_record.py`、`_delivery_runtime.py`、requirements workflow、implementation workflow、BUG contract、skill guide 改用 raw blob SHA-256。`delivery-run.schema.json`、ready-plan schema、execution schema原本已是 raw hash。新增 `SRC-PLANNING-VALIDATOR` 綁 technical-planning cross-reference consumer。

Direct coverage corrections：

- `SRC-GITIGNORE` → BDD-017／TEST-017／WP-004。
- `SRC-DELIVERY-RECORD` → BDD-007／TEST-007 與 BDD-008／TEST-008／WP-003。
- `SRC-IMPLEMENTATION-CONTRACT` → BDD-008／TEST-008／WP-003。
- `SRC-SKILL-GUIDE` → BDD-003／TEST-003／WP-001。
- `SRC-PLANNING-VALIDATOR` → BDD-007／TEST-007／WP-003。

### 2.1 Revision 3 的局部變更

| Change | Observed current state | Proposed target／oracle | Contract mapping |
|---|---|---|---|
| REV3-001 | `compare_portability_reports.py` 的 `REQUIRED_OSES` 為 Windows、macOS、Linux；`test_workflow.py` 建立三份報告；CI matrix 含 `macos-latest`。 | `REQUIRED_OSES` 只含 Windows、Linux；BDD／TEST 要求兩份真實報告 functional SHA 相同、50,000 files／5,000 pages、六個 timed operations 各 ≤2 秒，缺 Windows 或 Linux 任一份即 fail；CI 移除 macOS job。 | NFR-002／AC-016／KPI-005／D-015／BDD-016／TEST-016／CMD-PORTABILITY-001／WP-004 |
| REV3-002 | Skill 說明、測試名稱與 workflow step 仍使用「三平台」語意。 | 將 release-facing 說明改為 Windows／Linux；保留跨 OS 正規化與安全行為，不增加其他平台承諾。 | TD-010／IMP-010／WP-004 |

`SRC-REQ` 更新為唯一 current spec source，location／revision／hash 精確綁定 `requirements-2.md`；舊 `requirements.md` 只保留為 repository history，不再是 handoff 的規範來源。即使語義差異集中在 BDD-016／TEST-016／WP-004，source identity、full-command ownership 與 delivery current-requirements binding 仍使 revision impact closure 為 WP-001～004。

## 3. 模組、SEAM 與操作流程

| MOD | 責任 | 主要 SEAM | 產出／邊界 |
|---|---|---|---|
| MOD-001 | skill routing／stage policy | SEAM-001 CLI | query/bootstrap/lint/candidate/apply/recover，branch完成條件明確。 |
| MOD-002 | contracts／repo safety | SEAM-002 filesystem+Git | closed schema、normalized path、stable read、raw-base/materialized hash分流、secret/redirect。 |
| MOD-003 | retrieval | SEAM-003 real `rg` adapter | deterministic Top-5、canonical sidecar+content+provenance final snapshot。 |
| MOD-004 | bootstrap/lint/promotion | SEAM-004 fault injector | sealed Candidate、full lint、lock內重驗、journal/rollback/recover。 |
| MOD-005 | SDLC stage integration | SEAM-005 artifact staging | requirements/planning同核准 co-promotion，四stage read-only preflight。 |
| MOD-006 | delivery overlay | SEAM-006 delivery record | additive knowledge state、revision-aware source/snapshot、legacy compatibility。 |
| MOD-007 | outcome/reviews | SEAM-006 + review registry | preliminary/final fresh reviews、Outcome、dual snapshots。 |
| MOD-008 | migration/release | SEAM-002/003 | `.gitignore` exceptions、initial Candidate、golden/benchmark、Windows／Linux reports與two-report comparator。 |

流程：`stage intent → read-only query → raw citation verification → formal Candidate → semantic knowledge draft → sealed Candidate/full display → exact human approval → lock-held transactional apply → full lint → workflow transition`。

## 4. BDD／TDD 契約

沿用 stdlib `unittest` scenario registry、17個 BDD、17個 TEST；0 skip才算 green。每個 scenario 必須先有目標行為缺失造成的 assertion red，再以 mapped inner TEST 驅動 minimal green，最後 focused＋related green。Revision 3 只改變 BDD-016／TEST-016 的 oracle；其餘 16 個 scenario 的 oracle 不變，但 global-baseline generation 仍須依 WP 順序重播全部 17 個 scenario：

| BDD／TEST | Oracle 與修正後責任 | WP／focused command |
|---|---|---|
| BDD-001／TEST-001 | trusted bootstrap只分類terminal；核准前tree不變。 | WP-002／CMD-BDD-FOCUSED-002 |
| BDD-002／TEST-002 | requirements查詢≤5且有可重驗raw refs。 | WP-001／CMD-BDD-FOCUSED-001 |
| BDD-003／TEST-003 | requirements/planning/implementation/BUG四skill preflight；skill guide direct ownership。 | WP-001／CMD-BDD-FOCUSED-001 |
| BDD-004／TEST-004 | ad-hoc query zero-write；cache hit後source或sidecar drift均在return前失敗。 | WP-001／CMD-BDD-FOCUSED-001 |
| BDD-005／TEST-005 | 20題Top-5≥18、citation 100%、0 ineligible。 | WP-001／CMD-BDD-FOCUSED-001 |
| BDD-006／TEST-006 | requirements與knowledge使用同approval atomic promotion。 | WP-003／CMD-BDD-FOCUSED-003 |
| BDD-007／TEST-007 | complete Ready-plan bundle co-promotion；raw-base/materialized source分流與每-source direct BDD/TEST/WP validator。 | WP-003／CMD-BDD-FOCUSED-003 |
| BDD-008／TEST-008 | post-review completion gate；terminal snapshot按revision重建source，Outcome與dual snapshots完整。 | WP-003／CMD-BDD-FOCUSED-004 |
| BDD-009／TEST-009 | legacy狀態衝突進contested quarantine，0 current claim。 | WP-002／CMD-BDD-FOCUSED-002 |
| BDD-010／TEST-010 | verified BUG incident含 symptom/root cause/fix/regression refs。 | WP-003／CMD-BDD-FOCUSED-004 |
| BDD-011／TEST-011 | partial BUG保留不確定性且禁止確定修復語。 | WP-003／CMD-BDD-FOCUSED-004 |
| BDD-012／TEST-012 | stale source query排除、lint stable diagnostic＋repair Candidate。 | WP-002／CMD-BDD-FOCUSED-002 |
| BDD-013／TEST-013 | source/preimage/lock-window race零提交、保留concurrent bytes、可重試。 | WP-002／CMD-BDD-FOCUSED-003 |
| BDD-014／TEST-014 | valid contradictions雙方保留但不注入，decision required。 | WP-002／CMD-BDD-FOCUSED-002 |
| BDD-015／TEST-015 | provenance/link/orphan/ID/index/log/lifecycle/conflict完整lint。 | WP-002／CMD-BDD-FOCUSED-002 |
| BDD-016／TEST-016 | Windows與Linux各以50k files/5k pages執行五queries＋Candidate rebuild，各 operation≤2秒；兩份 functional SHA一致，缺任一required OS即fail，macOS不列為required report。 | WP-004／CMD-BDD-FOCUSED-004＋CMD-PORTABILITY-001 |
| BDD-017／TEST-017 | ignored/secret/traversal/redirect/hardlink/fault/Git-action防護；`.gitignore` direct ownership。 | WP-002+WP-004／CMD-BDD-FOCUSED-003 |

Handoff 共15個 command contracts：原14個BOOT、BDD discovery、4 focused BDD、full BDD、3 focused TDD、related、build-full、test-full、governance全部不改；新增 Proposed `CMD-PORTABILITY-001`，對準備好的 Windows／Linux真實reports執行 comparator。每個 command 的 cwd、timeout、network、allowed writes、success/completeness及absence evidence以 handoff 為權威。

## 5. 工作包、revision 與續接

| WP | Scope | Blocked by | Revision 3 disposition |
|---|---|---|---|
| WP-001 | read-only query、ranking、citation、stage hooks | — | Invalidated；下一 generation 重播 retrieval、citation 與 stage-hook contracts。 |
| WP-002 | lifecycle、lint、conflict、promotion/recovery/security | WP-001 | Invalidated；下一 generation 重播 lifecycle、transaction、recovery 與 security matrix。 |
| WP-003 | co-gates、Ready validator、Outcome/review/delivery overlay/BUG | WP-002 | Invalidated；下一 generation 重播 co-gates、validators、Outcome與delivery contracts。 |
| WP-004 | Git migration、initial Candidate、full/release evidence | WP-003 | Invalidated；改寫 two-platform oracle，並以 Windows／Linux 真實 reports 重驗。 |

核准後處理順序：

1. create-only 寫入本 bundle，將 handoff 僅更新為 `Ready` metadata，重驗 payload與artifacts。
2. 既有 implementation attempt 追加 `Awaiting upstream reapproval` evidence；delivery 建立 generation 4／new implementation run，execution base 仍為核准的 HEAD。
3. 新 generation 不把舊 diff 當成已驗證成果；可把它當唯讀參考，但必須依 WP-001→004 順序重新取得 outside-in red、mapped TEST red→green、focused＋related green。
4. WP-004 讓更新後的 BDD-016／TEST-016 在三平台 comparator／tests／CI 的舊行為上取得正確 red，再最小修改 comparator、owner tests、skill文字與CI matrix。
5. fresh 執行 build-full、test-full、BDD full、governance與 `CMD-PORTABILITY-001`；Windows／Linux真實reports必須 functional SHA一致且每項≤2秒。
6. 所有WP回到Verified後才交給未參與實作的fresh reviewer；review通過且終態契約完成後方可關閉。

## 6. 風險、追溯與完成條件

| Risk | Mitigation／blocking evidence |
|---|---|
| Source hash因CRLF/filters分裂 | 所有base-revision source只用raw blob；materialized artifact另驗current bytes；admission/resume/snapshot同一規則。 |
| Cache result與lifecycle metadata非同一快照 | selected canonical sidecar/content/source final stable re-read；任一hash/locator/excerpt drift即SOURCE_DRIFT。 |
| Promotion覆寫核准後併發內容 | lock後重驗＋pre-journal preimage assertion；race fixture必須保留concurrent bytes與零receipt。 |
| Reviewer coverage可借用別的source | producer validator與review validator共同要求direct source↔BDD↔TEST↔WP ownership。 |
| 語義差異局部卻錯誤沿用舊evidence | `SRC-REQ`是唯一current spec且直接支配全部WP；revision明列global-baseline，orchestrator建立新generation／run，舊evidence只作診斷參考。 |
| 50k/5k效能回歸 | clean standalone benchmark；setup不計時，每個operation≤2秒，不用平均掩蓋。 |
| portability evidence不完整 | Windows／Linux兩份真實reports與comparator；缺任一required OS、functional SHA不同或任一operation>2秒都禁止release-complete聲明。 |

Readiness checklist：`requirements-2.md` hash已重驗；requirements byte diff只含metadata與platform scope clauses；`SRC-REQ`為唯一current spec source；schema與cross-reference validator PASS；revision impact為global-baseline且精確列出WP-001～004；17/17 BDD、17/17 TEST、4 WP、15 commands完整；paths `plan-3/plan.md`、`plan-3/handoff.json` 尚未存在；approval仍為Candidate。只有使用者看到本plan與完整handoff bytes並明確核准後才可寫入。
