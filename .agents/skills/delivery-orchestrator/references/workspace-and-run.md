<!-- authority: delivery-run -->

# Workspace 與 Run 契約

本文件是 `work_id`、Git workspace、host-temp registry、resume 與 `delivery-run/v1` 的唯一權威。任何 worktree 或 branch mutation 前完整讀取。

## 1. Work ID 與固定位置

使用者在初始請求提供的 ID 只有符合 3–64 字元的 lowercase ASCII kebab-case（英數 segment 以單一 `-` 分隔，無空 segment）且不是 Windows reserved device name 時才接受；建立後不可改名。

未提供時：

1. 將最初要求落地的使用者訊息做 UTF-8 SHA-256，record 只保存 digest。
2. 從任務主題翻譯或音譯二至五個 ASCII kebab-case 單字；不足兩個時補 `work`，無可靠主題時使用 `general-work`。
3. 以 canonical JSON `{repo_id, initial_base_sha, request_sha256}` 的 SHA-256 前八碼形成 `work-YYYYMMDD-<topic>-<8hex>`；日期使用 host local date。

Generation 1 固定為：

| 資源 | 位置 |
|---|---|
| Worktree | `<primary-parent>/<repo-name>.worktrees/<work_id>` |
| Branch | `delivery/<work_id>` |
| Artifact root | `docs/work/<work_id>` |
| Requirements | `docs/work/<work_id>/requirements.md` |
| Plan bundle | `docs/work/<work_id>/plan/` |

Implementation contract 要求新 workspace/run 時，尚未 Complete 的 delivery 可新增 generation `N`：worktree 與 branch 分別使用 `<work_id>-rN` 與 `delivery/<work_id>-rN`。`start --generation N` 要求 primary HEAD 仍等於上一 generation 的 approved base，先重驗 current requirements／Ready bundle 的核准、base、paths 與 hashes，再以 create-only 寫入新 worktree；只 materialize 這些已核准 upstream bytes，不複製舊 generation 的產品、測試、設定或 dependency diff。任一 collision／drift 保留 Blocked 現場。若確實要改 base，須先經上游重新核准，不從 primary 現況猜測。`Complete` delivery 不新增 generation。

## 2. Helper 介面

唯一 workspace mutator 是 [`delivery_workspace.py`](../scripts/delivery_workspace.py)，固定以 `python -X utf8 -B` 執行並輸出 JSON：

```text
delivery_workspace.py probe --repo <path> [--topic <ascii-kebab>] [--request-sha256 <sha256>]
delivery_workspace.py start --repo <primary> --work-id <id> --request-sha256 <sha256> [--generation N]
delivery_workspace.py locate --repo <any-worktree> [--work-id <id>]
delivery_workspace.py transition --repo <any-worktree> --work-id <id> --phase <phase> --status <status> --event <kind> --evidence-ref <ref> [...]
```

`--registry-root` 只供隔離測試或明確 host 設定，且仍須位於 canonical host temp provider 之下；runtime 預設為其 `delivery-orchestrator/`。非零 exit 代表未取得所宣稱的結果；stderr 不得包含秘密。

`transition` 只有在對應 child 結果已持久化後執行。Requirements、plan 或 implementation refs 使用該 command 的具名參數一次追加，不能直接手改 `run.json`。

## 3. New-work preflight 與原子建立

Helper 保存不含原始命令輸出的 bounded probe evidence，依序驗證：

1. Git repository 非 bare，目前 root 精確等於 `git worktree list --porcelain` 第一筆 primary worktree，且 HEAD attached。
2. 安全的 recursive porcelain-v2 probe 為空：每層先以 `--untracked-files=all --ignore-submodules=dirty` 檢查自身，再逐一進入已初始化 gitlink，以該層已停用的 filter/fsmonitor 重做相同檢查；這在不執行 submodule 外部 driver 的前提下等價涵蓋 `--ignore-submodules=none` 的 dirty 判定。Ignored build/cache 不計；staged、unstaged、untracked 與任一深度 dirty submodule 都停止，未初始化的空 gitlink 仍視為 clean。
3. Base 固定為 probe 的完整 HEAD SHA；branch、destination、registry 均不存在，或既有 registry 可完整證明是相同 ready generation。
4. Destination canonical path 是 primary sibling container 的直接 child，不在 primary 內，也不是 primary 的 ancestor。
5. 宿主允許寫入 host temp 與 sibling destination；需要額外授權時在 Git mutation 前取得。

通過後先原子建立 `<root>/repos/<repo_id>/works/<work_id>/` 並保存 reservation。Git mutation 使用下面的邏輯操作，且不含 `-B`／`-f`：

```text
git worktree add --no-track -b <branch> <destination> <exact-base-sha>
```

實際 invocation 先移除會改寫 Git routing／trace 的環境變數，停用 lazy fetch、replace objects、fsmonitor、sparse checkout、submodule recursion、auto maintenance；以 host-temp 私有空目錄覆寫 `core.hooksPath`。Helper 在 superproject 與每個已初始化 submodule 從 tracked paths／effective attributes 列出 filter driver，再以 command-scoped config 清空其 process／clean／smudge並設 `required=false`。無法安全列出、逐層驗證或停用時，在 Git mutation 前停止。

完成後重新驗證 worktree registration、attached branch、HEAD、repo ID 與 clean status，才把 generation 標為 `ready`。Command evidence 只保存 operation、safe controls、exit code、stdout／stderr byte count 與 SHA-256，不保存原始輸出或完整 argv。任何中途 failure 追加 `blocked` event 並停止；不刪 path、branch、record 或 worktree。Incomplete／mismatched reservation 不自動接管。

## 4. Record 與 resume

Record 每次讀取與 atomic transition 前都必須通過 [`delivery-run/v1` schema](delivery-run.schema.json)及 append-only semantic validation；未知 root／nested 欄位一律拒絕，錯誤訊息不反射欄位值。Absolute primary／delivery paths 只存在這個 host-temp record；repository artifacts 只出現 `work_id` 相對路徑。

- `phase`：`workspace | requirements | planning | implementation | complete`
- `status`：`active | awaiting_user | blocked | complete`
- 正向 phase：workspace → requirements → planning → implementation → complete。
- 回流只允許 planning → requirements 與 implementation → planning；相同 phase 可追加 iteration。
- Blocked 解除時維持原 phase，保存 blocker 與解除證據後 `blocked → active`。
- Complete 沒有 outgoing transition，歷史 events／revisions／generations 只追加不覆寫。

Resume 不執行 new-work clean gate。指定 `work_id` 時只接受該 record；未指定時，非 Complete record 恰好一個才自動選取，多個則回傳可選 ID 並停止。Record 找到後重算 repo／worktree／branch、recorded base ancestry、current refs 與 hashes；允許 HEAD 在同 branch 上保留可證明源自 recorded base 的既有進度，不要求退回 base。無法證明連續性時標記 Blocked，不從目前 HEAD 或相似任務文字猜測。

## 5. 安全與失敗

- 不把原始 prompt、秘密、credential、token、hook／filter output或未遮蔽 command output寫入 record；只保存 digest、byte count、logical ref 或遮蔽事件。
- 不提供 cleanup／delete／commit 子命令。使用者取消或能力不足時保留 workspace 與 record並回報精確復原需求。
- Registry 遺失時，即使 branch／path 看似匹配也不靜默重建；回報 continuity blocker。
- 同一 ID 的 concurrent start 只有 atomic directory winner 可建立；loser 只能 locate 已完成 record，或在 winner 尚未完成時停止。
