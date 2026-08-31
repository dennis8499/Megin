<!-- authority: execution-quality -->

# 實作執行品質契約

本文件只做二元檢查；規則分別由 [Preflight／Ledger](preflight-and-ledger.md)、[Orchestrated Delivery](orchestrated-delivery.md)、[Resume／Revision](resume-and-revision.md)、[Greenfield Bootstrap](greenfield-bootstrap.md)、[BDD／TDD](bdd-tdd-loop.md)、[Reviewer](reviewer-contract.md)與[狀態／交付](delivery-protocol.md)擁有。每格必須有原始 evidence ref；缺少即 `Fail`。

## Preflight

| 檢查 | Pass |
|---|---|
| Ready contract | schema、approval／digest、artifacts／sources hashes、contracts／commands／DAG／impact 與 base binding 全部成立 |
| Workspace | fresh Reviewer capability、linked non-primary worktree、branch、dirty-state、tools 與 side-effect probes 全部成立；若使用 orchestrated requirements 例外，`delivery-run/v1`、Work ID、generation、核准 evidence、path／SHA 與 handoff `kind: spec` binding 全部相同 |
| Ledger identity | host-temp root、repo／worktree／run IDs、atomic binding 與 resume lookup 全部可重算；競爭者沒有 record |
| Baseline | 每個適用 Observed command fresh 通過 success／completeness，failure／skipped 為零；Proposed absence evidence 有效 |
| Zero-write gate | 產品、測試、dependencies、Ready、orchestrated requirements、秘密與外部狀態 hashes 不變 |

## BDD／TDD 與 WP

| 檢查 | Pass |
|---|---|
| Slice evidence | 每個新增行為依序有公開-seam BDD red、inner TEST red／green／refactor-green、BDD／related green |
| Red integrity | 錯誤 red 沒有 production diff；existing-green 有 coverage 且沒有無來源行為 |
| Bootstrap | 適用 `BOOT-*` 只含核准 shape 且 sentinel／oracle 證據成立；不適用時 red 前 production 不變 |
| Ordering | scenario／WP 依 slice order／DAG，commands、追溯與完成證據齊全後才 `Verified` |
| Scope | tracked／unignored diff 只含 plan 範圍；Ready、秘密、無關檔案、Git 與外部狀態邊界成立 |

## Verification、Review 與收斂

| 檢查 | Pass |
|---|---|
| Main verification | 全部 full commands `passed`；任何修正具有合法 Fixing 與 WP invalidation evidence |
| Snapshot | `implementation-snapshot/v1` 可重算並涵蓋 Ready／sources、base／HEAD、tracked diff 與 unignored files |
| Fresh review | attestation、獨立 commands、逐義務 coverage、raw refs、findings 與 stable keys 符合 `implementation-review/v1` |
| Verdict | APPROVED 沒有 blocking finding 或未通過 command；advisory、failed／blocked／not_run 均依契約表達 |
| Terminal order | Reviewer 與主代理的 before／after snapshots 相同，report 保存後才 append `Complete` |
| Ledger continuity | state／WP histories、commands、diffs、reviews、breaker、resume 與 revision attempts 都可重現且 append-only |
| Revision／breaker | WP-local／global 分流正確；stable counters 在指定門檻停止，未提前或延後 |
| BUG verification | BUG plan有正確regression red→green與create-only `bug-verification/v1`；implementation verdict與BUG result分開。verified具原始症狀pre／post，partial具核准proxy、殘餘風險與follow-up，failed不可Complete |
| Discovered BUG | current-scope／affecting-current-work／unrelated分流正確；不順手修unrelated，pending evidence在review／terminal前materialize且全域inbox不覆寫 |

## 判定

- `Pass`：所有適用格為真，且 terminal ordering 後為 `Complete`。
- `Fail`：記錄最早失敗格、authority 與 evidence，依唯一狀態機修正或終止。
