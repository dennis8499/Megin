# 需求分析：將 tgrep.exe 整合至 Project Knowledge 搜尋流程

- 文件狀態：Ready
- 日期：2026-09-08
- Work ID：`work-20260908-tgrep-index-4f6a8a9c`
- 需求來源：使用者明示的 tgrep v1.0.4 整合計畫與 Microsoft/tgrep 官方 README／原始碼
- 確認者：user；approval evidence `conversation:implement-tgrep-plan-20260908`

## 1. 目標與範圍

把 repository 根目錄已納入版本控制的 Windows-only `tgrep.exe` v1.0.4 作為 Project Knowledge 的可選搜尋加速器。一般 worktree regex／fixed-string 查詢在 Windows 且有有效 on-disk `.tgrep` index 時使用 tgrep；其他情況無聲回到既有 `rg`。`rg` 仍是必要依賴與可靠 fallback。

本需求包含 `knowledge_query.py` adapter、`knowledge_cli.py tgrep-index` 初始化命令、index state／fingerprint 驗證、測試、README／OPERATIONS、`.gitignore`／`.gitattributes`、第三方 attribution 與 Windows／Linux portability CI。既有 `knowledge-context/v1`、`knowledge-error/v1`、查詢唯讀語義、輸出 parser、路徑正規化及 staged `git grep --cached` overlay 必須保持相容。

## 2. 行為需求

### FR-001 — Windows indexed search with fallback

Windows 上只有在 bundled `tgrep.exe`、`.tgrep` index 與 `tgrep-index-state/v1` 全部存在、可讀、版本／binary hash／fingerprint／參數一致時，才選用 tgrep。binary 缺少、非 Windows、state mismatch、index stale、tgrep exit/error 或輸出無法解析時，查詢必須無聲使用 `rg`，不得自動建立 index、啟動 server 或新增 stderr。

### FR-002 — Preserve search semantics

tgrep adapter 必須使用 NUL、行號、檔名、ignore-case、fixed-string／regex 等與現有 `rg` 等價的選項，沿用既有 parser、結果排序、去重與 repository-relative path normalization。tgrep exit code 1 代表 no match，不得誤判為 tool failure。Windows `./` 或 `.\\` 路徑、CJK、hidden `.agents`、CRLF、untracked 與 dirty 檔案都必須與 `rg` 等價。

### FR-003 — Git staged overlay remains authoritative

`git grep --cached` 仍負責 staged snapshot 與 Git index 語義；tgrep 不得取代 staged overlay。大型查詢可以沿用既有 dirty／untracked worktree overlay，並以 tgrep 搜尋 worktree 部分後套用既有合併與去重規則。

### FR-004 — Explicit, race-safe index initialization

`python -X utf8 -B .agents/skills/project-knowledge/scripts/knowledge_cli.py tgrep-index --repo . [--force]` 是唯一初始化入口。命令只建立 repository-local `.tgrep/` 與 `tgrep-index-state/v1` state，index 建立前後若 repository snapshot 漂移，不能產生 ready state。`--hidden` 只用於建立 index；查詢省略 `--hidden` 以保留 indexed search。每個 worktree 各自維護 index。

### FR-005 — Stable state and provenance

state 必須記錄 repository snapshot、tgrep version、bundled binary SHA-256、index parameters 與 index fingerprint。內容、checkout、branch 或 index 變更後 state 必須失效，查詢不得以 stale index 產生漏結果。state writes 必須 atomic；query 維持無寫入與無額外 stderr。

### FR-006 — Portability and attribution

Windows CI 必須驗證 binary、初始化 index 並執行 indexed smoke test；Linux CI 必須明確證明不執行 `.exe` 且仍可用 `rg`。README／OPERATIONS 必須說明初始化與重建時機。repository 必須記錄 Microsoft/tgrep 來源、MIT license、v1.0.4 與目前 binary SHA-256，並將 binary 標為 binary、`.tgrep/` 加入 ignore。

## 3. 品質與相容限制

- 不新增 runtime package、network requirement、daemon 或 persistent server。
- 不改變既有 `knowledge-context/v1`／`knowledge-error/v1` schema、錯誤 mapping、結果排序或 citation semantics。
- 所有 query paths 仍唯讀；index initialization 是明確使用者命令，非 query side effect。
- tgrep 只在 Windows indexed path 使用；`rg` remains a required dependency and fallback。
- 驗證包含 unit parser／flags／fallback、Windows tgrep-vs-rg parity（CJK、hidden、CRLF、fixed、regex、staged、dirty、untracked）及 Linux portability。

## 4. 驗收情境

- AC-001：未初始化、過期、錯誤或 malformed tgrep output 均無聲回到 rg；query 不建立 `.tgrep`、不啟動 server、不改 stderr。
- AC-002：已初始化 Windows index 的 regex／fixed-string／CJK／hidden／CRLF／`./` 路徑結果與 rg 完全相同，且 cold／warm smoke 確認實際選用 tgrep。
- AC-003：staged、dirty、untracked overlay 維持既有結果與 Git index semantics；`git grep --cached` 仍被使用。
- AC-004：index command 記錄完整 state；建前後漂移不產生 ready state；`--force` 可明確重建，普通查詢不自動修復。
- AC-005：Windows portability gate 驗證 binary、state、indexed smoke；Linux gate 驗證 `.exe` 不執行且 rg fallback 通過；既有 full query／BDD／workflow suites 保持綠色。

## 5. 非目標

本次不使用 `tgrep serve` daemon、不自動下載或替換 binary、不改變 Git index 內容、不移除 ripgrep、不改寫既有知識 schema、不建立跨 worktree 或跨 invocation cache。
