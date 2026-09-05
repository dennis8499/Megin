# 統一 Skill 入口與流程授權技術規劃

## planning-claim

- 選定方案與理由：在現有 Delivery facade 新增唯讀 `authorize` seam，以持久化 run 與實際 Git／worktree 證據授權單一 active phase；child metadata 只改善發現性，不作為安全邊界。
