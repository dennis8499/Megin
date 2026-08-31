<!-- authority: ready-plan -->

# `ready-plan/v1` 交接契約

本文件是 Technical Planning producer 與 Implementation Execution consumer 之間的唯一 handoff 權威。[JSON Schema](ready-plan.schema.json)定義可機器檢查的形狀；本文件定義欄位語義、生命週期與跨欄位不變量。

## Bundle 與版本

每份 Candidate 與 Ready bundle 都包含：

- 一份 `role: primary` 的 `plan.md`。
- 零至多份因維護者、驗證方式或生命週期不同而拆出的 `role: supporting` artifacts。
- 一份固定名為 `handoff.json`、`role: handoff` 的 artifact。

`handoff.json.schema` 固定為 `ready-plan/v1`。consumer 只接受明確支援的版本；無版本、版本不支援或缺少 handoff 的舊計畫，唯一交接路由是重新規劃、完整展示與重新核准。

Artifact 只使用兩個正交欄位：

- `role`: `primary | supporting | handoff`
- `approval_status`: `Candidate | Ready`

`Required artifact`、`Proposed artifact` 或其他混合生命週期與角色的名稱不是本契約狀態。

## Candidate 與核准身分

`candidate.revision` 是每次完整展示都更新的不透明 revision。`candidate.payload_sha256` 綁定使用者看過的全部 handoff 語義與 primary／supporting hashes，且可在 Ready metadata 更新後重現。計算方式是深拷貝完整 handoff object，移除 `candidate.payload_sha256`，將 `approval` 正規化為 Candidate 的 `status` 與三個 `null` 身分欄位，並將所有 `artifacts[].approval_status` 正規化為 `Candidate`；再以 UTF-8、排序 object keys、無多餘空白、已正規化為 `/` 的 paths 且保留 handoff array 順序做 SHA-256。任何 source、contract、command、DAG、impact 或 artifact path／role／hash 改變都會改變 digest。

`handoff.json` 的 manifest self hash 固定為 `null`，避免遞迴；consumer 直接雜湊實際 handoff bytes，另用上述正規化重算 approval payload digest。

Candidate 的 `approval.status` 與所有 artifact `approval_status` 均為 `Candidate`，actor、time、evidence 為 `null`。明確核准後只允許：

1. 將 `approval.status` 與全部 artifact `approval_status` 改為 `Ready`。
2. 寫入 `approval.actor`、RFC 3339 `confirmed_at` 與能定位原始核准回覆的 `evidence`。

Primary／supporting bytes、revision、payload digest、paths 與其 hashes 保持等同使用者看過的 Candidate。任何其他變更都建立新 revision、重算 digest、重新展示並重新核准。

## Planning baseline 與 artifacts

`planning_baseline` 保存規劃查證時的 Git 身分：

- `repo_id`：解析 `git rev-parse --path-format=absolute --git-common-dir` 的 symlink／case、將分隔符正規化為 `/`，再對 UTF-8 path 做 SHA-256；artifact 不保存本機 absolute path。
- `head_sha`：規劃所依據的完整 commit SHA；沒有可證明的 Git baseline 時不能 Ready。
- `status_sha256`：以路徑排序的 porcelain v1 `-z` bytes 做 SHA-256，用來揭露查證時的 tracked／untracked 狀態，不取代 `head_sha` binding。

`primary_plan` 必須指向 artifact manifest 中唯一的 `primary` 項目，path 與 SHA-256 相同。Manifest 列出整個 bundle；每個 primary／supporting hash 必須等於寫入 bytes。所有本地 path 都以 `/` 分隔並受限於 canonical worktree：使用 repository-relative segments，只有 command `cwd` 可為 `.`，且不含 absolute／drive path、空 segment、`.`／`..` traversal；只有 `allowed_writes` 可保留尾端 `/`。consumer 的 execution base SHA 必須等於 `planning_baseline.head_sha`，否則進入 `Awaiting upstream reapproval`，零產品變更。

## `SRC-*` source manifest

每個會限制設計、驗收、命令或工作包的輸入建立一個 `SRC-*`：

- `kind`：`spec | governance | adr | project | platform | contract | supporting`。
- `location`：專案相對 path 或穩定 URI；本地路徑使用 `/`。
- `revision`：commit、版本、日期或其他穩定 revision。
- `sha256`：規劃實際引用內容的 SHA-256；URI 來源先保存或取得精確 response bytes 才能 Ready。
- `plan_refs`：該來源支持的需求、AC、`TD-*`、`BDD-FWK-*` 或其他 plan IDs。
- `wp_refs`：直接受其限制的 `WP-*`，不可只經 plan 間接推導。

對話、暫態 tool response、需原 session 權限或其他 consumer 無法獨立重取的來源，先把使用者看過的精確內容 materialize 為 bundle 內 `role: supporting` artifact，`location` 指向其 repository-relative path，且 `SRC-*`.sha256 等於該 artifact 的 manifest hash；原 channel／URI 只作 provenance，不冒充可重取 location。Implementation 重新雜湊所有本地來源並驗證可重取 URI 的 revision／bytes。缺失、無法讀取或 hash 不同即停止 Preflight。

## Contract index 與工作包

`contract_index` 是所有執行契約的單一索引。每項包含 ID、kind、直接 `SRC-*` refs 與直接 `WP-*` refs。保留既有識別碼族：

- `BDD-FWK-*`：framework、discovery、reporting 與零 skipped 契約。
- `BOOT-*`：完全 code-empty 時的行為中立 seam bootstrap；Primary 中固定精確 paths／signature／最小 host wiring、fixture 可捕捉且不逸出為 runtime error 的 deterministic sentinel、與全部驗收 oracle 互斥證據、禁止行為、bootstrap command 及第一個 BDD／WP 映射。可載入 seam 已存在時不建立，並以 source evidence 證明不適用。
- `BDD-*`：outside-in scenario、fixture、oracle 與正確 red。
- `TEST-*`：目前 scenario 的 inner TDD 驅動。
- `CMD-*`：可執行命令。
- `WP-*`：依賴排序的垂直工作包。

每個 contract 都至少有一個 source 與 WP mapping。每個 `WP-*` 在 `work_packages` 重列其 `blocked_by`、consumed contract、source 與 command refs。`blocked_by` 必須只引用現有 WP、不可自引且構成 DAG。

`revision_impact.changes` 對每個可重新核准的變更記錄：

- `scope: wp-local`：只改變列出的 WP contracts，列出完整 `affected_wp_refs`。
- `scope: global-baseline`：改變 `BDD-FWK-*`、Observed baseline、全域 command、跨 WP interface 或其來源；影響所有未完成與已完成 WP。

未能證明為 `wp-local` 的變更一律是 `global-baseline`。

`wp-local.affected_wp_refs` 的可重算規則是：先由 changed `SRC-*`／contract／plan ref 的直接 mappings 取得 seed，再沿 `blocked_by` DAG 加入全部 downstream closure；宣告集合至少等於該 closure。遺漏 direct 或 downstream WP 是 producer gap。

## Command contract

每個 `CMD-*` 固定包含：

- `purpose`、`status: Observed | Proposed`、canonical `cwd`、可直接執行的精確 `command` 與不含秘密值的 `environment_prerequisites`。
- 正整數 `timeout_seconds` 與 `network_policy: forbidden | optional | required`。
- `allowed_writes`：只列命令可建立的 ignored 或 temporary paths、類型與清理責任；空陣列代表不得寫入。
- `external_side_effects`：目標、效果、可逆性與既有授權；空陣列代表無外部副作用。
- 分開的 `success_criteria` 與 `completeness_criteria`；測試命令的完整性必須能判定 discovery、failure 與 skipped 數量。
- `absence_evidence`：只有 `Proposed` 命令需要，記錄已執行的 probe、結果與 `SRC-*`，證明 command／script／manifest entry 目前不存在；Observed 命令固定為空陣列。

Bundle 必須包含獨立的 `purpose: bdd-discovery` 命令；它只列出／發現 BDD scenarios，不以執行 full suite 代替。需要額外安裝的 Proposed framework 另有 `bdd-install`；由 target runtime 內建者以一手 source evidence 記錄「無獨立安裝」及其 availability probe。其餘依適用性包含 focused BDD、full BDD、focused TDD、related、full build、full test、治理、CI 及 `BOOT-*` 命令。

## Consumer 不變量

## Conditional `bug_context`

Standard plan省略`bug_context`，也不得使用`kind: bug` source或`purpose: bug-reproduction` command。Bug plan三者同時存在，且唯一bug source的location／SHA精確等於`bug_context.assessment.path`／`sha256`；JSON／Markdown paths必須屬於同一`bug_id`與revision。Assessment revision只能是無前導零的正整數`[1-9][0-9]*`，bug source的`revision`必須精確等於path中的`N`；`0`、`00`或`01`一律拒絕。

`regression_bdd_refs`與`regression_test_refs`必須指向由同一bug source直接擁有的BDD／TEST contracts。`original_reproduction_command_ref`若非null，必須指向`bug-reproduction` command。

- `verification_target: verified`要求`reproduction_status`為`reproduced | intermittent`、original reproduction command非null，partial safeguards全部為空。
- `verification_target: partial`要求root cause不是confirmed high-confidence，且`reason`、非空proxy BDD／TEST refs、residual risks與follow-up完整。`reason`必須明示無法重現／不確定／低信心，逐項residual risk必須含不確定性或風險語意，逐項follow-up必須是明確的驗證動作；任何`conclusive`、`remediated`、`validated`或中英文等價的確定修復宣稱皆fail closed。Proxy refs同樣直接屬於bug source。

`partial`只核准低信心交付分支，不代表症狀已驗證修復；consumer必須另外產生`bug-verification/v1`。

## Consumer 不變量

Implementation Preflight 在任何產品寫入前驗證：

1. JSON Schema、版本與本文件跨欄位不變量。
2. Ready 核准身分、Candidate digest、artifact 與 source hashes。
3. Primary path、全部 ID／cross-reference、WP DAG 與 revision impact map。
4. execution base SHA 與 planning baseline 相同。
5. 每個必要 command 的 cwd、timeout、network、允許寫入、外部副作用、成功／完整性及 Proposed absence evidence 完整。
6. BDD discovery 命令存在，且其輸出可建立預期 scenario inventory。

任一項失敗時唯一狀態是 `Awaiting upstream reapproval` 或無法取得必要證據時的 `Blocked`；產品 diff 保持為零。
