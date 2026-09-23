# Review findings Red／Green

- Protected promises: only exact predeclared process records are excluded; review needs every command source; evidence paths cannot contain `.` or `..`; delivery compares staged Git blob identities with the accepted product manifest.
- Red: `review-fixes-red.log`, exit `1`, six assertions failed before the fixes.
- Green: `review-fixes-green.log`, exit `0`, 16 tests passed after the fixes.
- Staging comparison uses Git-normalized blob identities so line-ending filters produce the same bytes that a commit would contain.
