# Review 2 findings Red／Green

- Protected promises: structured writer/reviewer/acceptance identities and outcomes must be nonempty strings and must match exact lines in their hashed raw sources; command and exit-code fields likewise bind to raw command logs.
- Red: `review-2-fixes-red.log`, exit `1`; 22 tests ran and three bypass assertions failed because contradictory raw review/acceptance text and container-valued identities were accepted.
- Green: `review-2-fixes-green.log`, exit `0`; all 22 tests passed after claim locators and type checks were added.
- Isolated regressions also cover missing command output, changed output digest, stale per-command snapshot, a single `.` path segment, independent unstaged/untracked rejection and delivery audit fields.
