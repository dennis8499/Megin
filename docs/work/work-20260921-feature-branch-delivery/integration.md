# 本機整合證據：feature 分支與人工審核後本機整合

- base_branch: `main`
- feature_branch: `feature/work-20260921-feature-branch-delivery`
- merge_strategy: `--no-ff`
- feature_implementation_commit: `7c2fbdc6ad0c49b3dc4a4c5b31cd4f623d8bc891`
- feature_delivery_evidence_commit: `4d472ef6ad0c49b3dc4a4c5b31cd4f623d8bc891`
- merge_commit: `c814ad33864351dd1e806093735f9c7d6d58b04c`

## 命令結果

| 檢查 | 結果 |
| --- | --- |
| `git merge --no-ff feature/work-20260921-feature-branch-delivery -m "Merge feature/work-20260921-feature-branch-delivery"` | 成功，使用 `ort` strategy |
| `git show -s --format='%H%n%P%n%s' HEAD` | merge SHA `c814ad33864351dd1e806093735f9c7d6d58b04c`；父提交 `44e29147209099368d8eed8cc773582148c26eaa`、`4d472ef6ad0c49b3dc4a4c5b31cd4f623d8bc891`；訊息為 `Merge feature/work-20260921-feature-branch-delivery` |
| `git merge-base --is-ancestor feature/work-20260921-feature-branch-delivery main` | 通過；feature tip 是 main 的祖先 |
| `git diff --exit-code main feature/work-20260921-feature-branch-delivery` | 通過；merge 後產品樹一致 |
| `git branch --list feature/work-20260921-feature-branch-delivery` | 通過；feature branch 保留 |
| `git diff --check` | 通過；無 whitespace error |

合併後追加的本檔案與 workflow 最終狀態屬於純流程證據，與已驗收產品內容分開辨識；沒有 amend
merge commit，也沒有推送、PR、部署、branch 刪除或 worktree 清理。
