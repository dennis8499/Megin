# Fresh independent review 2

- Context: `/root/independent_quality_review_2` (fresh read-only; not writer)
- Reviewed protected snapshot: `dd7408232e30d37fa38fba0a83f8788c0763b63ec7590058829bdf284cfb537d`
- Verdict: `CHANGES_REQUIRED`

## Raw reviewer result

CHANGES_REQUIRED

- **高｜`quality_gate.py:185,333,348`**：Gate 只核對原始 review／acceptance 檔案的 SHA-256，卻獨立信任 `quality.json` 中的 `verdict`、`context`、`version`。在臨時測試 repo 中已重現：
  - 引用檔內容為 `CHANGES_REQUIRED`，但 evidence 宣稱 `verdict: APPROVED` 時，`acceptance` 仍 exit `0`。
  - 引用檔內容為 `REJECTED`，且 `acceptance.version` 是 JSON object 時，`delivery` 仍 exit `0`。
  - writer／reviewer context 分別使用不同的非字串容器也能通過。

  這違反 `quality-gates.md:13,26-27` 的實際原始裁決與明確驗收承諾。應將裁決、context、Work ID、version、snapshot 綁到可機器核對的原始來源欄位或精確 locator，並要求非空字串型別。現有 16 tests 不會在這些行為失效時失敗。

- **中｜`test_quality_gate.py:205`**：review-1 四項修正已存在，但需要隔離測試：
  - review gate 應分別阻擋缺 output、變更 output digest、stale per-check snapshot；
  - canonical path 應另外覆蓋 `.`；
  - delivery 應分開保護 staged blob mismatch、unstaged/untracked，並核對 audit fields。

分支、HEAD、base 與受保護快照符合交接，所有路徑在核准範圍內且無 staged 檔案。六項本機命令 fresh exit `0`，ZIP 與 12 個 Skills 位元組一致；21 個 evidence references／locator 與 24 個 Test/Test2 來源 manifest 項目匹配。

限制：GitHub CI 未執行；未重新執行 Test/Test2 或 Docker 情境；未在實際 repository staging。審查未修改、暫存或提交檔案。
