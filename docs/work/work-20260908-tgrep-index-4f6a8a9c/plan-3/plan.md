# 技術規劃：將 tgrep.exe 整合至 Project Knowledge 搜尋流程

- 計畫狀態：Ready
- Candidate revision：`candidate-3`
- 日期：2026-09-09
- Work ID：`work-20260908-tgrep-index-4f6a8a9c`
- 來源規格：`docs/work/work-20260908-tgrep-index-4f6a8a9c/requirements.md`
- 範圍：Project Knowledge query adapter、明確 tgrep index command、狀態 fingerprint、測試、文件、attribution 與 portability CI
- 基線：主分支 `8e88c1278d7cdf5c0c08106a49290d0d80ea327f`；根目錄已追蹤 `tgrep.exe` v1.0.4

## 1. 成果、限制與決策

本計畫把 tgrep 作為 Windows-only、可驗證的 on-disk 搜尋加速器；`rg` 保持必要依賴與所有不適用／失敗情況的 fallback。查詢不建立 index、不啟動 daemon，既有 `knowledge-context/v1`、`knowledge-error/v1`、結果排序、parser、path normalization 與 Git staged 語義不變。

規劃決策：只在 Windows 且 state、index 與 repository fingerprint 全部一致時使用 tgrep，其餘情況無聲回到 rg。

- 範圍內：`knowledge_query.py` tgrep adapter、`knowledge_cli.py tgrep-index`、atomic state、binary/index/source fingerprints、unit／integration parity tests、README／OPERATIONS、`.gitignore`／`.gitattributes`、attribution 與 portability workflow。
- 範圍外：`tgrep serve`、自動下載或更新 binary、Git index 寫入、跨 invocation／跨 worktree cache、移除 `rg`、公開 schema 改版。
- Runtime：不新增 Python package、network requirement 或 persistent service。
- Index：建立時使用 `--hidden`；查詢省略 `--hidden`，並保留 `.git/**` exclusion。每個 worktree 的 `.tgrep/` 與 state 分開維護。

## 2. 設計與資料流

### TD-001 — Engine adapter 與等價 parser

在既有 `rg` runner 旁新增 tgrep runner，集中產生 NUL、line-number、with-filename、ignore-case、color-never、glob 與 fixed／regex flags。只接受 exit 0（有輸出）或 1（no match）；輸出交給同一套 parser 與路徑正規化。非零其他狀態、解碼／NUL／line parse failure 都轉為靜默 rg fallback。

### TD-002 — Index state 與 stale fail-closed

`TgrepIndexState` 使用 `tgrep-index-state/v1` sidecar，記錄 canonical worktree identity、repository snapshot、tgrep version、binary SHA-256、index parameters、index fingerprint 與 source fingerprint。query 只接受 state 與當前 repository snapshot 完全一致的 index；任何 content、checkout、branch、index 或 binary drift 直接使用 rg。state 以 temporary file + atomic replace 寫入，未完成或漂移不發布 ready state。

### TD-003 — Explicit index lifecycle

CLI 新增 `tgrep-index --repo <repo> [--force]`。它在 index 前後 capture snapshot，執行 `tgrep.exe index --hidden ...`，驗證 index status／fingerprint，最後才原子發布 state；前後 snapshot 不同時移除／不產生 ready state 並回傳 versioned error。query 永不呼叫 index 或 serve。

### TD-004 — Git overlay 與 portability

`git grep --cached` 繼續負責 staged snapshot；dirty／untracked overlay 維持目前合併與 dedupe。Windows workflow 驗證 binary、version、hash、index command、實際 indexed smoke；Linux workflow 以 `rg` 驗證並明確確認 `.exe` 不被執行。文件說明 stale／checkout／branch 變更後重建。

## 3. 模組、介面與不變量

| Module | 責任 | 可觀察介面 | 不變量 |
|---|---|---|---|
| MOD-001 | tgrep executable resolution／argv／parser | internal runner seam | Windows-only；NUL output；exit 1 是 no-match |
| MOD-002 | index command／state validation | `knowledge_cli.py tgrep-index` JSON／exit | explicit write only；atomic ready state |
| MOD-003 | query engine selection | existing query JSON | state mismatch／failure fallback to rg |
| MOD-004 | overlay／portability／docs | staged result、CI、操作文件 | git grep cached remains authoritative |

查詢流程：capture current session → validate tgrep state → tgrep worktree search or rg → existing staged/dirty overlay → existing parser/order → one public response。初始化流程：pre-snapshot → index build → post-snapshot → fingerprint/state validation → atomic state publish。

## 4. 測試策略與驗收映射

使用現有 Python stdlib `unittest` 與 Project Knowledge behavior runner，不新增 framework。新增外部可觀察 tgrep scenarios 與 inner unit tests，涵蓋：argv flags、NUL parser、`.`／`./`／`.\\` paths、exit 1、malformed output、state mismatch、binary/index failure、no auto-write、CJK、hidden `.agents`、CRLF、fixed／regex、staged、dirty、untracked 與 Windows/Linux fallback。

BDD-001：已初始化 Windows index 的 query 實際選 tgrep，結果與 rg golden 完全相同。

BDD-002：未初始化／stale／失敗／malformed tgrep 查詢維持 rg 結果、零 query writes、零額外 stderr。

BDD-003：index command 建前後 repository 漂移不產生 ready state；`--force` 才會重建。

BDD-004：staged／dirty／untracked overlay 與 `git grep --cached` 維持既有結果。

TEST-001：command builder、NUL parser、Windows path 與 exit-1 unit coverage。

TEST-002：state／fingerprint／atomic publication／fallback coverage。

TEST-003：Windows tgrep-vs-rg fixture parity、Linux rg-only portability 與既有 query／BDD／workflow regression。

驗收門檻：`knowledge-context/v1`／`knowledge-error/v1` bytes 與 public mapping 不變；所有 fallback 無額外 stderr；Windows smoke 觀測 tgrep；Linux 不執行 `.exe`；repository status 在 query／測試後回到執行前狀態。


### Revision R-001 — full-test runner contract

上一輪 attempt-002 的 CMD-TEST-FULL-001 使用直接的 unittest discover，雖然命令本身可啟動測試，卻沒有先建立既有 Project Knowledge full-suite 所需的隔離 fixture；觀察結果為 exit 1、Ran 105 tests、errors=152，錯誤集中在 fixture_root 與 scenario binding 缺失。這是 runner contract mismatch，不是 tgrep 行為回歸。

修訂決策：採用既有 run_full_suite.py 作為 full-test runner，保留 12 個 validation obligations。

新的 CMD-TEST-FULL-001 exact command 是：

    python -X utf8 -B .agents/skills/project-knowledge/scripts/run_full_suite.py --scope all --profile local --fixture-root .knowledge-test-tmp/fixtures --jobs 1 --evidence-root .knowledge-test-tmp/evidence

runner 由既有腳本建立並清理 .knowledge-test-tmp/fixtures，將 validation evidence 寫入 .knowledge-test-tmp/evidence；執行器以 IMPLEMENTATION_READY_PAYLOAD_SHA256 綁定當前 Ready handoff，不把 digest 硬編碼進 command，避免 self-reference。此命令 network forbidden、jobs 固定為 1，且不寫產品檔案。CMD-TEST-FULL-001 在新 revision 中標為 Proposed，待新的 generation 以完整 fixture 執行。

這次變更改動全域 test-full command／validation baseline，分類為 global-baseline；因此核准後由 Delivery Orchestrator 建立 generation 2，不沿用 generation 1 的產品 diff。既有 plan-2 與 attempt-001／attempt-002 證據保留為歷史。

## 5. 工作包

### WP-001 — Query adapter、state validator 與 explicit index CLI

- 需求：FR-001..005、AC-001、AC-003、AC-004；MOD-001..003。
- 順序：先建立 runner/parser seam 與預期 red，再實作 state validation、index command、atomic publication，最後接入一般 regex／fixed worktree search。
- 完成：所有 tgrep 不適用／失敗路徑 fallback；staged overlay 未被取代；CLI 不被 query 隱式呼叫。

### WP-002 — Behavior／unit／integration parity

- 需求：FR-002..005、AC-001..004；MOD-001..004。
- Blocked by：WP-001。
- 順序：先跑 command/parser/state red，完成最小 green，再加入 CJK／hidden／CRLF／Git overlay 與 Windows cold/warm sample。
- 完成：新增 tgrep suite 零 unexpected skip，rg golden parity 與 no-write／stderr oracle 通過。

### WP-003 — Attribution、文件與 portability CI

- 需求：FR-006、AC-005；MOD-004。
- Blocked by：WP-001、WP-002。
- 順序：加入 binary attributes／ignore／第三方 notice，更新 README／OPERATIONS，再補 Windows／Linux path filters、smoke 與 rg-only assertions。
- 完成：Windows 驗證 binary/index/tgrep smoke；Linux 明確不執行 exe 且 fallback 綠；full query／BDD／workflow／governance 綠。

## 6. 風險與追溯

| Risk | 影響 | 緩解 |
|---|---|---|
| stale index 漏結果 | incorrect knowledge context | source fingerprint 與 state mismatch fail-closed to rg |
| tgrep／rg flags 差異 | CJK、hidden 或 path parity drift | 共用 parser、golden fixture、Windows/Linux matrix |
| overlay 誤取代 staged | Git semantics regression | `git grep --cached` 保留為 staged authority |
| index 建立競態 | ready state 宣稱過早 | pre/post snapshot、index fingerprint、atomic sidecar |
| binary／license drift | reproducibility／distribution risk | tracked binary hash、attribution、CI verification |

## 7. Artifact 與 readiness

| Path | Role | 內容 |
|---|---|---|
| `plan-3/plan.md` | primary | 設計、介面、測試、WP、風險與驗收 |
| `plan-3/source-evidence.md` | supporting | repository／tgrep 官方來源、版本與 baseline evidence |
| `plan-3/handoff.json` | handoff | ready-plan/v1 source、contract、command、WP 與 validation manifest |

本計畫只授權進入 implementation-execution；不授權 commit、merge、push、部署或 `tgrep serve`。implementation completion 必須附 outcome、fresh full suite、Windows／Linux portability evidence 與 query no-write proof。
