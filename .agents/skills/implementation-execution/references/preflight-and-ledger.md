<!-- authority: execution-ledger -->

# Preflight 與 Ledger 契約

本文件是 workspace、Ready binding、run identity、baseline、resume 與 revision 的唯一權威。任何產品／測試寫入前完整讀取；Preflight 期間唯一允許的寫入是 host temp Ledger。

## 1. 鎖定執行輸入

唯一合法輸入是 Technical Planning producer 擁有的 [`ready-plan/v1`](../../technical-planning/references/ready-plan-contract.md)，其 machine shape 由 [`ready-plan.schema.json`](../../technical-planning/references/ready-plan.schema.json)定義。讀取原始 `handoff.json`、Primary 與每個 supporting/source artifact，不使用摘要替代。

依序驗證：

1. `schema: ready-plan/v1`、`approval.status: Ready`、actor／time／evidence、Candidate revision 與 canonical payload digest。
2. Manifest 唯一 primary／handoff、全部 artifact paths／roles／statuses／hashes，以及 handoff 實際 hash。
3. `SRC-*` kind／location／revision／hash、plan refs 與 direct WP refs；所有本地來源重算 hash，URI revision 仍可取得且 bytes 相同。
4. Contract index 涵蓋 `BDD-FWK-*`、適用 `BOOT-*`、全部 `BDD-*`／`TEST-*`／`CMD-*`／`WP-*`；cross-references 完整，WP DAG 無環。Code-empty source 必須在 Primary 中完整滿足 producer-owned Ready contract 的 `BOOT-*` 語義；任一欄位放寬或缺失都在 Preflight 停止。
5. 每個 command 具有 cwd、精確命令、非秘密 environment prerequisites、timeout、network policy、allowed ignored／temp writes、external side effects、success／completeness criteria；Proposed command 有不存在證據，Observed command 的該陣列為空。
6. 有獨立 `bdd-discovery` command，且 plan 的 scenario inventory 與 contract mapping 可由其輸出判定。

任一缺失、歧義、hash drift 或矛盾都是 producer contract 缺口，進入 `Awaiting upstream reapproval`，產品 diff 保持為零。無版本／版本不支援的舊 Ready plan 走重新規劃、完整展示與重新核准。

## 2. 能力與 Git 邊界

保存每項 probe 的 command 與 raw output，並驗證：

1. 宿主能建立 fresh、無實作歷史、唯讀、不得委派且能執行必要命令的 Reviewer；否則 `Blocked`。
2. Git 可用。解析 `git rev-parse --path-format=absolute --git-common-dir` 的 symlink／case、正規化 `/` 後取 UTF-8 SHA-256 得 `repo_id`；`canonical_worktree` 是同樣 canonical 化的 absolute toplevel。Artifact 只保存 repo ID，absolute common-dir path 只留 host-temp probe evidence。目前 root 必須精確匹配 `git worktree list --porcelain` 的 linked、非 primary worktree；branch attached，且不同於治理或 remote HEAD 所識別的 repository default branch，也不同於 primary worktree 的 attached branch。
3. `initial_base_sha = HEAD = handoff.planning_baseline.head_sha`，`repo_id` 也與 handoff 相同。無可證明差異進入 `Awaiting upstream reapproval`。
4. 首次 run 的 porcelain v2／untracked 狀態只可包含 handoff manifest 所列且 hash 相同的 Ready artifacts；產品、測試、設定及其他檔案均 clean。唯一額外例外是下述「Orchestrated requirements gate」。Resume 只接受最後 Ledger snapshot 中 hash 相同的 executor-owned changes。
5. Git、runtime、compiler、runner、package manager 與 commands 所需工具可用。Observed BDD runner 現在可用；Proposed 內建 framework 執行核准的 availability probe，需額外安裝者只驗證核准的安裝前提，兩者都不在 Preflight 修改 manifest。
6. 每個 command 的 network／外部副作用已有本次請求範圍內的授權；未授權副作用進入 `Blocked`，不執行命令。

任一 workspace、工具、能力或未記錄 dirty state 失敗進入 `Blocked`。唯一允許的處理是保存證據並停止；不 stash、reset、clean、覆寫、建立／切換／刪除 worktree。

### Orchestrated requirements gate

Standalone execution 不使用此例外，原 manifest-only 規則完全不變。只有全部條件同時成立時，首次 run 可把一個 requirements 檔視為額外的唯讀 upstream input：

1. 使用者或上游明示提供 host-temp run record；它完整符合 [`delivery-run/v1`](../../delivery-orchestrator/references/delivery-run.schema.json)，不是 repository 內檔案，且 status／phase 精確為 `active/implementation`。
2. Record 的 `repo_id`、current generation `canonical_worktree`／`worktree_key`／attached branch／base SHA 與本次 execution probes、binding 及 `handoff.planning_baseline` 全部相同；generation 為 `ready`。不由 branch 名、相似 path 或 Work ID 猜測 record。
3. 唯一例外 path 精確等於 record 的 current Ready requirements revision，形狀只能是 `docs/work/<work_id>/requirements.md` 或最小 `requirements-N.md`；Work ID 與 record、artifact root、current plan path 均一致。該 revision 具有非空且已遮蔽的 approval evidence refs，實際 bytes SHA-256 與 record 相同。
4. Current handoff 精確等於 record 的 current Ready plan revision；其 `approval.evidence` 存在於 record 的 plan approval refs，且 `sources` 恰有一個 `kind: spec` source，其 repository-relative `location` 與 `sha256` 分別等於 current requirements path 與實際 hash。重新計算 Candidate payload digest與全部既有 Ready/source hashes仍通過。
5. 該 path 不是產品、測試、設定、dependency manifest／lockfile或 command allowed-write。Porcelain 中除原 manifest Ready artifacts與這一個 requirements path之外仍為空；requirements 在 Preflight、execution及 review 全程不可修改。

任一 record 欄位、核准 evidence、Work ID、workspace、branch、base、path、source kind、SHA 或 current ref 缺失／不符，就不套用例外並以未記錄 dirty path進入 `Blocked`。Record 與 probe 只寫 host-temp Ledger evidence；不把 absolute path 加入 repository artifacts。

## 3. Binding 與 run identity

Ledger root 固定為 host canonical temp provider 下的 `implementation-execution/`，不接受 repository 內 scratch root。對 `canonical_worktree` 的 UTF-8 bytes 做 SHA-256 得 `worktree_key`。

Resume 先讀 `<root>/bindings/<worktree_key>/binding.json`，由 record 取得 `run_id` 與 `initial_base_sha`，不從目前 plan 或 HEAD 猜測 Ledger。新 run 在所有 read-only Git／Ready checks 通過後，以「建立不存在的 binding directory」取得排他權：

1. 原子建立 `<root>/bindings/<worktree_key>/`；同時只有一個 caller 成功。
2. 勝者立即以可復原寫入 `binding.json = {repo_id, canonical_worktree, worktree_key, branch, initial_base_sha, run_id}`。
3. Directory 已存在時只可 resume 完整且相符的 record；不完整、無法讀取、不同 repo／worktree 或另一 run 均為 `Blocked`。不接管、不覆寫、不依 terminal state 回收 binding。

新 `run_id` 為下列 UTF-8 canonical JSON 的 SHA-256 全 64 位：`repo_id`、`worktree_key`、`initial_base_sha`、canonical handoff path、Candidate revision。Canonical handoff path 由 `canonical_worktree` 與 manifest 中已正規化的 repository-relative path 組合，再使用相同 symlink／case／`/` 規則解析。Run directory 固定為 `<root>/runs/<run_id>/`。Binding 寫入或 run directory 初始化失敗時停止，不宣稱已取得 workspace。

秘密不進入 manifest、命令列或 Ledger；raw output 若含秘密，只遮蔽該值並另記遮蔽事件。每個 WP 開始／完成、global transition 與 snapshot 前重算 Ready/source hashes；drift 立即走 revision 分支。

## 4. Ledger 位置與結構

使用[execution records schema](execution-records.schema.json)保存：

| 路徑／紀錄 | 必要內容 |
|---|---|
| `run.json` | `implementation-ledger/v1`、binding、initial base、目前 revision／attempt／state、連續 state history 與能力／baseline evidence refs |
| `source-manifest.json` | Producer manifest、實際 hashes 與每次 plan revision |
| `wp-ledger.json` | DAG、狀態、BDD／TEST 映射、失效原因；WP 狀態只用 `Pending／Executing／Verified／Invalidated／Blocked`，scenario outcome 可用 `Red／Green／Satisfied by existing implementation` |
| `commands/<sequence>/` | command、cwd、非秘密環境前提、開始／結束時間、exit code、完整 stdout／stderr |
| `evidence/` | baseline、受限 bootstrap、red／green／refactor、coverage 與完成證據索引 |
| `diffs/` | bootstrap 前後、每個 red 前、WP 完成、full verification 與 review snapshot |
| `reviews/<round>/` | reviewer input manifest、snapshot、raw output logical refs、原始 `implementation-review/v1` report 或 invalid report |
| `breaker.json` | finding identity、連續未解輪數與無進展輪數 |

每次狀態或證據變更以可復原方式更新；失敗時停止，不宣稱已保存。Ledger 是執行狀態，不是 Ready artifact，不提交，也不進 review snapshot。

## 5. Baseline 與狀態

首次執行在 Ready、workspace 與 binding 通過後，按 handoff command contract fresh 執行全部適用 `Observed` full build、full test、full BDD 與治理 baseline。每項須符合 success／completeness、零 failure／skipped、timeout、network、allowed writes 與 side-effect contract；命令後 tracked 與 unignored content 不變。

`Proposed` command 不宣稱執行；其 absence evidence 必須證明為何 baseline 不適用。Code-empty 不豁免 repository 其他 Observed commands。本應存在卻失敗或被誤標 Proposed 是 producer gap；環境、工具或真實既有 baseline failure 是 `Blocked`。

Preflight 全部通過前，產品、測試、dependency manifest 與 lockfile 保持不變。執行狀態與終止順序只由[交付協定](delivery-protocol.md)管理。

## 6. Resume 與計畫 revision

Resume 由 binding 找到 run，驗證 initial base、Ready/source hashes、目前 Git 狀態與最後 snapshot。保留首次 baseline，不在含 executor changes 的 workspace 重建它；依 Ledger 最後合法 state 重跑下一個 required command。連續性不可證明時 `Blocked`。

Ready/source hash 改變時先終止目前 attempt 為 `Awaiting upstream reapproval`。沒有新 Ready approval 時只計算 provisional impact，不改 WP／evidence／breaker。取得新核准後：

- `revision_impact` 全部為 `wp-local`、planning `head_sha` 等於 `initial_base_sha`，且 changed sources／contracts 完全落在宣告 impact 時，可在同一 run 追加 attempt。直接 affected WP 與其 DAG downstream 轉 `Invalidated`；保留舊 evidence／review 為 `superseded`，未受影響 WP 只有在 source、input contract、snapshot 與 evidence 都相同時保留 `Verified`。從最早 invalidated WP 以 `Invalidated → Executing → Verified` 續跑。
- 任一變更涉及 `BDD-FWK-*`、Observed baseline、全域 command、跨 WP contract，impact 無法證明完整，或 planning base 改變時，分類為 `global-baseline`；目前 run 保持 `Awaiting upstream reapproval`，由外部建立新專用 worktree／base／run。
- `Complete` run 永遠凍結；任何 revision 都使用新 worktree／base／run。

Finding counter 只有其 source obligation／required outcome 被新 revision 實質取代時標 `superseded`；其餘延續。所有舊 revision、attempt、evidence 與 binding record只追加、不覆寫或刪除。
