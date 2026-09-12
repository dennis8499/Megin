# BUG 現況盤點與結案追蹤

- Work ID：work-20260912-bug-remediation-0e0ea628
- 驗證日期：2026-09-12
- Assessment：17 份文件，按 BUG ID 去重為 16 項（Critical 1、High 11、Medium 4）。
- Native Linux evidence bundle: validation/linux-native-6/index.json (native Linux ext4 clone; Python 3.13.15; Git 2.43.0; ripgrep 14.1.0; BDD-008/010/011/016 passed).
- Current execution attempt: attempt-2 (native Linux and Windows portability evidence rerun)
- Ready candidate：candidate-3
- 驗證 HEAD：9ca64837a9c519d324a5f36a28c3ab7eb6e479e8

## 結論

本輪沒有足夠證據把任何一項標為「修復已驗證」。目前盤點結果如下：

| 判定 | 數量 | 說明 |
|---|---:|---|
| 仍可重現 | 0 | 沒有完成原始症狀的獨立現行 reproduction；不代表沒有待修工作。 |
| 修復已驗證 | 0 | 尚未同時滿足原始症狀、回歸、完整驗證及獨立 review。 |
| 部分驗證 | 16 | Windows／Linux proxy 或 full suite 有通過，但仍缺原始 red→green、完整 native toolchain 或 reviewer 綁定。 |
| 證據不足 | 0 | 本輪沒有項目完全失去現行 proxy；Linux 項目仍因工具鏈與逐 BUG 綁定不足而不能結案。 |
| 待追蹤總數 | **16** | 16 部分驗證。這是目前不能結案的 BUG 數，不是宣稱 16 項都仍存在。 |

本輪已產生 16 份 bug-verification/v1 JSON。已核准的 handoff.json 沒有 bug_context，因此既有 semantic validator 無法將多 BUG 盤點綁成單一 BUG verification。依計畫，不改寫 handoff 或歷史 assessment；此契約缺口列入 WP-004 待辦。

## 逐項判定

每列的 assessment revision、hash、回歸契約、證據引用與下一步均在同列 verification JSON 中；本表只保留可快速重算的結論。

| # | BUG | Assessment | Severity | WP | 判定 | 現況／主要證據缺口 | Verification |
|---:|---|---|---|---|---|---|---|
| 1 | bug-knowledge-apply-commit-boundary-toctou | assessment-1 | Critical | WP-002 | 部分驗證 | Windows promotion／workflow 代理與完整測試通過；Linux 發布證據被 linked-worktree 環境阻擋。 | docs/bugs/bug-knowledge-apply-commit-boundary-toctou/verifications/work-20260912-bug-remediation-0e0ea628.json |
| 2 | bug-knowledge-apply-concurrent-state-loss | assessment-1 | High | WP-002 | 部分驗證 | promotion／workflow 與 full owner suite 通過；後寫入保留及 rollback ownership 尚缺雙平台現行證據。 | docs/bugs/bug-knowledge-apply-concurrent-state-loss/verifications/work-20260912-bug-remediation-0e0ea628.json |
| 3 | bug-knowledge-candidate-publish-overwrite | assessment-1 | High | WP-002 | 部分驗證 | promotion focused 與 full suite 通過；POSIX create-only collision 尚缺原生 Linux 現行證據。 | docs/bugs/bug-knowledge-candidate-publish-overwrite/verifications/work-20260912-bug-remediation-0e0ea628.json |
| 4 | bug-knowledge-outcome-create-only-toctou | assessment-1 + assessment-2 | High | WP-002 | 部分驗證 | workflow、BDD full 與 Windows 代理通過；revision 2 的 identity rollback 要求未能綁定。 | docs/bugs/bug-knowledge-outcome-create-only-toctou/verifications/work-20260912-bug-remediation-0e0ea628.json |
| 5 | bug-knowledge-promotion-retirement-read-failure | assessment-1 | High | WP-002 | 部分驗證 | promotion／workflow proxy 通過；RECOVERY_REQUIRED 與 journal／receipt 一致性尚缺雙平台證據。 | docs/bugs/bug-knowledge-promotion-retirement-read-failure/verifications/work-20260912-bug-remediation-0e0ea628.json |
| 6 | bug-knowledge-candidate-ancestor-redirect | assessment-1 | High | WP-003 | 部分驗證 | Delivery／promotion proxy 與 full suite 通過；ancestor junction／leaf swap 跨平台證據不完整。 | docs/bugs/bug-knowledge-candidate-ancestor-redirect/verifications/work-20260912-bug-remediation-0e0ea628.json |
| 7 | bug-knowledge-promotion-registry-component-validation | assessment-1 | High | WP-003 | 部分驗證 | promotion focused 與 governance／full suite 通過；component stable-read／create 跨平台證據不完整。 | docs/bugs/bug-knowledge-promotion-registry-component-validation/verifications/work-20260912-bug-remediation-0e0ea628.json |
| 8 | bug-linux-posix-path-classification | assessment-1 | Medium | WP-003 | 部分驗證 | Linux ext4 clone 的 Delivery BDD proxy 已通過；仍缺原生 Linux ripgrep 與逐 BUG owner contract 綁定。 | docs/bugs/bug-linux-posix-path-classification/verifications/work-20260912-bug-remediation-0e0ea628.json |
| 9 | bug-linux-delivery-posix-path-classification | assessment-1 | Medium | WP-003 | 部分驗證 | Linux ext4 clone 的 BDD-008／010／011 已通過；仍缺逐 BUG transition evidence 與原生 dependency。 | docs/bugs/bug-linux-delivery-posix-path-classification/verifications/work-20260912-bug-remediation-0e0ea628.json |
| 10 | bug-delivery-knowledge-formal-paths-bypass | assessment-1 | High | WP-003 | 部分驗證 | governance、Delivery focused、workflow 與 full suite 通過；缺逐 BUG red→green 與獨立 review 綁定。 | docs/bugs/bug-delivery-knowledge-formal-paths-bypass/verifications/work-20260912-bug-remediation-0e0ea628.json |
| 11 | bug-delivery-reviewer-identity-reuse | assessment-1 | High | WP-003 | 部分驗證 | review／governance／full suite 通過；缺持久化 fresh reviewer identity same-agent red evidence。 | docs/bugs/bug-delivery-reviewer-identity-reuse/verifications/work-20260912-bug-remediation-0e0ea628.json |
| 12 | bug-knowledge-page-closed-contract-lint | assessment-1 | High | WP-003 | 部分驗證 | governance、BDD full 與 owner suite 通過；缺 page／claim／source 三層逐項 red→green。 | docs/bugs/bug-knowledge-page-closed-contract-lint/verifications/work-20260912-bug-remediation-0e0ea628.json |
| 13 | bug-preliminary-review-ready-validation | assessment-1 | High | WP-003 | 部分驗證 | Ready／governance／full proxy 通過；handoff 無 bug_context，verification 無法通過既有 Ready semantic gate。 | docs/bugs/bug-preliminary-review-ready-validation/verifications/work-20260912-bug-remediation-0e0ea628.json |
| 14 | bug-bdd016-warm-query-tail | assessment-1 | Medium | WP-004 | 部分驗證 | benchmark 五 cold／五 warm 與 hash 曾通過；一次 Windows release capture 的 index_candidate=2.0487s 超過門檻。 | docs/bugs/bug-bdd016-warm-query-tail/verifications/work-20260912-bug-remediation-0e0ea628.json |
| 15 | bug-bdd020-first-cold-tail | assessment-1 | Medium | WP-004 | 部分驗證 | 50k／5k benchmark 五 cold、五 warm、hash、cleanup 有通過證據；缺 fresh reviewer 重測。 | docs/bugs/bug-bdd020-first-cold-tail/verifications/work-20260912-bug-remediation-0e0ea628.json |
| 16 | bug-bdd020-review-query-tail | assessment-1 | High | WP-004 | 部分驗證 | benchmark、query 與 full suite 通過；缺 reviewer profile 的五 cold／五 warm 獨立確認。 | docs/bugs/bug-bdd020-review-query-tail/verifications/work-20260912-bug-remediation-0e0ea628.json |

## 共通實作位置

- P0 交易／回滾：.agents/skills/project-knowledge/scripts/knowledge_promotion.py、knowledge_outcome.py、knowledge_workflow.py。
- P1 路徑：knowledge_query.py、knowledge_workflow.py、knowledge_delivery.py、.agents/skills/delivery-orchestrator/scripts/delivery_workspace.py。
- P1 契約：knowledge_governance.py、knowledge_delivery.py、knowledge_outcome.py、.agents/skills/implementation-execution/scripts/validate_contracts.py。
- P2 效能：knowledge_query.py、knowledge_benchmark.py、test_behavior.py。
- 本輪未修改上述 product／validator source；目前工作成果是逐項現況證據與待追蹤邊界，避免把歷史修復證據誤當結案。

## 驗證證據

- Evidence bundle：validation/baseline-1/index.json（11 passed、3 failed；包含完整原始 stdout/stderr）。
- Corrected AST bundle：validation/ast-2/index.json（1 passed；直接執行 .agents/**/*.py AST scan）。
- Native Linux evidence bundle: validation/linux-native-6/index.json (native Linux ext4 clone; Python 3.13.15; Git 2.43.0; ripgrep 14.1.0; BDD-008/010/011/016 passed).
- 通過：BDD discovery、promotion／delivery／governance／performance focused、BDD full（39/39）、workflow（45/45）、related governance（18/18）、full suite、contract validator、benchmark（50k files／5k pages）。
- 保留失敗：AST 初始 wrapper 的 shell quoting（已由 ast-2 補正）；一次 Windows release 的 BDD-016 index_candidate=2.0487s；Linux 初始 linked-worktree probe 與無 rg probe 均保留為環境失敗，後續 linux-native-5 以 shim 完成 proxy。
- Benchmark passing run 保留五次 cold、五次 warm、functional hash bae0d3eee98a4ba39967ca26e3b60fd1d2f5f1d781b7dca8e00b8d385c615f83；不覆蓋超標樣本。

## WP-004 結案門檻

1. 在具備原生 Linux ripgrep 的 native Linux checkout 完成兩個 Linux BUG 的 ordinary path／symlink／inspection-error 與 Delivery transition evidence。
2. 為每個 BUG 補原始 reproduction command、現行 post-fix oracle、red→green raw output；不得以成功重跑覆蓋超標或失敗樣本。
3. 修正或核准可表達多 BUG 的 Ready bug_context／assessment revision 契約，再執行 semantic validator。
4. 由不同 fresh reviewer identity 完成 preliminary/final review；在此之前，16 項均不得標為已結案。

## 執行環境事故紀錄

WSL Linux probe 曾因 linked worktree 的 Git 環境污染 delivery index／common config；已備份並以精確目標恢復，未刪除 product files，primary repo 與 delivery worktree 的既有狀態已恢復。後續 probe 已取消 GIT_DIR／GIT_WORK_TREE，但仍無法在此 linked worktree 取得完整 native Linux toolchain 結果。

## 責任角色

- WP-002：Implementation owner；負責 P0 regression 與 recovery ownership。
- WP-003：Platform／Delivery owner；負責 native Linux worktree、path safety 與 Ready consumer。
- WP-004：Performance owner + independent reviewer；負責固定 workload、完整樣本與結案核對。
## Continuation update (attempt-2)

- Native Linux release evidence is now complete and independently bundle-verified: validation/linux-native-6/index.json.
- Windows release rerun is bundle-verified: validation/windows-native-2/index.json; BDD-008/010/011/016 passed.
- The previous Windows BDD-016 index_candidate sample of 2.0486980000005133 seconds remains preserved and prevents an unconditional performance pass.
- The approved handoff still has no bug_context; representative semantic validation remains blocked with BUG verification: Ready plan has no bug_context.
- A different fresh reviewer session and its preliminary/final review artifacts are still required. The 16 BUGs therefore remain partial/unresolved for tracking.
