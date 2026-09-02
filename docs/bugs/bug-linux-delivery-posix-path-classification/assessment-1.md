# BUG Assessment：bug-linux-delivery-posix-path-classification

- BUG ID：`bug-linux-delivery-posix-path-classification`
- Revision：1
- Verdict：`confirmed`
- Severity：`medium`
- Relation：`current-scope`
- Source Work：`work-20260831-project-knowledge-system-19202d78`
- Disposition：`current-run`

## Observed／Expected／Impact

- Observed：native Linux full suite 的前 16 個 subcommands 全部通過，但 `TEST-OWNER-DELIVERY-WORKSPACE` 在 50 tests 中出現 5 failures、20 errors；普通 artifact path 被拒為 `INVALID_PATH` symlink／reparse point。
- Expected：普通 POSIX 路徑可通過 stable no-follow 驗證，真正 symlink 仍 fail closed，Delivery tests 的預期 transition/error oracle 不被 path false-positive 截斷。
- Impact：阻斷本次 Linux full-suite 與 release gate；Windows 17-command full suite仍通過。
- Symptom oracle：同一 Linux full suite 的 17 個 subcommands 全部 exit 0，Delivery workspace tests 50/50 通過；普通目錄分類 false，真正 symlink 分類 true。

## Reproduction／Amplification

- Status：`reproduced`
- 最小步驟：在 native Linux validation copy 執行 full suite；另對普通 temporary directory 呼叫 Delivery `_is_reparse_path`。
- 固定條件與樣本：Python 3.12.3、POSIX、同一 product snapshot；full suite 1/1 重現，低階 probe 1/1 重現。
- Evidence refs：`host-temp:evidence/bug-linux-delivery-posix-path-classification-diagnosis.json`

## Compare／Trace

- 最近正常／目前異常：Windows full suite 的相同 Delivery workspace tests 50/50 通過；Linux 進入 artifact binding 即被 path false-positive 截斷。該 helper 行為在 HEAD 已存在，但 Delivery record 同時是目前 WP-003 直接修改來源，且本次已核准 Linux full suite 使其成為 current-scope blocker。
- 最小案例：普通 Linux temporary directory 不是 symlink，`lstat()` 不提供 `st_file_attributes`，原 helper 仍回傳 true。
- Data／control flow：`_verify_repo_file` → `_has_reparse_component` → `_is_reparse_path` → 缺少 Windows-only member 產生 `AttributeError` → 與真正 inspection `OSError` 共用 unsafe 分支 → 提前回 `INVALID_PATH`。

## Hypotheses

根因已由單一變因 pre/post probe 確認，無開放假設。

## Root cause confidence

- Status：`confirmed`
- Confidence：`high`
- Summary：只在 process memory 將缺少 platform-specific member 解讀為零，Delivery 的 100 個 discoverable tests 即全部通過；真正 `OSError` 仍回 unsafe，排除 transition、fixture 與 Git 環境為共同根因。
- Evidence refs：`host-temp:evidence/bug-linux-delivery-posix-path-classification-diagnosis.json`

## Risks／Safety

- Security／privacy／data risk：否
- Redacted summary：不適用
- Secure evidence refs：無
- Named human reviewer：無

## Disposition 與下一步

- Disposition：`current-run`；修正履行既有 NFR-002／AC-016 與 path safety contract，不改 Requirements、Plan、schema、公開介面或依賴。
- Next falsifiable action／owner：Implementation executor 使 WP-003 再次失效，保存 regression red，只修正 Delivery POSIX attribute 分類，重驗 WP-003、續跑 WP-004 native Linux full suite與正式 review。
- 禁止聲明：尚未修復；不得自動建立 Work／issue／commit／push／merge／deploy／通知。
