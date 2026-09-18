#!/usr/bin/env python3
"""Read-only SessionStart context for Megin v3.

The hook reports routing capability and an existing resumable state when the
host supplies a repository path.  It never approves, creates a branch, edits a
file, or invokes the delivery controller.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        payload = {}
    repo_value = payload.get("cwd") or payload.get("repo") or os.getcwd()
    repo = Path(str(repo_value)).expanduser().resolve()
    context = [
        "Megin v3 is active; hooks are read-only routing hints.",
        "Classify the request before mutating a repository.",
        "Require one explicit plan approval, then independent task reviews, verify, and human acceptance before finish.",
    ]
    if (repo / ".git").exists():
        try:
            result = subprocess.run(["git", "status", "--porcelain"], cwd=str(repo), text=True, capture_output=True, timeout=10, check=False)
            context.append("The current worktree is dirty; preserve existing changes and do not infer ownership." if result.stdout.strip() else "The current worktree is clean.")
        except (OSError, subprocess.SubprocessError):
            context.append("Git status could not be checked; keep the session read-only until it is resolved.")
    output = {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": " ".join(context)}}
    print(json.dumps(output, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
