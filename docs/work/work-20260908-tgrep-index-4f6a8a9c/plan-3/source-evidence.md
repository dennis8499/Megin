# 規劃來源證據：tgrep.exe 與 Project Knowledge

- 日期：2026-09-09
- Work ID：`work-20260908-tgrep-index-4f6a8a9c`
- 用途：materialized supporting source for the Ready plan；外部網址僅作 provenance，不作不可重取的唯一 bytes source。

## 1. 使用者核准範圍

使用者要求根據 Microsoft/tgrep 將根目錄 `tgrep.exe` 整合至 Project Knowledge 搜尋流程，並明確要求：Windows-only 預設加速、保留 `rg` fallback、保留 `knowledge-context/v1`／`knowledge-error/v1`、保留 `git grep --cached` staged overlay、不自動建 index、不使用 serve，以及補齊 state、測試、文件、attribution 與 portability CI。

此內容由本次對話中的完整實作計畫 materialize；核准 evidence：`conversation:implement-tgrep-plan-20260908`。

## 2. Binary 與受控 probes

- `tgrep.exe` 是 PE binary，版本／產品版本為 1.0.4，執行 `tgrep 1.0.4`。
- 現有 binary SHA-256：`bac0a288f6e588e7708c87ace2e381f50d5190269c471c10e1ffb9c524fc02de`。
- 未建立 index 時，`tgrep status .` 回報 repository-local `.tgrep` 不存在；查詢不得因此自動建立。
- `tgrep index . --hidden` 可建立 trigram index；indexed query 省略 `--hidden` 時仍可查到 hidden `.agents`，加上 `--hidden` 會退回 brute-force。故 `--hidden` 只屬 index-build argv。
- indexed search 支援 ripgrep 相容 flags；NUL／line number／filename 輸出可由既有 parser 正規化。
- stale index probe 顯示 index 建立後的內容變更可能同時漏掉舊值與新值；state 必須以 repository snapshot／fingerprint fail-closed。

## 3. Existing repository seams

- `knowledge_query.py` 已有 `rg` regex／fixed-string runners、NUL parser、路徑 normalization、`QuerySearchSession`、Git staged／dirty／untracked overlay 與 `git grep --cached`。
- `knowledge_cli.py` 是 Project Knowledge public CLI；新增命令不可改寫既有 query JSON／error JSON。
- `test_query.py` 與 `test_behavior.py` 是現有 query／BDD owner surfaces；`.github/workflows/knowledge-portability.yml` 是跨平台 path filter、query 與 benchmark gate。
- `.gitattributes`、`.gitignore`、README 與 OPERATIONS 已是 binary／ignored-state／操作文件的既有維護入口。

## 4. First-party upstream provenance

本計畫查閱並以版本 1.0.4 的本地 binary 為實作來源；以下網址是可供 reviewer 重查的 Microsoft/tgrep 一手來源：

- README：<https://github.com/microsoft/tgrep>
- CLI search implementation：<https://raw.githubusercontent.com/microsoft/tgrep/main/tgrep-cli/src/search.rs>
- CLI flags／exit semantics：<https://raw.githubusercontent.com/microsoft/tgrep/main/tgrep-cli/src/main.rs>
- server implementation（本次排除）：<https://raw.githubusercontent.com/microsoft/tgrep/main/tgrep-cli/src/serve.rs>

## 5. Verification boundaries

Required：查詢必須唯讀且無額外 stderr；index 是 explicit command；Windows 才選 tgrep；Linux 不得執行 `.exe`；`rg` 永遠可用。

Proposed：tgrep adapter flags、state schema、index fingerprint、atomic publication、malformed-output fallback、Windows parity fixture、Linux rg-only assertion、README／OPERATIONS wording 與 path-filter CI。


## 6. Full-test runner revision evidence

# Full-test runner revision evidence

- Work ID: work-20260908-tgrep-index-4f6a8a9c
- Evidence source: implementation run 299d340e2614f68184015cf1ecdcb5686f210dde1727b07235dd2516f12d82b8, attempt-002, command sequence 008.
- Previous exact command: python -X utf8 -B -m unittest discover -s .agents/skills/project-knowledge/scripts -p "test_*.py"
- Previous result: exit 1; 105 tests started; errors=152; skipped=0.
- Previous stdout: 0 bytes, SHA-256 e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855.
- Previous stderr: 109359 bytes, SHA-256 330fd08af61a48d357042b8eaed46088eb284f6d29f2542627e0becd24bc3f5f.
- Failure class: direct unittest discovery bypassed the existing full-suite fixture initialization; representative errors reported missing scenario_function and fixture_root.
- Existing runner contract: run_full_suite.py accepts --scope all, --profile local, --fixture-root, --jobs and --evidence-root; it creates a disposable fixture root, schedules the owner suites, emits knowledge-suite-report/v1, and writes validation-evidence/v1.
- Revised exact command: python -X utf8 -B .agents/skills/project-knowledge/scripts/run_full_suite.py --scope all --profile local --fixture-root .knowledge-test-tmp/fixtures --jobs 1 --evidence-root .knowledge-test-tmp/evidence
- Binding: the governed executor sets IMPLEMENTATION_READY_PAYLOAD_SHA256 to the current Ready handoff payload before execution. The command stays free of a circular literal digest.
- Scope classification: global-baseline, because CMD-TEST-FULL-001 is a full validation command and the new execution baseline applies to every work package.
