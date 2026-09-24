# 完成前驗證

- Work ID: `work-20260924-remote-aware-merge`
- snapshot: `1838932d4582a5007f657f86071fe6b1e4f7cadb1a0145812007de4eb660c065`
- branch: `feature/work-20260924-remote-aware-merge`
- base commit: `86c727916d03835ea4821d0f34a69ba0d0433fe1`
- independent review: `APPROVED`，見 `evidence/review.md`

## 自動檢查

| 命令 | 結果 |
| --- | --- |
| `python -X utf8 -B tests/group-workspace/test_group_workflow.py` | exit 0；15 tests，0 failed，0 skipped；105.535s |
| `python -X utf8 -B tests/quality-gates/test_quality_gate.py` | exit 0；22 tests，0 failed，0 skipped；71.068s |
| `python -X utf8 -B tests/requirements-discovery/test_rules.py` | exit 0；規則回歸測試通過 |
| `python -X utf8 -B tests/requirements-discovery/check_materials.py` | exit 0；11 cases、6 source snapshots 與 fixtures 通過 |
| `python -X utf8 -B tests/requirements-discovery/test_materials.py` | exit 0；材料檢查器回歸測試通過 |
| `python -X utf8 -B .agents/skills/megin/scripts/validate_skills.py --archive megin-skills.zip` | exit 0；12 個 Megin Skills 通過 |
| `git diff --check` | exit 0；無 whitespace 錯誤 |
| `python -X utf8 -B .agents/skills/megin/scripts/quality_gate.py check --repo . --work-id work-20260924-remote-aware-merge --gate review` | exit 0；`ok: true`，snapshot 與本紀錄一致 |
| `python -X utf8 -B .agents/skills/megin/scripts/quality_gate.py check --repo . --work-id work-20260924-remote-aware-merge --gate acceptance` | exit 0；`ok: true`，使用者已接受相同 snapshot |

封裝與 Group 安裝另外逐一比對 34 個 ZIP 檔案，Group 根目錄的 `.agents/skills/` 內容完全一致。Python AST 解析也通過。

## 人工驗收

使用者已以 `acceptance-1` 接受先前快照 `65d7b337efd93a47af54dff683d703954eb84ea21e540ce4491c208747d8b3d8`，並確認 SCN-007：從 Group root 啟動 Codex 後，`/skills` 列出 12 個 Megin Skills。該回覆保留於 `evidence/acceptance.md`；測試檔尾端空行修正產生新快照 `1838932d4582a5007f657f86071fe6b1e4f7cadb1a0145812007de4eb660c065`，需重新接受此快照後交付。

交付前以 `git ls-remote --exit-code origin refs/heads/main` 確認遠端 SHA `86c727916d03835ea4821d0f34a69ba0d0433fe1`，與核准基線及本機 `main` 一致。

## 知識檢視

結果：`no-change`。計畫未核准額外的 canonical knowledge promotion 範圍；本次核准的 Skills、參照、README 與 OPERATIONS 就是 Megin 的 canonical source。依 `rg --files -g '*knowledge*' -g '!docs/work/**' -g '!*.zip'` 搜尋，Repo 中沒有 Work ID 以外的獨立 knowledge 檔案。既有 Work ID 的 knowledge notes 保持歷史紀錄，不將其舊 source digest 當成本次現況依據，也未改寫。

下列來源由目前工作樹重新讀取，雜湊作為本次知識結果的來源定位；確定性均為 `confirmed`。摘要與行為細節以這些 canonical source 及其回歸測試為準；沒有互相衝突或待提升的 claim。

| 來源 | SHA-256 |
| --- | --- |
| `.agents/skills/megin/SKILL.md` | `850d1fab2c19c73a218f9ac7b53e6011b485d97fe6e44dd342fce8dcfccac91a` |
| `.agents/skills/megin-behavior-contract/SKILL.md` | `429206282e308f293720029206711530bc9c9fe0ccf8c6820e2e3f8922c819f2` |
| `.agents/skills/megin-bug-diagnosis/SKILL.md` | `fb0424e41526d719905b09393dfa9fd96bc66183472f46990530578667235f3d` |
| `.agents/skills/megin-code-review/SKILL.md` | `4d63da5d0b53ab05922a29a3cb7ba0682705ee3a5e3a90229e25269272bdc48c` |
| `.agents/skills/megin-finishing-delivery/SKILL.md` | `6c422f0d72e83d063a7a11c67bad301aa4428fe22bcf4ab9d42dc50f75fc5da1` |
| `.agents/skills/megin-human-acceptance/SKILL.md` | `8e7b4e0be869e928a56e413d60365ea04be7ef5b8bc0c4dc372fcc24e7dca190` |
| `.agents/skills/megin-implementation-execution/SKILL.md` | `69138216fddce8b92356c1225325bd19a3f96d09848b2b1a3d819fdd70426455` |
| `.agents/skills/megin-project-knowledge/SKILL.md` | `93596b3daf6f6e7650117f952ccaca95f3ffe5bf5c33e835336c5f1ea95fa52b` |
| `.agents/skills/megin-requirements-discovery/SKILL.md` | `53bbe3f8108d2e169fb173beaff11c5e5e36ed0bd44294b2512090b3d3edad64` |
| `.agents/skills/megin-technical-planning/SKILL.md` | `e0c5941c0c42d21fe2721c24096a1380687b6b521d4c744de119ac131279e5ec` |
| `.agents/skills/megin-test-driven-development/SKILL.md` | `26e8b519e02a9d1d8eefc3f0d64a1dd446c34b888d69baf03efda6e7ab93ba25` |
| `.agents/skills/megin-verification-before-completion/SKILL.md` | `aeb71f83ac7b8f688cee97fa843f9b9f974ea10d2aff253d07e373aa555b9165` |
| `.agents/skills/megin/references/branch-policy.md` | `ebece4b39a34ba819ca1d9552a31a6ed90baa2df217d7d266fd578030e7c8c96` |
| `.agents/skills/megin/references/group-workspace.md` | `a400fc5ab31f648b8014b59c17d251af552f55a132f4cdbf5d24259bd749718d` |
| `.agents/skills/megin/references/quality-gates.md` | `4b2293e2678b154d3075398e2f5cae1ad2dc3dbdc15c2598ad42089901e5f140` |
| `.agents/skills/megin/references/workflow-record.md` | `af8ecb8c9fa28558068b818bd09c9c5eaad1f1cbe7fe7175508791841fa6e187` |
| `README.md` | `ec250e79879fad2526b955fe848d391c85f2e06231de79ebb63b9433bb2d1993` |
| `OPERATIONS.md` | `f260b816d02dc0dcda73047dba4878d09add7dfaaa06f09c7420c63749705974` |
| `.agents/skills/megin/scripts/quality_gate.py` | `73d84c6aad3b7af7f4512f8249c687900732a68b410f5560e66c5da2ad2d5806` |
| `tests/group-workspace/test_group_workflow.py` | `21e03cb38ff98892a929fe8bbd4f76dfe266dfea45e380d675ca92ceaeb2f1c6` |
