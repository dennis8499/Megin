# 將 tgrep.exe 整合至 Project Knowledge 搜尋流程

## requirements-claim

把 repository 根目錄已納入版本控制的 Windows-only `tgrep.exe` v1.0.4 作為 Project Knowledge 的可選搜尋加速器。一般 worktree regex／fixed-string 查詢在 Windows 且有有效 on-disk `.tgrep` index 時使用 tgrep；其他情況無聲回到既有 `rg`。`rg` 仍是必要依賴與可靠 fallback。
