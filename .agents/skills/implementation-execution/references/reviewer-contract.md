<!-- authority: execution-review -->

# Reviewer 契約

本文件是 canonical snapshot、fresh Reviewer、`implementation-review/v1` 與 breaker 的唯一權威。所有 WP 完成後讀取；Reviewer 只接受原始 artifacts、內容與 outputs，不接受主代理結論作為證據。

## 1. 主代理的全量驗證與 snapshot

從乾淨的命令程序、plan 指定的工作目錄與非秘密環境前提，依序新鮮執行：

1. 完整 build／compile command；
2. 完整 test command；
3. BDD full-suite command；
4. plan 與治理列出的 lint、format-check、typecheck、security、codegen consistency 或其他 required commands。

每項依 handoff success／completeness 判定 `passed`，包含 exit 0、零 failure、零 skipped 與完整 discovery；runner 不提供計數時以 raw output 或 machine result 證明 inventory。任何 failure 依[執行迴圈](bdd-tdd-loop.md)走 `Verifying → Fixing`，尚未建立 review snapshot。

全量通過後依 [execution records schema](execution-records.schema.json)建立 `implementation-snapshot/v1`：

1. 固定 `repo_id`、`worktree_key`、`base_sha`、`head_sha`。
2. Ready artifacts（含實際 handoff hash）按 normalized ref 排序；sources 按 `SRC-*` 排序並重算 SHA-256。
3. 以 `git diff --binary --full-index --no-ext-diff --no-textconv <base_sha> --` 取得 base 至工作樹的原始 tracked bytes，禁止 external diff與textconv driver，SHA-256 寫入 `tracked_diff_sha256`。
4. 以 `git ls-files --others --exclude-standard -z` 取得全部未忽略新檔；path 正規化為 `/`、依 Git path bytes 排序，逐檔雜湊原始 bytes。Snapshot 前清除 command contract 要求清除的 temporary outputs；只排除 Ledger、timestamps 與 handoff 明列的 allowed ignored build outputs。
5. 對不含 `snapshot_id` 的 object 使用 UTF-8（無 BOM）、object keys 字典序、arrays 依上述 ref/path 排序、`/` 分隔符、無額外 whitespace 或尾端 newline的 JSON：等價於 `ensure_ascii=false, sort_keys=true, separators=(",", ":")`。其 SHA-256 為 `snapshot_id`。

Snapshot 本身不含 timestamp、Ledger path、review round 或 command output location。相同內容必須重算出相同 ID；任何 reviewed byte drift 使該輪失效並回 `Verifying`。

## 2. Fresh read-only Reviewer

每輪只啟動一個全新 subagent，並要求其 report attestation 可驗證：

- `implementation_conversation_received: false`：不帶實作對話、主代理推理、辯護、預期 verdict 或前一位 Reviewer 的未驗證結論；原始 Ledger evidence 仍是下一項所需的審查輸入；
- 直接取得原始 source manifest、artifacts、plan revision、base SHA、完整 repository snapshot、Ledger evidence 與 raw command outputs；
- 唯讀檢視 source 與 reviewed files，不使用任何編輯工具、不安裝 dependency、不 commit／push／merge／deploy／清理或改變外部狀態；
- 不再啟動 subagents；
- 可執行 plan 的驗證命令；命令只可產生 plan 已允許且被忽略的 build／test artifacts 或 host-temp 輸出。若命令會改變 tracked／未忽略內容，回報 `BLOCKED`；
- 命令前後自行重算 snapshot，證明 reviewed bytes 未改變。

Attestation 的 `write_actions: false` 表示 Reviewer 沒有直接編輯或未宣告寫入；驗證命令產生且僅產生 contract 允許的 ignored／host-temp outputs 不視為 Reviewer 寫入責任，仍須在 command outcome 與 snapshot probes 中揭露。

不得只交付 diff 摘要或主代理整理的選段。Reviewer 應自行讀取完整 tracked diff、所有未忽略新檔及原始來源。

Reviewer 沒有 Ledger 寫入責任：所有 command raw output、logical refs 與原始 JSON report 只透過回覆傳回，主代理原樣保存。回覆與 report 不重現秘密值；若 command 意外輸出已知秘密，Reviewer 在回覆前只替換該精確值並附 redaction event，主代理把這份已遮蔽的原始回覆原樣保存。Fresh Reviewer 先依 sources、snapshot 與 commands 完成自己的 outcomes、coverage、findings draft，再讀 prior reports 只核對 finding transition；舊 reports 保留，不複製其 verdict。

## 3. 獨立驗證面向

Reviewer 必須自行重跑全量 build、test、BDD 與治理命令，並獨立檢查：

- 每項規格需求與驗收的實作、BDD、TDD 與 WP 完成證據；
- 邊界、失敗、復原、相容、安全、隱私與適用品質限制；
- oracle 是否獨立且真的執行，沒有 skip、弱化 assertion、假 green 或只驗證 implementation detail；
- 每個 production behavior change 是否都有正確 red，既有已滿足情境是否沒有無依據擴張；若第一個 greenfield red 前存在 production shape，逐 bytes 核對它只符合已核准 `BOOT-*`、sentinel 與所有驗收結果互斥、bootstrap command 未執行 behavior，且後續 behavior diff 才由 red 驅動；
- plan 決策、Module／Interface／Seam、依賴版本、CI 與 scope 是否一致；
- 無關檔案、Ready artifacts、秘密、Git 與外部狀態是否保持邊界。

正確性、規格忠實度、安全、資料完整性、測試缺口、破壞性相容問題及會造成驗證不可信的缺陷都是實質 finding。純命名／格式偏好或無需求依據的替代寫法是非 blocking advisory。

## 4. `implementation-review/v1`

原始 report 必須符合 [execution records schema](execution-records.schema.json) 的 `reviewReport`：verdict、snapshot-before／after、Reviewer attestation、獨立 command outcomes、raw-output logical refs、逐一對應 `SRC-*`／`plan_refs` 的 requirement coverage、findings 與 summary 均完整。

Command outcome 語義：

- `passed`：命令執行且 success／completeness 全部成立；exit、failure、skip 為實際整數。
- `failed`：命令執行但任一判定失敗；可取得的 counts 為整數，不可取得者為 `null`。
- `blocked`：命令已啟動，但因環境、權限、side-effect 或可靠性阻塞而無法完成可信判定；不可取得欄位為 `null`。
- `not_run`：命令未啟動；無論原因是前置能力／權限不成立、外部取消或其他可定位事件，counts 與 exit 均為 `null`，`not_run_reason` 必填。`blocked` 或 `not_run` 都不能支持 APPROVED。

每個已執行command outcome使用不同且非空的raw output ref；`raw_output_refs`自身也不得重複。共用同一output或只改路徑不能冒充多個獨立command證據。

Finding 的 `blocking` 是 JSON boolean；`false` 可表達 advisory。`finding_key` 是 `key_inputs = {category, sorted unique source_refs, sorted unique affected_loci, normalized required_outcome}` 的 canonical JSON SHA-256，沿用第 1 節 UTF-8／sorted keys／compact separators 規則：`category` 另轉小寫，所有文字 trim 並將連續 whitespace 壓成一格，path 分隔符轉為 `/`；duplicate normalized refs直接拒絕，不能藉重複元素改key。`affected_loci` 只用穩定 path＋symbol／test／contract ID，不含 line number 或 diff hunk；每輪可變的精確 lines、diffs、tests 與 outputs 放在 `evidence_refs`。Reviewer 自己的 `finding_id` 可變，key 不因措辭、行號或 round 改變。

Verdict 只依下列分支：

- `APPROVED`：全部 required commands `passed`；每個covered obligation都有非空BDD、TEST、WP與code evidence，且BDD／TEST contract與WP都直接擁有同一`source_ref`，不得借用另一來源的有效ID；snapshot-before 等於 snapshot-after，且沒有 `blocking: true` finding。
- `CHANGES_REQUIRED`：snapshot 可審，且至少一個可由目前執行範圍修正的 blocking finding；advisory 可同時存在。
- `BLOCKED`：來源、能力、環境、snapshot 或上游決策使可靠判定不可完成。主代理依原始證據分流至 `Awaiting upstream reapproval` 或 `Blocked`。

## 5. 修正輪迴與進展式熔斷

主代理逐項驗證 finding，不可因不同意就省略。實質 finding 依 BDD／TDD 契約修正；advisory 只記錄。每次修正後完整重跑主代理驗證，建立新 snapshot，再啟動另一個全新 Reviewer。

Ledger 以 `finding_key` 保存每輪原始 ID、alias 與 transition。只有 key inputs 實質改變才是不同 finding；改寫 ID／message 不重置計數：

- 同一 blocking finding 在三份連續 report 中仍未達 required outcome：`Blocked`。
- Review round 1 只建立 blocking baseline，no-progress streak 初始化為 0，不算一次無進展。
- 從 round 2 起，每一輪只與前一份 report 比較；若同時沒有 blocking finding 數量下降、沒有既有 blocking finding 轉為 resolved、也沒有足以改變判定的全新 command／test／diff／source-decision 證據，no-progress streak 加 1，否則歸零。
- 每輪必要的新`output_ref`只是傳輸位置，不是進展；validator只比較passed command、covered obligation、code evidence與來源決策等語義結果。
- no-progress streak 到 2（即兩次連續 report-to-report transition 都無進展）：`Blocked`。
- 新 finding 不自動代表進展；必須仍依上述三項判斷。
- 舊key消失但由新blocking key等量取代時，只有伴隨全新語義證據才算進展；A→B→C無證據輪換持續累積global no-progress。

resolved transition 必須有新命令、測試、diff 或來源決策證據。到達熔斷時保存 counters、所有 reports 與最後 snapshot，停止修改並依交付協定回報。

`breaker.json`只保存latest blocking keys；validator以round 1起連續保存的reports重算trailing unresolved與no-progress counters。`last_evidence_sha256`是latest report中該key的round、snapshot、key inputs、finding evidence、command outcomes與coverage之canonical JSON SHA-256；缺report chain、round缺口、key集合或digest不一致都不可作熔斷證據。

## 6. Accepted 與 invalid report

Report 只有在 schema／attestation 合法，`snapshot_before`／`snapshot_after` 等於送審 ID，且主代理重算目前 snapshot 相同時才具 accepted 資格。任一 snapshot 不同時，原始回覆只保存為 `invalid-snapshot` evidence，不成為 accepted report。

主代理原樣保存 Reviewer response／outputs，Reviewer 不取得寫入工具或責任。保存前後的重算、state transition 與 `Complete` append 順序只由[交付協定](delivery-protocol.md)管理；pre-review evidence 維持 append-only。
