<!-- authority: execution-ledger -->

# Preflight 與 Ledger 契約

本文件是共同 Ready binding、workspace capability、run identity、Ledger與baseline的唯一權威。任何 Ledger、產品或測試寫入前，必須已有 `implementation/active` stage authorization；Preflight唯一允許的產品外寫入是host-temp Ledger。Orchestrated delivery、resume/revision與greenfield各由條件reference擴充。

## Ready input

唯一合法輸入是 Technical Planning producer擁有的 [ready-plan/v1 contract](../../technical-planning/references/ready-plan-contract.md)與 [machine schema](../../technical-planning/references/ready-plan.schema.json)。直接讀取 handoff.json、Primary及每個supporting/source artifact：

1. Schema discriminator、Ready approval actor/time/evidence、Candidate revision與canonical payload digest成立。
2. 唯一Primary／handoff、全部artifact role/status/path/hash與handoff actual hash成立。
3. SRC kind/location/revision/hash、plan refs、direct WP refs與全部本地／URI source bytes成立。
4. Contract index涵蓋 BDD-FWK、適用BOOT、全部BDD／TEST／CMD／WP；cross-references完整、DAG無環。
5. 每個command具cwd、exact command、非秘密env前提、timeout、network、allowed writes、external side effects、success與completeness；Proposed有absence evidence，Observed的absence evidence為空。
6. 獨立bdd-discovery command可證明scenario inventory與contract mapping。
7. 若有`bug_context`：恰有一個`kind: bug` source，其assessment JSON／Markdown path與hash、bug ID、reproduction／root-cause狀態、regression refs、verification target及partial safeguards全部通過producer contract；沒有`bug_context`的舊Ready plan維持相容。

任一缺失、歧義、hash drift或矛盾為producer gap，結果是 Awaiting upstream reapproval且產品diff為零。

## Capability 與 Git workspace

保存command與raw output的host-temp refs並驗證：

1. Host能建立fresh、沒有實作歷史、唯讀、不得委派且能執行必要命令的Reviewer。
2. repo_id由canonical git common-dir推導；canonical_worktree精確匹配linked、non-primary worktree；HEAD attached，branch不是repository default或primary branch。
3. initial_base_sha = HEAD = handoff planning_baseline head_sha，repo_id相同。
4. 首次run的porcelain只含manifest列出且hash相同的Ready artifacts，以及通過 [Orchestrated Delivery Gate](orchestrated-delivery.md)後精確核准的requirements input；沒有 valid Delivery authorization 時不建立 run。歷史 standalone Ledger 與 Ready artifacts 只讀、不遷移、不刪除，也不授權續寫。
5. Git、runtime、compiler、runner、package manager與commands工具可用；Proposed dependency只驗證核准安裝前提。
6. Network與external side effects具有本次scope授權；未授權command不執行。

Terminal consumer只接受下列兩個exact ordered `capability_evidence_refs`形狀：legacy為`evidence/capability.json`、`evidence/capability/raw-reviewer.json`、`evidence/capability/raw-git-workspace.json`、`evidence/capability/raw-toolchain.json`；governed形狀只可在legacy尾端再加`evidence/capability/raw-delivery-authorization.json`。前者保留既有三項capability checks的原bytes，後者精確新增`delivery_authorization: passed`；除此以外的額外check、raw ref、改序或替代路徑都fail closed，且不遷移歷史Ledger。

Workspace、能力、工具或未記錄dirty state失敗為Blocked。嚴禁stash、reset、clean、覆寫、建立／切換／刪除worktree。

BUG Ready只額外允許`bug_context.assessment`精確列出的JSON／Markdown dirty paths；其他`docs/bugs/`內容（包含過早建立的verification或未綁定assessment）一律是未授權dirty path並Blocked。Standard Ready不允許任何BUG dirty path。

## Binding 與 run identity

Ledger root固定在host canonical temp provider的 implementation-execution，不接受repository scratch root。worktree_key是canonical_worktree UTF-8 bytes的SHA-256。

新run在階段授權與全部read-only checks通過後，以create-only binding directory取得排他權，立即保存 repo_id、canonical_worktree、worktree_key、branch、initial_base_sha與run_id。既有directory只可由 [Resume 與 Revision](resume-and-revision.md)驗證，且續寫前仍重驗階段授權；不完整、不可讀或mismatch不接管。

run_id是 repo_id、worktree_key、initial_base_sha、canonical handoff path與Candidate revision的canonical JSON SHA-256。Run directory固定為 host-temp/runs/run_id。任何binding／run初始化失敗停止，不宣稱取得workspace。

秘密不得進入manifest、命令列或Ledger。Executor在記憶體維持本次已知秘密值集合，每次保存Ready、delivery、Ledger或output record前，以consumer validator的`known_secret_values`做exact-value scan；集合與原值不持久化。Repository中的assessment與`bug-verification/v1`另須對stable-read raw JSON bytes在parse前掃描，拒絕duplicate object keys並核對parsed object，避免last-key-wins隱藏秘密。Raw output若含秘密，保存前只遮蔽該秘密值、保留其餘完整輸出並另記redaction event。每個WP開始／完成、global transition與snapshot前重算Ready／source hashes；任何drift立即進入[Resume與Revision](resume-and-revision.md)分支。

完成條件：binding與run identity可由raw probes重算，race只有directory winner有record。

## Ledger shape

[Execution records schema](execution-records.schema.json)擁有machine shape：

| 路徑 | 必要內容 |
|---|---|
| run.json | binding、base、revision／attempt／state與連續history |
| source-manifest.json | producer manifest、actual hashes與plan revisions |
| wp-ledger.json | DAG、WP states、BDD／TEST mapping與失效原因 |
| commands/sequence/ | command、cwd、env前提、時間、exit、完整stdout／stderr |
| evidence/ | baseline、bootstrap、red／green／refactor、coverage索引 |
| diffs/ | bootstrap、red前、WP完成、full verification與review snapshots |
| reviews/round/ | reviewer input、snapshot、raw response／outputs、report或invalid report |
| breaker.json | stable finding identity與counters |
| repository `docs/bugs/<bug-id>/verifications/<work-id>.json` | create-only `bug-verification/v1`；綁定Ready、assessment、原始症狀、regression／proxy red→green、full commands、殘餘風險與review ref |

WP states只用 Pending／Executing／Verified／Invalidated／Blocked；scenario outcome可用 Red／Green／Satisfied by existing implementation。Ledger append-only且不進review snapshot或repository artifact。

Validation runner 的 create-only bundle 保存在 Ledger evidence，或先寫入 handoff 核准的 ignored temporary root後完整匯入 Ledger。`validation-evidence/v1` index 綁定執行時 HEAD、binary diff、全部未忽略新檔、所有變更 Markdown、精確 command／child inventory、環境與 Ready payload；stdout／stderr、exit、duration、hash與 fixture profile由 runner 自動產生，Agent 不手工拼接或把引用結果冒充重跑。`validation_evidence.py render` 可由 Ready handoff 與已驗證 index重建 command、追溯與 evidence review Markdown。

長期保存使用 `validation_evidence.py archive export` 建立 deterministic、create-only `evidence-archive/v1`，再以 `archive verify` 重驗 manifest、每個檔案 hash與 run／repo／worktree identity。`archive import` 只匯入 quarantine root並回傳 `approval_inherited: false`；續跑前仍須 Delivery authorization、Ready／source／workspace preflight及Ledger連續性。Active run不自動刪除，Complete evidence至少保存30天；prune只能由明確命令觸發，且不得刪除目前 active、未驗證 archive 或唯一證據副本。

每個global state transition的`evidence_refs`至少含一個該transition專用且未被其他transition重用的`integrity/*ready-source.json`重算結果。Complete transition另作terminal index，精確列出`source-manifest.json`、`wp-ledger.json`、`breaker.json`、`commands/full-verification.json`及它宣告的每個`commands/sequence/` stdout／stderr、含canonical snapshot的`diffs/`、current review raw response、report宣告的每個`reviews/<round>/outputs/`與該report；每個Verified WP另列`integrity/<WP-ID>/start-ready-source.json`及`complete-ready-source.json`。另依序列出`terminal/01-review_received.json`至`terminal/06-snapshot_matched_after_persist.json`；每份物件固定含`sequence`、`step`與該步已保存的`evidence_refs`，Ledger的Complete transition本身就是第七步`complete_appended`。

Consumer validator以canonical run root逐一讀取上述bytes，也讀取Ledger宣告的capability／baseline refs。它要求main command index精確涵蓋Ready full commands且每項pass、stdout／stderr集合完整，current review raw output集合與report完全相等，source manifest／WP Ledger等於Ready／Complete attempt，snapshot ID等於review before／after，六個ordering witnesses內容及順序canonical；缺檔、redirect、重用ref或只有成功聲明都不成立。

Capability refs的第一項是`implementation-capability/v1`物件，綁定run ID、fresh Reviewer／Git workspace／toolchain三項passed checks及其後全部raw evidence refs；Baseline refs的第一項是`implementation-baseline/v1`物件，綁定run ID、`passed|not_applicable` outcome及其後全部raw evidence refs，兩者都至少有一份實體raw evidence。每份`integrity/*ready-source.json`是`implementation-integrity/v1`物件，含自身scope、attempt ID、transition sequence、canonical Ready SHA-256與依source ID排序的actual source hashes；validator以本次Ready重算比對，不接受任意文字或空JSON。

完成條件：每次state／evidence transition可復原寫入；寫入失敗時沒有成功聲明。

## Fresh baseline

Ready、workspace與binding通過後，按handoff command contract fresh執行全部適用Observed full build／test／BDD／governance baseline。Success／completeness、零failure／skipped、timeout、network、allowed writes與side effects全部成立，command後tracked與unignored content不變。

Proposed不宣稱執行；其absence evidence證明baseline不適用。Code-empty不豁免其他Observed commands。Producer誤標為Awaiting upstream reapproval；環境、工具或真實既有baseline failure為Blocked。

完成條件：所有適用baseline有raw evidence且結果可信，preflight zero-write gate仍成立，才可開始Executing。

## Portable v2 preflight

若 current state 是 `delivery-run/v2`，在任何產品或測試寫入前另驗證：task class 與
approval policy、repository／Work ID／worktree identity、current writer assignment、
single-writer lock、allowed path set、test／evidence commands、knowledge scope 及
finish destination。v2 runtime records 與 raw outputs 必須位於 repository 外的持久化
state root；目標 repository 不需要本 bundle 的 `.agents/skills` tree。

`read_only` 沒有 implementation authorization。`small` 必須具備一次 integrated
approval；`large`／bug 必須具備相應 Requirements／Planning／diagnosis evidence。缺少
assignment、fresh Reviewer capability、scope digest 或 state continuity 時維持零寫入，
回報 `awaiting_user`／`blocked`，不得把 v1 Ready plan 或主代理 prompt 當成 v2 授權。
v2 完成後的 knowledge review 與 Git finish handoff 只使用同一份 approved scope；v1
preflight、host-temp Ledger 與 capability evidence 不被遷移或改寫。
