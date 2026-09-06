# 技術規劃：人工核准 Gate 的 File-first + Summary-only Chat

- 狀態與核准證據：見 handoff.json.approval
- Candidate revision：candidate-20260905-gate-file-summary-chat-01
- 日期：2026-09-05
- 來源規格：docs/work/work-20260905-gate-file-summary-chat-cc5ef02c/requirements.md
- 範圍：統一所有需在 Chat 取得人類核准的 Gate；保留自動 validation／review／test／CI Gate
- Planning baseline：repo 0c5534020993ce0e527ffefdd0bbbdf8e3e26138d3933defe22de1ed5ea2530c；HEAD 6cf33bd5c0ef8a5658e3142ae1a6cc40d3c60de7；status 5a91e871cc09726a1a30b114ed8d2febecdfb35ee9107200f1bc58ee1a5bf45c
- Primary／handoff：docs/work/work-20260905-gate-file-summary-chat-cc5ef02c/plan/plan.md／docs/work/work-20260905-gate-file-summary-chat-cc5ef02c/plan/handoff.json

## 1. 成果、範圍與限制

交付一個共用且可測的人類 Gate review contract：完整 Candidate 先以不可變檔案封存並重驗，Chat只呈現摘要、直接連結、manifest identity與單一決策提示。既有 knowledge promotion與delivery phase machine繼續擔任 mutation authority。

- 範圍內：Project Knowledge seal／review／apply presentation；Requirements、Plan、BUG co-gate、bulk-edit map、Implementation後 Knowledge Gate；owner Skill／reference／validator／BDD／inner tests。
- 範圍外：產品功能、Git提交／merge／deploy、外部系統，以及自動 validation、fresh review、test、performance、security、lint、schema與CI輸出的縮減或改寫。

| ID | Required／Observed 限制 | SRC-* |
|---|---|---|
| CON-001 | Requirements、Plan與Knowledge是既有人工邊界；BUG assessment與occurrence map必須併入原Gate且只問一次。 | SRC-SPEC、SRC-EVIDENCE |
| CON-002 | 核准提示前只可產生隔離、unapproved、create-only review files；Ready／canonical／product／phase維持不變。 | SRC-SPEC |
| CON-003 | Approval須綁work／stage、current candidate ref、payload SHA、review manifest SHA與全部檔案；任何缺檔或drift都使舊核准失效。 | SRC-SPEC |
| CON-004 | Secret redaction、no-follow、path normalization、preimage、hash、duplicate-key、transaction與lint規則維持。 | SRC-SPEC、SRC-EVIDENCE |
| CON-005 | 歷史Ready與automatic evidence不migration；舊pending Candidate缺新sidecar時重新seal為新revision。 | SRC-SPEC |
| CON-006 | Bulk-edit分類的八個標準category全部有明確action；不存在的repo-local runtime不虛構驗證結果。 | SRC-OCCURRENCE、SRC-EVIDENCE |

## 2. 證據與變更影響

| SRC ID | Kind／location／revision | 事實 | Plan refs | 直接 WP refs |
|---|---|---|---|---|
| SRC-SPEC | spec／docs/work/work-20260905-gate-file-summary-chat-cc5ef02c/requirements.md／Ready-1 | Required：BR-001、FR-001..008、TR-001..002、NFR-001..003與AC-001..009定義完整Gate inventory及安全邊界。 | CON-001..005、TD-001..004 | WP-001..004 |
| SRC-EVIDENCE | supporting／docs/work/work-20260905-gate-file-summary-chat-cc5ef02c/plan/source-evidence.md／candidate-1 | Observed：sealed store已保存完整files；CLI仍回傳全文；owner contracts要求full Chat；baseline suite為green。 | CON-001、CON-004、CON-006、TD-001..003 | WP-001..004 |
| SRC-OCCURRENCE | governance／docs/work/work-20260905-gate-file-summary-chat-cc5ef02c/plan/occurrence_map.json／candidate-1 | Required：跨檔語意變更逐類處理，serialized／CLI／fixtures人工審查，imports與logs保持；本次JSON是現行trusted path guard下的self-hosting representation。 | CON-006、TD-004 | WP-001..004 |

### Current → target

目前 Candidate完整postimages雖已存在host-temp files，正常輸出仍把它們帶回Chat，且六個owner各自描述展示規則。目標把sealed files變成唯一完整審閱面，以一個versioned review index與shared authority投影所有人工Gate；Ready promotion與automatic gates的資料流不變。

| 影響 ID | 能力／Module | New／Modified／Removed／Preserved | 來源要求 |
|---|---|---|---|
| IMP-001 | Candidate registry | Modified：與candidate／postimages原子建立immutable review.json；不複製payload。 | FR-002、FR-004、FR-006、NFR-001 |
| IMP-002 | Human-facing CLI／Chat projection | Modified：candidate／bootstrap／lint與resume只回allowlisted摘要、links、manifest及identity；完整sentinel不逸出。 | FR-003、FR-008、NFR-002 |
| IMP-003 | Requirements／BUG／Planning composite Gate | Modified：Gate-specific檔案全部列入同一manifest，維持一次核准。 | FR-001、FR-007、AC-001、AC-002、AC-004 |
| IMP-004 | Knowledge／Delivery／Implementation Gate | Modified：進awaiting_user前重驗review sidecar；apply／transition仍由既有receipt與phase contract控制。 | FR-001、FR-004、FR-005、AC-003 |
| IMP-005 | Owner contracts與authoring doctrine | Modified：shared authority為single source of truth，各owner只保留inventory與context pointer。 | FR-001、NFR-002 |
| IMP-006 | Historical Ready與automatic Gates | Preserved：schema／raw evidence／ordering／pass-fail不做展示型migration。 | TR-001、TR-002、NFR-003 |

## 3. 設計與決策

| Context | Observed／Required | Proposed | SRC／TD |
|---|---|---|---|
| Runtime／dependency | Python 3.14.6、stdlib unittest；無網路與新dependency需求。 | 只用stdlib JSON／hash／path primitives。 | SRC-EVIDENCE／TD-001 |
| Data／identity | Candidate ref與payload SHA已是promotion authority。 | 新增human-gate-review/v1 sidecar與review SHA；candidate payload schema及receipt identity保留。 | SRC-SPEC、SRC-EVIDENCE／TD-001 |
| Path／security | Registry已採create-only、no-follow與hash驗證。 | Sidecar只接受candidate root內的normalized relative files；presentation才產生validated native links。 | SRC-SPEC／TD-001 |
| Skill governance | 展示規則分散在owner docs。 | project-knowledge/references/human-gate-review.md成為單一authority；owner以精確pointer套用。 | SRC-EVIDENCE／TD-002 |
| Compatibility | 歷史Ready不可重寫；pending需重建。 | Ready receipt維持；缺review sidecar的pending ref回LEGACY_RESEAL_REQUIRED。 | SRC-SPEC／TD-003 |
| Bulk edit | 同一Gate語意跨多檔但不同surface風險不同；現行Plan builder只接受Markdown／JSON。 | 本次依occurrence_map.json逐項分類；更新guard後未來bundle可使用occurrence_map.yaml，不做全域字串替換。 | SRC-OCCURRENCE／TD-004 |

### TD-001 — 在既有 sealed Candidate 上建立review projection

- 需求／證據：FR-002、FR-004、FR-006、FR-008、NFR-001；SRC-EVIDENCE。
- 選定方案與理由：重用既有 sealed Candidate 的 create-only postimage store，新增唯讀 review projection 與固定 Summary-only Chat contract；approval 仍綁 candidate ref 與 payload SHA，不新增第二套儲存或第三道 Gate。
- 真實替代方案／拒絕原因：把完整bundle另存worktree會在核准前污染正式artifact namespace；建立第二套store會產生雙重identity與drift；只在Chat給hash則不滿足直接審閱。
- Interface、資料、相容性、測試與營運影響：seal transaction新增create-only review.json；它列出Gate、work、candidate ref／payload SHA、prospective approval binding、每個target與stored file的SHA／bytes／role、validation與projection digest。Apply與resume先重讀candidate、sidecar及所有files；sidecar缺失代表legacy pending並要求新seal。歷史已套用receipt不回溯。

### TD-002 — Allowlist summary與single-source authority

- 需求／證據：FR-003、FR-007、NFR-002；writing-great-skills的single source of truth原則。
- 選定方案與理由：human-facing commands只輸出closed、versioned review projection；shared reference定義Chat七類欄位與唯一問題，各owner只宣告其bundle inventory及何時進Gate。
- 真實替代方案／拒絕原因：每個Skill各自複製模板會漂移；依payload大小截斷會使contract非deterministic；自由文字denylist無法證明sentinel不洩漏。
- Interface、資料、相容性、測試與營運影響：用allowlist serializer排除postimage／diff／raw output欄位；直接links指向immutable files。Behavior evaluator以大型fixture與唯一sentinel驗證輸出與payload大小無關。

### TD-003 — 以review SHA補強核准但保留既有promotion authority

- 需求／證據：FR-004、FR-005、TR-001、TR-002。
- 選定方案與理由：Chat同時顯示candidate ref、payload SHA與review SHA；新Candidate的apply／owner resume必須提交並重驗三者。Promotion receipt與delivery transition仍綁原candidate ref／payload／approval evidence，避免歷史schema migration。
- 真實替代方案／拒絕原因：修改所有歷史receipt與delivery records成本高且違反TR-001；不驗review SHA則無法封閉manifest被替換的窗口。
- Interface、資料、相容性、測試與營運影響：新Candidate強制review binding；old pending fail closed並以新evidence token產生不同revision；已Ready資料只走現有讀取相容分支。

### TD-004 — 語意分類取代機械式全面替換

- 需求／證據：CON-006、SRC-OCCURRENCE。
- 選定方案與理由：active human-facing contracts與tests按surface改寫；imports、logs、historical reports保持；serialized keys與CLI逐項審查。
- 真實替代方案／拒絕原因：全域replace會破壞machine schemas、歷史證據與automatic-gate output；完全不碰validators則無法防止未來回歸。
- Interface、資料、相容性、測試與營運影響：每個modified occurrence都能回指map category與WP；沒有path move。Planning formal-path validator加入yaml／yml supporting artifact但primary仍限定Markdown、handoff仍限定JSON；本次Candidate保留現行guard允許的JSON representation。

| MOD ID | 責任 | Caller-facing contract | SEAM／Adapter | 隱藏內容 | 要求 |
|---|---|---|---|---|---|
| MOD-001 | Candidate Review Registry | seal_for_review(repo,draft,binding) -> human-gate-review/v1；成功時files全存在且hash-valid，失敗零partial Candidate。 | SEAM-001／in-process | registry root、atomic temp／rename、postimage decoding | FR-002、FR-006、NFR-001 |
| MOD-002 | Review CLI／presentation | candidate、bootstrap、lint、review回closed summary；apply --review-sha256只接受current bytes。 | SEAM-001、SEAM-002／CLI adapter | native path formatting、sentinel filtering | FR-003、FR-004、FR-008 |
| MOD-003 | Human Gate authority | 定義Gate inventory、seven-field Chat summary、single prompt、drift／legacy處置；owners以pointer採用。 | SEAM-002／documentation contract | owner-specific artifact生成 | FR-001、FR-007、NFR-002 |
| MOD-004 | Cross-owner verification | BDD與owner validators證明全部human Gates採authority且automatic outputs不變。 | SEAM-003／test harness | fixture repos、mutation probes、report plumbing | AC-001..009、NFR-003 |

主要流程：owner形成完整draft → seal原子保存candidate／postimages／review index → review command重驗並回summary-only projection → Chat列出全部direct links與exact identity後只問一次 → explicit approval → apply以candidate／payload／review SHA重驗 → 現有receipt／lint／phase transition。任何file drift、missing、collision或legacy pending都留在原phase並建立新revision或Blocked。

## 4. 測試策略

| BDD-FWK ID | Observed／Proposed framework、版本與一手來源 | Test-only／安裝邊界 | Feature／binding／fixture | Discovery／report／zero-skip／CI |
|---|---|---|---|---|
| BDD-FWK-001 | Observed：Python 3.14.6 stdlib unittest＋test_behavior.py custom scenario registry；SRC-EVIDENCE。 | Test-only；不安裝dependency、不用network。 | .agents/skills/project-knowledge/scripts/test_behavior.py；binding同檔；.knowledge-test-tmp/。 | CMD-BDD-DISCOVERY-001列inventory；focused/full回JSON report；failed=0且skipped=0；CMD-TEST-FULL-001納入owner suites。 |

| SEAM ID | 可觀察 Interface | 替身策略 | 測試層 |
|---|---|---|---|
| SEAM-001 | seal／review／apply API與CLI JSON | 真實TemporaryDirectory registry及fixture Git repo；不mock filesystem safety。 | integration／contract |
| SEAM-002 | persisted review.json與allowlisted Chat projection | 唯一sentinel、large postimage、Windows-native direct path fixture。 | contract／behavior |
| SEAM-003 | owner pointers、Gate state與automatic evidence | mutation validators＋既有delivery／knowledge suites。 | governance／integration |

BOOT-*：不適用。Baseline已存在可載入的seal_candidate_draft、candidate registry、knowledge_cli.main與BDD runner（SRC-EVIDENCE）；第一個red可直接在SEAM-001形成正常assertion mismatch。

| BDD ID | 要求／scenario | SEAM／fixture | Oracle／正確 red | Feature／binding | Focused CMD | WP／order |
|---|---|---|---|---|---|---|
| BDD-021 | Sealing pending Candidate時，完整files與immutable review index先存在，projection精確列出Gate、manifest、validation及三重identity。 | SEAM-001／multi-file Candidate | Baseline無review.json／review SHA，assertion因目標behavior缺失而red。 | test_behavior.py／presentation scenario registry | CMD-BDD-FOCUSED-001 | WP-001／1 |
| BDD-022 | Candidate與review CLI對large payload只輸出allowlisted摘要及direct links，唯一sentinel與postimage全文皆不出現。 | SEAM-002／large sentinel | Baseline seal output含postimages與sentinel，negative assertion正確red。 | 同上 | CMD-BDD-FOCUSED-001 | WP-001／2 |
| BDD-023 | Requirements＋Knowledge＋BUG及Plan＋Knowledge＋occurrence map各為單一file-first Gate，manifest不漏檔且只一個prompt。 | SEAM-002／composite bundles | Active owner contracts仍要求full Chat或分散規則，contract evaluator red。 | 同上＋owner validators | CMD-BDD-FOCUSED-001 | WP-002／1 |
| BDD-024 | Standalone／bootstrap／repair及Implementation後Knowledge Gate可resume同一review，核准後才apply／Complete。 | SEAM-001、SEAM-003／delivery fixture | Baseline無review binding，awaiting-user precondition assertion red。 | 同上＋delivery tests | CMD-BDD-FOCUSED-001 | WP-003／1 |
| BDD-025 | Missing／drift／ambiguous approval／legacy pending全部fail closed；historical Ready與automatic raw evidence保持byte-compatible。 | SEAM-001..003／fault matrix | Baseline舊pending仍可直接apply，或projection drift未被綁定，assertion red。 | 同上＋full suites | CMD-BDD-FOCUSED-001 | WP-004／1 |

| TEST ID | BDD／風險 | 層級／SEAM／fixture | Oracle／red | Focused／related CMD |
|---|---|---|---|---|
| TEST-021 | BDD-021／partial persistence | integration／SEAM-001／fault-injected registry | sidecar與files原子、path/hash/bytes一致；baseline class不存在。 | CMD-TDD-FOCUSED-001／CMD-RELATED-001 |
| TEST-022 | BDD-022／payload leakage | unit＋contract／SEAM-002／large sentinel | closed schema keys；serialized result不含sentinel、postimages或raw output。 | CMD-TDD-FOCUSED-001／CMD-RELATED-001 |
| TEST-023 | BDD-023／composite omission或duplicate prompt | governance／SEAM-002／owner corpus mutation | 每個owner有shared pointer、exact inventory與one-prompt completion criterion。 | CMD-TDD-FOCUSED-001／CMD-RELATED-001 |
| TEST-024 | BDD-024／resume與phase bypass | integration／SEAM-001、SEAM-003／delivery records | awaiting_user前review valid；approval後相同triple才套用；其他零mutation。 | CMD-TDD-FOCUSED-001／CMD-RELATED-001 |
| TEST-025 | BDD-025／相容與automatic regression | regression／SEAM-003／legacy Ready、old pending、raw evidence snapshots | Ready hashes不變、pending回re-seal、全部owner/full suites與raw evidence contract green。 | CMD-TDD-FOCUSED-001／CMD-TEST-FULL-001 |

| CMD ID | Purpose | Observed／Proposed | 摘要；完整 contract 在 handoff.json |
|---|---|---|---|
| CMD-BDD-DISCOVERY-001 | bdd-discovery | Observed | Baseline 19 scenarios；變更後包含BDD-021..025且不執行body。 |
| CMD-BDD-FOCUSED-001 | bdd-focused | Proposed | 新presentation group；先取得五個正確red，再逐scenario green。 |
| CMD-BDD-FULL-001 | bdd-full | Observed | 全部Knowledge BDD，failed=0、skipped=0。 |
| CMD-TDD-FOCUSED-001 | tdd-focused | Proposed | 新HumanGateReviewTests逐測試red→green。 |
| CMD-RELATED-001 | related | Observed | Baseline related suite已green，變更後仍含全部owner validators。 |
| CMD-BUILD-FULL-001 | build-full | Observed | 全repo syntax／schema owner inventory。 |
| CMD-TEST-FULL-001 | test-full | Observed | Knowledge＋Requirements＋Planning＋Implementation＋BUG＋Delivery全量。 |
| CMD-GOVERNANCE-001 | governance | Observed | Knowledge provenance、approval、structure及staged worktree lint。 |

順序：各WP依目前BDD取得正確red → 映射TEST red／minimal green／refactor-with-green → focused BDD與related green；同一WP scenario green後才開始下一個。全部WP完成後fresh執行full build、BDD、test及governance commands。

## 5. 工作包

### WP-001 — Immutable review bundle與summary projection

- 要求／結果／impact：FR-002..006、FR-008、NFR-001..002；IMP-001、IMP-002。
- Blocked by：None。
- Consumes／produces：既有knowledge-candidate/v1 → versioned review sidecar、review SHA、summary-only CLI與apply revalidation。
- Intent：在Project Knowledge registry transaction內加入review index；採closed allowlist，不改canonical promotion payload。
- Slice order：BDD-021→TEST-021；BDD-022→TEST-022。
- Commands／完成證據：全部八個CMD符合handoff criteria。

### WP-002 — Requirements／BUG／Plan複合Gate

- 要求／結果／impact：FR-001、FR-003、FR-007、AC-001、AC-002、AC-004；IMP-003、IMP-005。
- Blocked by：WP-001。
- Consumes／produces：shared human-Gate authority＋review projection → 三種composite inventory、one-prompt owner contracts與occurrence-map分類。
- Intent：建立單一authority；Requirements、Planning、BUG及bulk-edit只保留stage-specific清單、pointer與completion criterion。
- Slice order：BDD-023→TEST-023。
- Commands／完成證據：全部八個CMD；owner mutation validators能刪除任一pointer／bundle item／single-prompt規則而正確失敗。

### WP-003 — Knowledge／Delivery／Implementation整合

- 要求／結果／impact：FR-001、FR-004..005、FR-008、AC-003；IMP-004、IMP-005。
- Blocked by：WP-001。
- Consumes／produces：review binding → standalone、bootstrap、repair、post-Implementation Gate的resume／apply／phase前置條件。
- Intent：在現有receipt與delivery transition外層增加review precondition；不新增人工Gate或改變automatic review authority。
- Slice order：BDD-024→TEST-024。
- Commands／完成證據：全部八個CMD；knowledge/awaiting_user與Complete fault matrix fail closed。

### WP-004 — 相容、drift與全域回歸

- 要求／結果／impact：TR-001..002、NFR-003、AC-005..009；IMP-006。
- Blocked by：WP-002、WP-003。
- Consumes／produces：前三包contracts → legacy pending re-seal、historical Ready preservation、large-payload與automatic evidence回歸。
- Intent：以forward evaluator及full suites證明「只改人工presentation」；清理temporary fixtures並確認occurrence-map compliance。
- Slice order：BDD-025→TEST-025。
- Commands／完成證據：全部八個CMD fresh green；Git diff逐項分類且無historical／logs／automatic output drift。

## 6. 風險與追溯

### 風險與取捨

| Risk ID | 觸發條件 | 影響 | Mitigation／驗證 | Owner／決策點 |
|---|---|---|---|---|
| RISK-001 | review sidecar與Candidate files非原子或未綁定 | 人類核准錯誤manifest | 同registry transaction、review SHA、apply前全量重讀與fault tests | WP-001 |
| RISK-002 | absolute link越界、symlink或host path失效 | 洩漏／不可審閱 | persisted relative path＋candidate-root no-follow驗證；presentation才產生native path；失敗Blocked | WP-001 |
| RISK-003 | formatter依payload大小截斷或自由文字帶出sentinel | Summary-only失效 | closed allowlist schema、large sentinel negative assertions | WP-001、WP-004 |
| RISK-004 | shared contract在owner間複製 | 未來Gate漂移 | 單一authority＋owner pointer mutation tests | WP-002、WP-003 |
| RISK-005 | legacy migration回寫歷史Ready | audit bytes改變 | 只拒絕old pending；historical Ready／receipts snapshot regression | WP-004 |
| RISK-006 | 全域字串替換改動machine output | automatic Gate相容破壞 | 八類occurrence map、semantic diff review與full suites | WP-002、WP-004 |

### 追溯矩陣

| SRC／要求 | TD／MOD／SEAM | BDD | TEST | WP | CMD／證據 |
|---|---|---|---|---|---|
| SRC-SPEC／FR-002、FR-004、FR-006、NFR-001 | TD-001、MOD-001、SEAM-001 | BDD-021 | TEST-021 | WP-001 | focused／related／governance |
| SRC-SPEC／FR-003、NFR-002、AC-009 | TD-002、MOD-002、SEAM-002 | BDD-022 | TEST-022 | WP-001 | focused／full BDD |
| SRC-SPEC／FR-001、FR-007、AC-001／002／004 | TD-002、TD-004、MOD-003、SEAM-002 | BDD-023 | TEST-023 | WP-002 | focused／owner validators |
| SRC-SPEC／FR-001、FR-005、FR-008、AC-003 | TD-003、MOD-003、SEAM-003 | BDD-024 | TEST-024 | WP-003 | related／delivery |
| SRC-SPEC／TR-001／002、NFR-003、AC-005..009 | TD-003、TD-004、MOD-004、SEAM-003 | BDD-025 | TEST-025 | WP-004 | build／test／governance |
| SRC-OCCURRENCE／CON-006 | TD-004、MOD-004 | BDD-023、BDD-025 | TEST-023、TEST-025 | WP-002、WP-004 | diff classification＋full suite |

## 7. Artifacts 與 readiness

### Artifact manifest

完整role／approval_status／SHA-256 manifest以handoff.json為權威；本節只提供閱讀索引。

| Path | Role | 建立理由 | 權威內容 |
|---|---|---|---|
| docs/work/work-20260905-gate-file-summary-chat-cc5ef02c/plan/plan.md | primary | 主入口 | 設計、測試、WP與追溯 |
| docs/work/work-20260905-gate-file-summary-chat-cc5ef02c/plan/source-evidence.md | supporting | 將暫態查證materialize | baseline、source hashes、absence evidence |
| docs/work/work-20260905-gate-file-summary-chat-cc5ef02c/plan/occurrence_map.json | supporting | Bulk-edit guardrail；self-hosting path-compatible representation | 八類action、exceptions與no-move決策；未來Gate支援YAML |
| docs/work/work-20260905-gate-file-summary-chat-cc5ef02c/plan/handoff.json | handoff | versioned machine handoff | ready-plan/v1 data、commands、DAG與hashes |

### Readiness

- 缺口／未知／衝突：無；repo-local occurrence schema不存在已明確記錄，分類artifact仍完整。
- BDD framework／BOOT／BDD／TDD／WP／commands：完整；BOOT有observed不適用證據。
- handoff.json schema、payload digest、artifact hashes與cross-references：Candidate seal前由producer validator通過。
- 品質門檻：範圍、design、interfaces、failure／recovery、security、compatibility、test order、DAG及traceability完整。
- 核准狀態與寫入證據：見handoff.json.approval；本次self-hosting Gate仍依舊契約完整展示，核准前repository零Plan寫入。
