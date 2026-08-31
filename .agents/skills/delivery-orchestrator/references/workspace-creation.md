<!-- authority: delivery-workspace-creation -->

# Workspace 建立契約

只在建立新 work 或新增 generation 時完整讀取。本文件是 Git preflight、safe worktree mutation、generation materialization 與 post-verification 的唯一權威。

## New-work preflight

Helper 依序證明：

1. Repository 非 bare；目前 root 精確等於 `git worktree list --porcelain` 的 primary，HEAD attached。
2. Recursive porcelain-v2 strict status 為空。每層停用 active filters、fsmonitor 與 submodule recursion後檢查 staged、unstaged、untracked及已初始化 submodule；ignored output不計。
3. Base 是 probe 的 exact HEAD；branch、destination、registry不存在。
4. Destination 是 `<primary-parent>/<repo-name>.worktrees/` 的直接 child，不與 primary重疊，也不是 symlink／junction redirect。
5. Host temp 與 sibling destination可寫；額外授權在 Git mutation 前取得。

任一條件失敗時沒有 Git mutation。完成條件：probe evidence 已持久化為 digest／byte count，record reservation 由 atomic directory winner 建立。

## Hardened Git invocation

Git invocation 清除 routing、repository、config-injection 與 trace overrides；固定 `LC_ALL=C`、`LANG=C`、`LANGUAGE=C` 供 failure classification。它停用 lazy fetch、replace objects、fsmonitor、sparse checkout、submodule recursion與 auto maintenance，以 host-temp 私有空目錄覆寫 hooks path，並清空 tracked paths 使用的 process／clean／smudge filter。

Trust failure 只在記憶體辨識 `detected dubious ownership` 與 `safe.directory`，回報 `GIT_TRUST_REQUIRED`。Caller 取得 unsandboxed authorization後重跑；嚴禁用 command config、global config或環境變數新增／繞過 `safe.directory`。

唯一 mutation 的邏輯形狀：

```text
git worktree add --no-track -b <branch> <destination> <exact-base-sha>
```

沒有 `-B`、`-f`、hooks、filters或 shell。完成條件：command evidence只有 operation、safe controls、exit code、digest與 byte count。

## Post-verification

建立後重新驗證 worktree registration、non-primary、attached branch、HEAD、repo ID與 strict-clean。全部成立才把 generation改為 `ready` 並追加 created event；任一失敗將 generation設為 `blocked`，保存 evidence且不 cleanup。

完成條件：record、Git registration與實際 workspace identity一致，或 Blocked evidence清楚指出唯一失敗分類。

## Later generation

只有未 Complete 的既有 record可建立 contiguous `N`。Primary HEAD 必須仍等於上一 generation 的 approved base；current Ready requirements／plan approvals、paths、payload及 source hashes全部重驗。

新 generation只以 create-only materialize已核准 upstream bytes；primary bug run assessment與任何已materialize的途中assessment都連同Markdown／JSON及hash複製，pending evidence不假裝成repository artifact。它不複製舊 generation 的產品、測試、設定或 dependency diff。非 bundle／requirements local source在 Git mutation前讀取recorded-base blob並核對manifest SHA；不存在或bytes不符即停止。任何 collision／drift保留 Blocked現場。

完成條件：新 generation是 `ready`、核准 upstream bytes hash相同、產品 diff為空，舊 generation與歷史 record保持不變。
