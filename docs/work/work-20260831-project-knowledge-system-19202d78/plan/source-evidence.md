# 技術規劃證據快照：單一專案可信工程知識系統

- Candidate revision：`candidate-20260831-01`
- 擷取日期：2026-08-31（Asia/Taipei）
- 性質：`supporting`；保存本次規劃實際使用的 Observed／Required 證據與外部設計來源
- 安全：只含路徑、版本、雜湊、測試摘要與公開連結，不含秘密值或本機檔案內容全文

## 1. Git 與工作區基線

- Repository ID：`0c5534020993ce0e527ffefdd0bbbdf8e3e26138d3933defe22de1ed5ea2530c`
- Planning HEAD：`5ddfe8a73560dd6754b00aa6ce45a333449c4f32`
- Primary worktree porcelain-v1 `-z` status SHA-256：`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`（空 bytes；strict clean）
- 目前 tracked files：74。
- `rg --files .agents/skills/project-knowledge` 回傳無檔案，故新 skill、CLI、contracts 與測試皆為 Proposed。
- Repository root 未找到 `AGENTS.md`、README、package manifest、solution 或 application project；受影響產品是現有 `.agents/skills` 工作流本身。

## 2. 本地一手來源

| Path | SHA-256 | 本次使用事實 |
|---|---|---|
| `docs/work/work-20260831-project-knowledge-system-19202d78/requirements.md` | `66c641cc25c6833c4ce12ca10ecff491d36b190ed4edfe15f61a5c24601c7381` | 唯一 Ready 規格；定義 BR、FR、NFR、TR、AC 與核准邊界。 |
| `.gitignore` | `971c52a12de3c6ced85c32155a00eced180bb04e2627f9bf00a3ae273b325b38` | 第 484 行以 `docs/` 忽略所有正式文件；需做最小例外遷移。 |
| `.agents/skills/delivery-orchestrator/SKILL.md` | `201553272c324b94fce5ed36a7c32e35c39a1c8de693019609e78df85c7298b5` | 現有單一 Work ID、隔離 worktree 與 requirements→planning→implementation→complete 路由。 |
| `.agents/skills/delivery-orchestrator/references/delivery-run.schema.json` | `052b283cb14737c44364119c58764cc309eca53064ca1c090ac99030a7dc1146` | `delivery-run/v1` 目前無 knowledge phase／binding；schema 為 closed object。 |
| `.agents/skills/delivery-orchestrator/scripts/_delivery_record.py` | `32da97fdd725c6990288ff04f050321a8d0a1bd361ef10c46c7d204801e0bc0e` | Ready requirements／plan、Complete implementation、snapshot 與 review 的 fail-closed 驗證位置。 |
| `.agents/skills/delivery-orchestrator/scripts/_delivery_runtime.py` | `7aecf128718abd629700581178c8d5f5cc85890ebe62ed60fea4c0e9ee27290d` | 既有 canonical path、stable file read、atomic JSON、秘密與 symlink／reparse 防護可抽象沿用。 |
| `.agents/skills/requirements-discovery/SKILL.md` | `95e46211e40e3c68a5abe1cfd549b8d6412794104cee61d9d400524cf0c670b3` | 需求探索入口與 evidence-first interview 邊界。 |
| `.agents/skills/requirements-discovery/references/delivery-protocol.md` | `a55b2280dab5e89423993152234ceccefec8c2ad9c1c15e323368b25f401304b` | requirements Candidate 的完整展示、人工核准與 create-only 寫入規則。 |
| `.agents/skills/technical-planning/references/ready-plan.schema.json` | `c3e90430e69acb6a06795f1855ab6fd045281ce555627061bd877c00d3f5c13b` | `ready-plan/v1` 的 source／contract／command／WP／approval digest 契約；可加 optional knowledge binding 保持舊資料可讀。 |
| `.agents/skills/implementation-execution/SKILL.md` | `ac6a57e2535d79a7284d99ba4711519d423bb32014e42158deccba4d26888b80` | outside-in BDD、inner TDD、full verification 與 fresh read-only review 的現有執行入口。 |
| `.agents/skills/implementation-execution/references/execution-records.schema.json` | `001646122fe6b80cf099840a92c0d20746cee133f1aab7827cee464b8ab864d1` | 目前持久 execution evidence 位於 host temp，尚無 repo-side `implementation-outcome/v1` 或 knowledge snapshot。 |
| `.agents/skills/implementation-execution/references/delivery-protocol.md` | `5d91f08ba8f45eb6876767f86632acb18c0cb850359dafd077a7639b9ec9a655` | fresh review 後目前直接形成 Complete，需插入人工 knowledge gate。 |
| `.agents/skills/implementation-execution/references/reviewer-contract.md` | `ddb8b71143d2bf515bff168c70c3401ce88e532aafacb45a1f187874804bb1aa` | reviewer 必須 fresh、唯讀、重新執行命令並綁定 snapshot。 |
| `.agents/skills/bug-diagnosis/SKILL.md` | `37e5c4b131f755c8e85059d865a2c638f5b06d183dad2c2993c9d0d39e5bcd08` | BUG diagnosis 是唯讀 evidence 階段，不等同已修復結果。 |
| `.agents/skills/bug-diagnosis/references/assessment-contract.md` | `3540fd11bb16332bbe690df6d92b98365a0fb61e63406639a8acaed98a8c6272` | assessment 與後續 verification 分離，支援 partial／failed 語義。 |
| `.agents/skills/writing-great-skills/SKILL.md` | `8c38389dbcfdb3605690c5ce2fe0fa433e7a2f2371a7f1e697d080d81d15fdea` | 新 skill 應維持短入口、明確完成條件與按 branch 漸進揭露 references。 |

## 3. 執行環境與基線驗證

- Observed toolchain：Python `3.14.6`、Git `2.51.0.windows.1`、ripgrep `15.2.0`。
- 2026-08-31 從 repository root 以 `python -X utf8 -B` 執行四個 owner validators，全部輸出 `contracts: PASS`。
- 同次執行 `requirements-discovery` 8、`technical-planning` 7、`implementation-execution` 14、`delivery-orchestrator` 20 個 stdlib `unittest`，合計 49/49 通過、0 failed、0 skipped。
- 現有 behavior reports 證明本 repository 以 Python standard-library test harness 驗證 BDD/TDD 次序；沒有第三方 BDD runtime manifest。新方案因此延續 stdlib scenario registry，另提供獨立 discovery，不新增 production dependency。

## 4. Legacy bootstrap 證據

以下檔案存在 primary worktree，但因 `docs/` 規則被忽略，未出現在 delivery worktree。Bootstrap 只使用本節已 materialize 的狀態與 hash 證據，不假裝可在 delivery worktree 重新取得原 bytes。

| Primary-worktree path | SHA-256 | Observed 狀態 |
|---|---|---|
| `docs/requirements/2026-08-27-dotnet-10-todo-list.md` | `e5d24ba686b4600e79534ce639154edb0aec1335c6d92bcd3299a14143bc06dd` | Markdown 第 3 行為 `文件狀態：Ready`。可列入 raw-source catalog，但本次不逐條晉升內容。 |
| `docs/plans/2026-08-29-dotnet-10-todo-list/plan.md` | `4447636865a3fe9237bfb949ce3d810f14da11f1f1c55c9367866c9307f258c1` | Markdown 第 3 行為 `Candidate—Awaiting confirmation`。 |
| `docs/plans/2026-08-29-dotnet-10-todo-list/research.md` | `8d2ba43fb5152269cc24a68bf142b357d55e0bee4a7e5ce17c2414cfe6c79a5e` | Markdown 第 4 行為 `Candidate—Awaiting confirmation`。 |
| `docs/plans/2026-08-29-dotnet-10-todo-list/handoff.json` | `afe401167a15b67616a55d4ab6bc858b0e05e966b71e6dbf45ceb9d3f8131e38` | `approval.status` 與 artifact statuses 為 `Ready`。 |

Machine handoff 與同 bundle 的人類可讀 primary／supporting 狀態不能同時成立。依 `TR-003`，初始 bootstrap 必須建立 contested quarantine 記錄、保留四方 hash 與 locator、排除自動 context；不得以 JSON、時間或檔案類型自動勝出。

## 5. 上游設計來源（inspiration，不取代本規格）

- [Karpathy LLM Wiki gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)：採用 raw source、LLM 維護的 interlinked Markdown wiki、`index.md`／`log.md`、query／lint 與可選搜尋加速的分層想法；本案依使用者決策只採 Markdown + `rg`，不採資料庫。
- [mattpocock/skills](https://github.com/mattpocock/skills)：採用小而可組合的 skills、共享詞彙／ADR／研究捕捉及診斷與 TDD 分工；本案以單一 `project-knowledge` skill 暴露一致 vocabulary，再由四個 SDLC skills 呼叫。
- [obra/superpowers](https://github.com/obra/superpowers)：採用從需求澄清、隔離 workspace、計畫、TDD 到 review 的強制階段概念；本案保留現有 delivery orchestrator 並新增 knowledge completion gate。
- [Fission-AI/OpenSpec](https://github.com/Fission-AI/OpenSpec)：採用 explore／propose／apply／archive 的 artifact-guided 生命週期與「先同意再寫入」邊界；本案以 Candidate／Ready promotion 表達。
- [github/spec-kit](https://github.com/github/spec-kit)：採用 constitution／specify／plan／tasks／implement 的規格驅動追溯；本案不引入其 CLI，而把 knowledge retrieval／promotion 嵌入現有 requirements、planning、implementation、BUG 流程。

## 6. 平台一手契約

- [Python `subprocess`](https://docs.python.org/3/library/subprocess.html)：以 argument sequence、`shell=False` 呼叫 Git／`rg`，避免 shell quoting 與平台差異。
- [Python `pathlib`](https://docs.python.org/3/library/pathlib.html)、[`tempfile`](https://docs.python.org/3/library/tempfile.html) 與 [`os.replace`](https://docs.python.org/3/library/os.html#os.replace)：提供跨平台 path、host-temp staging 與單檔 atomic replacement；多檔 promotion 仍需 journal、rollback 與 recovery，不能宣稱 filesystem 具跨檔 transaction。
- [ripgrep GUIDE](https://github.com/BurntSushi/ripgrep/blob/master/GUIDE.md)：`--json` 提供可解析 match stream，預設遵守 ignore 規則並可用 glob 限定 canonical Markdown。
- [Git `ls-files`](https://git-scm.com/docs/git-ls-files)：`--cached --others --exclude-standard -z` 可建立 tracked 與未忽略 in-flight sources 的 eligibility set；query 仍須另做 path／symlink／hash 驗證。
- [Python `unittest`](https://docs.python.org/3/library/unittest.html)：可用 test IDs、fixtures 與 CLI 形成無新依賴的 focused／full 測試；獨立 scenario inventory 由 Proposed runner 補足。

## 7. 證據結論與邊界

- Required：唯一規範來源是本 Work ID 的 Ready requirements。
- Observed：現況為 skill-only repository、closed JSON contracts、host-temp run evidence、Git-ignored `docs/` 與通過的 stdlib contract tests。
- Proposed：`project-knowledge` skill、knowledge contracts、read-only retrieval、transactional promotion、repo-side implementation outcome、dual snapshots、delivery knowledge phase、Git path migration及初始 Wiki Candidate。
- 不宣稱：未執行 Proposed commands、未證明未來跨平台 CI 已綠燈、未將 legacy planning bundle 判為 Ready，也未在 Candidate 階段寫入 repository artifacts。
