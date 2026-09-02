# BUG Assessment：bug-knowledge-candidate-publish-overwrite

- BUG ID：`bug-knowledge-candidate-publish-overwrite`
- Revision：1
- Verdict：`confirmed`
- Severity：`high`
- Relation：`current-scope`
- Source Work：`work-20260831-project-knowledge-system-19202d78`
- Disposition：`current-run`

## Observed／Expected／Impact

- Observed：`_persist_candidate` 在最後安全檢查後以 `os.replace(staging, final)` 發佈；Linux 允許它取代競爭者剛建立的同名空目錄，Windows 則拒絕，形成資料遺失與平台差異。
- Expected：Candidate identifier 的 commit boundary 必須使用原子 create-only publish；若任何競爭者先占用 final name，回 `CANDIDATE_EXISTS` 並完整保留既存 entry。
- Impact：sealed Candidate registry 的獨立 concurrent state 可被覆蓋，破壞 immutable identifier、審查綁定與 Windows／Linux 一致性。
- Symptom oracle：競爭者在最後檢查後建立同名空目錄時，sealer 必須失敗且該目錄 inode 保持不變。

## Reproduction／Amplification

- Status：`reproduced`
- 最小步驟：在 final commit boundary 建立同名空 Candidate directory，於 Windows 模擬 POSIX directory replace，並在 WSL 使用 Linux 原生 filesystem 執行同一 governance test。
- 結果：修正前 Windows 合成 POSIX probe 與 Linux 原生測試皆為 15 tests 中唯一失敗案例，原因是預期 `KnowledgeError` 但 sealer 成功返回；其餘 14 tests 通過。
- Evidence refs：`host-temp:evidence/bug-knowledge-candidate-publish-overwrite-diagnosis.json`、`host-temp:evidence/bug-knowledge-candidate-publish-overwrite-red.json`

## Compare／Trace

- Candidate bytes 先在隱藏 staging directory 完整建立並 stable-read；缺口只在 staging 到 final 的 publish primitive。
- `os.replace` 在 Windows 對既存 directory fail、在 Linux 可取代既存空 directory，因此同一個 safety contract 產生不同結果。
- 既有 pre-check／post-check 無法消除 check-to-publish 競態；必須由 kernel no-replace primitive 在 commit boundary 保證。

## Hypotheses

根因已由 reviewer WSL probe、Windows 合成 POSIX red 與 Linux 原生 red 交叉確認，無開放假設。

## Root cause confidence

- Status：`confirmed`
- Confidence：`high`
- Summary：Candidate directory 發佈錯用允許 POSIX replacement 的 `os.replace`，而非跨 Windows／Linux 的原子 create-only rename。

## Risks／Safety

- Security／privacy／data risk：否（已使用不含敏感資料的隔離 registry fixture）。
- Redacted summary：不適用。
- Secure evidence refs：無。
- Named human reviewer：無。

## Disposition 與下一步

- Disposition：`current-run`；直接屬於 WP-002／NFR-002／NFR-008／AC-017。
- Next falsifiable action／owner：Implementation executor 以 Windows no-replace rename 與 Linux `renameat2(RENAME_NOREPLACE)` 取代 directory replace，缺少安全 primitive 時 fail closed，再重跑 Windows／Linux governance 與 full verification。
- 禁止聲明：尚未完成 fresh review；不得自動 commit／push／merge／deploy。
