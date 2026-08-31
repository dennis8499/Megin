<!-- authority: bug-assessment -->

# `bug-assessment/v1` 契約

本文件擁有 BUG ID、assessment files、schema semantics、create-only materialization 與安全邊界。Machine shape 由 [JSON Schema](assessment.schema.json)定義。

## Identity 與位置

合法 `bug_id` 是 7–64 字元 lowercase ASCII kebab-case，固定以 `bug-` 開頭。使用者提供合法且未占用 ID 時優先；否則由二至五個症狀 topic words 產生 `bug-<kebab-topic>`。已占用時依序嘗試 `-2`、`-3`，使用最小可用後綴，不覆寫或重用既有 directory。

每個 revision 使用最小正整數 `N`：

| Artifact | Repository-relative path |
|---|---|
| 人類 assessment | `docs/bugs/<bug-id>/assessment-N.md` |
| Machine sidecar | `docs/bugs/<bug-id>/assessment-N.json` |
| BUG verification | `docs/bugs/<bug-id>/verifications/<work-id>.json` |

所有檔案與目錄 entry create-only。任一路徑在核准／materialize 間被占用時，整組不寫；重新配置下一個 revision 或 ID，完整展示並依既有 gate 重新綁定。

## Read-only diagnosis 與 writer ownership

`bug-diagnosis` 只在對話或 host-temp evidence 形成 Candidate，不寫 repository。

- 開案：delivery／requirements writer 在第一道既有核准中一起展示 assessment Markdown、JSON sidecar 與 Requirements；核准後以同一次 transition materialize並保存兩個 hashes。
- 途中 current-scope／affecting：Implementation writer先保存host-temp diagnosis；需要上游改變時在 handoff 前 materialize並轉 reapproval。
- 途中 unrelated：不得修改其產品；先以host-temp create-only全域inbox保存遮蔽refs，再於fresh review或任何terminal handoff前materialize repository assessment。

Assessment 是 evidence。Requirements 是 observed／expected、影響、範圍與驗收的唯一 WHAT 權威；Ready plan 是 root-cause／修法／regression seam／verification target的唯一 HOW 權威。

## Hash 與 binding

Sidecar 的 `markdown.path` 必須精確等於同 `bug_id`／revision 的 Markdown path；`markdown.sha256` 是實際 UTF-8 file bytes SHA-256。Validator 另外取得 sidecar 自身 path，要求它同樣符合 revision。Consumer 必須對 stable no-follow 取得的 raw JSON bytes 在 parse 前做 secret scan，並拒絕任何層級的 duplicate JSON object key；不得讓 parser 的 last-key-wins 語義隱藏已持久化的秘密。任何 mismatch、symlink／reparse redirect、path traversal、collision 或已存在 target 都 fail closed。

來源 work 使用合法 `work_id` 或 `null`；entry relation 是 `intake`。途中 relation只能是 `current-scope | affecting-current-work | unrelated`。Evidence refs 是不含秘密的 logical refs，不冒充原始輸出。

## Verdict 與 disposition

| Verdict | 合法 disposition |
|---|---|
| `confirmed`／`likely` | `delivery | current-run | upstream-reapproval | deferred-inbox`，依 relation 限縮 |
| `not-a-bug` | `standard-feature | closed` |
| `insufficient-evidence` | `blocked | deferred-inbox | upstream-reapproval` |

`confirmed` 表示存在可觀察 BUG，不必然表示 root cause confirmed。Root cause不是 `confirmed` 時需要 3–5 個可否證 hypotheses；同時最多一個 `testing`，且 `active_hypothesis_id` 必須與它一致。一次只測一個 variable。

## 敏感 evidence

`security_privacy_or_data_risk: true` 時，repository 只保存遮蔽摘要、secure evidence refs 與非空的具名人工審查責任；不得保存 token、credential、完整敏感 payload 或可還原秘密的值。Consumer 同時拒絕credential-shaped assignment／sentinel／known token格式，並以本次記憶體中的 `known_secret_values` 做 exact-value scan；delivery CLI只接受`--known-secret-env`名稱並在process內解析，原值、集合與環境變數名稱皆不寫入record。

Critical／high severity 不改上述規則，也不繞過 Requirements、Plan、regression、full verification或fresh review。

## Completion

Machine sidecar的raw bytes與parsed object共同通過 duplicate-key、schema、cross-field、path/hash、create-only與secret scan；人類 Markdown 符合模板且不與 sidecar 矛盾；writer 保存 binding refs 後才可交接。Diagnosis-only回覆不宣稱已寫入。
