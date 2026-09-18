#!/usr/bin/env python3
"""Read-only UserPromptSubmit router for Megin v3."""

from __future__ import annotations

import json
import sys


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        payload = {}
    prompt = str(payload.get("prompt") or payload.get("user_prompt") or "")
    folded = prompt.casefold()
    if any(token in folded for token in ("explain", "review", "查詢", "說明", "檢視", "評估")) and not any(token in folded for token in ("implement", "build", "fix", "修正", "新增", "開發")):
        route = "read_only"
    elif any(token in folded for token in ("bug", "error", "regression", "錯誤", "異常", "失效")):
        route = "bug_diagnosis"
    else:
        route = "change_exploration"
    output = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": f"Megin v3 route hint: {route}. Explore codebase and Project Knowledge first; this hook never authorizes development.",
        }
    }
    print(json.dumps(output, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
