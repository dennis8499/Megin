<!-- authority: delivery-run -->

# Workspace 與 Run 契約

本文件是 `work_id` identity、host-temp registry、`delivery-run/v1`、resume 與 record continuity 的唯一權威。New work／generation 的 Git mutation 由 [Workspace 建立契約](workspace-creation.md)擁有。

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

完成條件：caller 已保存成功 JSON 或精確 error code；stderr 沒有秘密或原始 Git command output。

## Registry 與 record

Registry 固定為 `<host-temp>/delivery-orchestrator/repos/<repo_id>/works/<work_id>/`。每次讀取與 atomic transition 都先驗證 [delivery-run/v1 schema](delivery-run.schema.json)與 append-only semantics；未知 root／nested field 一律拒絕，錯誤不反射欄位值。

- Phase：`workspace → requirements → planning → implementation → complete`
- 唯一回流：`planning → requirements`、`implementation → planning`
- Status：`active | awaiting_user | blocked | complete`
- Blocked recovery：相同 phase 的 `blocked → active`
- Complete：沒有 outgoing transition
- Events、revisions、generations：只追加，不覆寫

Requirements、plan、implementation refs 必須由具名 `transition` 參數一次追加，且只在 child 結果已持久化後執行。Repository artifact 只含 Work ID 相對路徑；absolute primary／worktree paths 只在 host-temp record。

完成條件：schema 與 semantic validation 同時通過，最後 event 精確重建目前 phase/status，current refs 各指向一個已記錄且 hash 相符的 revision/run。

## Locate 與 resume

指定 `work_id` 時只接受該 record。未指定時，非 Complete record 恰好一個才自動選取；多個回傳候選 ID；沒有回傳 `NOT_FOUND`。

Resume 不執行 new-work clean gate。它重算 repo/worktree/branch、recorded base ancestry、current refs 與 hashes；同 branch 上源自 recorded base 的既有進度可保留。Registry 遺失、binding mismatch、hash drift 或 ancestry 不可證明時進入 Blocked，不從 branch 名、相似文字或目前 HEAD 猜測 continuity。

完成條件：已定位唯一 record，current generation 經重新驗證，下一個 action 是 record 中最早未完成的 child action；已持久化核准與 Complete child 不重做。

## Evidence 與失敗

Git command evidence 只保存 logical operation、safe controls、exit code、stdout／stderr byte count與 SHA-256；raw argv 與 raw output只在目前 process memory用於分類。原始 prompt、credential、token、hook／filter output及秘密值不進 registry。

任何建立後 failure 追加 `blocked` event並保留 path、branch、record 與 worktree。能力或授權不足時回報精確復原需求。
