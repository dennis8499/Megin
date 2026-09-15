<!-- authority: delivery-run -->

# Workspace 與 Run 契約

本文件是 repository-local legacy path 的 `work_id` identity、host-temp registry、
`delivery-run/v1`、resume 與 record continuity 的唯一權威。Portable `delivery-run/v2`
state 的欄位與 lifecycle 由 [v2 任務分級與核准契約](v2-task-routing.md)補充；New
work／generation 的 Git mutation 仍由 [Workspace 建立契約](workspace-creation.md)擁有。
所有人工 Gate 的呈現遵循 `.agents/skills/project-knowledge/references/human-gate-review.md`；本文件只擁有 phase／record binding，不另定 Chat payload 規則。

## Identity 與固定位置

合法 `work_id` 為 3–64 字元 lowercase ASCII kebab-case，無空 segment，且不是 Windows reserved device name；建立後不可改名。未提供 ID 時，以初始落地請求 UTF-8 SHA-256、`repo_id`、exact base SHA 與二至五個 ASCII topic words 產生：

`work-YYYYMMDD-<topic>-<canonical-input-sha256 前八碼>`

Record 只保存 request digest。Generation 1 的固定 identity：

| 資源 | 位置 |
|---|---|
| Worktree | `<primary-parent>/<repo-name>.worktrees/<work_id>` |
| Branch | `delivery/<work_id>` |
| Artifact root | `docs/work/<work_id>` |
| Requirements | `docs/work/<work_id>/requirements.md` |
| Plan bundle | `docs/work/<work_id>/plan/` |

Generation `N > 1` 的 worktree label 與 branch 分別追加 `-rN`；artifact paths 仍由 revision suffix 區分。

## Portable v2 state

`sdlc init --repo <path>` 只建立目標專案設定、state binding 與必要的 ignore-safe
metadata；runtime record、dispatch assignments、review reports、raw test outputs
與 publication state 位於 plugin 管理的使用者狀態區，並依 repository identity／Work ID
隔離。State root 必須在目標 repository 之外；不把 credential、token 或原始秘密寫入
state，也不要求目標專案安裝或包含本 repository 的 `.agents/skills` tree。

v2 `start` 先做唯讀 classification。`read_only` 不建立 run；`small` 在一次 integrated
approval 前只保存 create-only design bundle；`large`／bug 在完成各自 Requirements／
Planning／diagnosis gates 前也只保存候選 state。核准與 payload digest 綁定後，才可建立
Work ID 專用 worktree／branch。`doctor` 與 `status` 顯示 repository identity、task class、
phase／status、current assignment、review／knowledge／publication state 與 state path，
`resume` 只重試第一個未完成 action。

v2 state 與 v1 registry 不共用 record、approval 或 evidence。既有 v1 record 缺少
`delivery-run/v2` discriminator 時，沿用本文件下方的 legacy host-temp rules；不做自動
遷移。v2 finish handoff 的 commit／push／draft PR 規則見
[v2 派工、審查與交付收尾契約](../../implementation-execution/references/v2-dispatch-and-finish.md)。

## 公開 helper

唯一 workspace mutator是 [`delivery_workspace.py`](../scripts/delivery_workspace.py)：

```text
delivery_workspace.py probe --repo <path> [--topic <ascii-kebab>] [--request-sha256 <sha256>]
delivery_workspace.py start --repo <primary> --work-id <id> --request-sha256 <sha256> [--generation N]
delivery_workspace.py locate --repo <any-worktree> [--work-id <id>]
delivery_workspace.py transition --repo <any-worktree> --work-id <id> --phase <phase> --status <status> --event <kind> --evidence-ref <ref> [...]
```

固定以 `python -X utf8 -B` 執行。成功輸出為既有 JSON contract；非零 exit 表示結果未成立。唯一新增的 failure code 是 `GIT_TRUST_REQUIRED`：caller 取得 unsandboxed Git probe／mutation 授權後重跑同一命令，不改 Git trust configuration。

`--registry-root` 只供隔離測試或明示 host 設定，且必須位於 canonical host temp provider。Helper 沒有 cleanup、delete 或 terminal Git command。

BUG new work另接受 `start --work-kind bug --bug-id <bug-id>`；standard可省略。Requirements transition可原子接受`--bug-assessment-id`、JSON／Markdown path與SHA-256。途中BUG使用`--deferred-bug-id/relation/status/evidence-ref`，materialized事件另帶assessment JSON／Markdown path與hash；legacy Complete或required knowledge review gate使用`--bug-verification-path/sha256/result`。需做exact-value secret scan時以可重複的`--known-secret-env <ENV_NAME>`只傳環境變數名稱，值只在process memory解析並傳給assessment、verification、review與terminal evidence validators，永不進argv output或record。Assessment與verification consumer在stable read後、JSON parse前掃描同一份raw bytes，拒絕duplicate object keys並核對parsed object，錯誤不反射秘密。

新的公開 `start` 一律建立 optional field `knowledge_gate` 的 required policy；舊 record 沒有該 field 時明確維持 legacy policy，不做 registry migration。Self-host 中已進入 implementation 的既有 record只能以具證據的 `--enable-knowledge` self-transition啟用。Transition 的 `--knowledge-candidate-*`、dual snapshot、product snapshot、outcome、promotion receipt與approval evidence參數是同一 gate 的具名 binding；只傳部分欄位會 fail closed。

完成條件：caller 已保存成功 JSON 或精確 error code；stderr 沒有秘密或原始 Git command output。

## Registry 與 record

Registry 固定為 `<host-temp>/delivery-orchestrator/repos/<repo_id>/works/<work_id>/`。每次讀取與 atomic transition 都先驗證 [delivery-run/v1 schema](delivery-run.schema.json)與 append-only semantics；未知 root／nested field 一律拒絕，錯誤不反射欄位值。

- Phase：legacy為`workspace → requirements → planning → implementation → complete`；required overlay在 implementation 後加入`knowledge`
- Required forward path：`implementation/active → knowledge/active → knowledge/awaiting_user → complete/complete`
- 回流：`planning → requirements`、`implementation → planning`；knowledge若需產品修改則`knowledge → implementation`並清除 reviewed Candidate binding
- Status：`active | awaiting_user | blocked | complete`
- Blocked recovery：相同 phase 的 `blocked → active`
- Complete：沒有 outgoing transition
- Events、revisions、generations：只追加，不覆寫

Optional BUG overlay：

- `work_kind`缺失等同`standard`；舊standard record可完全沒有`bugs`，途中發現BUG時才以`primary_bug_id: null`加入optional overlay，不得冒充primary bugfix。
- `work_kind: bug`具有primary BUG、create-only assessment bindings、途中deferred evidence與terminal verification binding。
- Bug run進Planning前必須在同一次Requirements approval綁定assessment Markdown／JSON paths、hashes與相同approval refs。
- Legacy Bug run Complete必須在同一次terminal transition綁定非`failed` verification；required overlay則在`implementation → knowledge/active` fresh-review transition綁定，最後 promotion transition重驗，不得更早占用create-only binding。`partial`的Plan safeguard與implementation review仍由各自owner驗證，兩份summary皆不得過度宣稱。
- Deferred history以每個bug ID的`pending → materialized`連續sequence追加，不原地更新。`unrelated`的全域inbox使用host-temp create-only `<registry>/repos/<repo_id>/bug-inbox/<bug-id>.json`，只含遮蔽evidence refs；ID碰撞拒絕覆寫並要求最小數字suffix。安全、隱私或資料風險須同時提供`--deferred-bug-sensitive`、`--deferred-bug-redacted-summary`、`--deferred-bug-human-reviewer`與安全的`--deferred-bug-evidence-ref`；materialized assessment必須逐值吻合。

Requirements、plan、implementation refs 必須由具名 `transition` 參數一次追加，且只在 child 結果已持久化後執行。Repository artifact 只含 Work ID 相對路徑；absolute primary／worktree paths 只在 host-temp record。

Optional knowledge overlay：

- 新 record 的`policy`固定為`required`；`candidate_ref`／payload、reviewed knowledge snapshot、product snapshot、repo-side outcome、Ready promotion history與current promotion都使用closed contract。
- Required requirements與plan gate各自必須在同一次人工核准 transition綁定相同approval evidence的`knowledge-promotion/v1` Ready receipt與passed lint；缺任何一側回`MISSING_KNOWLEDGE_GATE`。
- Preliminary fresh review先以實體report／raw outputs核准尚未含Outcome的product；latest create-only `implementation-outcome/v1`綁current run、preliminary report path／hash與逐command evidence。封存Candidate後由不同final fresh review綁相同的`knowledge_snapshot_before/after`、Candidate ref／digest與只排除`docs/knowledge/**`的final product snapshot，才進`knowledge/active`。Knowledge snapshot由目前全部Git-eligible `docs/knowledge/**` pre-tree與sealed operations重建expected post-tree；不得信任caller只傳相等ID。完整 diff 留在同一 immutable manifest 並提供直接連結，Chat 只回摘要後才進`knowledge/awaiting_user`。
- `knowledge/awaiting_user → complete/complete`只接受與review binding相同的implementation／bug Candidate、Ready receipt、相同approval evidence、實際完整knowledge tree等於reviewed expected post-tree及passed full lint。Required record不得`implementation → complete`；legacy absence仍走既有terminal checks。

完成條件：schema 與 semantic validation 同時通過，最後 event 精確重建目前 phase/status，current refs 各指向一個已記錄且 hash 相符的 revision/run。

## Locate 與 resume

指定 `work_id` 時只接受該 record。未指定時，非 Complete record 恰好一個才自動選取；多個回傳候選 ID；沒有回傳 `NOT_FOUND`。

Resume 不執行 new-work clean gate。它重算 repo/worktree/branch、recorded base ancestry、current refs 與 hashes；同 branch 上源自 recorded base 的既有進度可保留。Registry 遺失、binding mismatch、hash drift 或 ancestry 不可證明時進入 Blocked，不從 branch 名、相似文字或目前 HEAD 猜測 continuity。

完成條件：已定位唯一 record，current generation 經重新驗證，下一個 action 是 record 中最早未完成的 child action；已持久化核准與 Complete child 不重做。

## Evidence 與失敗

Git command evidence 只保存 logical operation、safe controls、exit code、stdout／stderr byte count與 SHA-256；raw argv 與 raw output只在目前 process memory用於分類。原始 prompt、credential、token、hook／filter output及秘密值不進 registry。

任何建立後 failure 追加 `blocked` event並保留 path、branch、record 與 worktree。能力或授權不足時回報精確復原需求。
