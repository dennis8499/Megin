from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path


def run(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        text=True,
        capture_output=True,
    )


with tempfile.TemporaryDirectory(prefix="megin-diff-check-") as temp:
    repo = Path(temp)
    run(repo, "init", "--quiet")
    config = ["-c", "user.name=megin-test", "-c", "user.email=megin-test@example.invalid"]
    (repo / "README.md").write_text("clean\n", encoding="utf-8")
    run(repo, "add", "README.md")
    run(repo, *config, "commit", "--quiet", "-m", "base")
    base = run(repo, "rev-parse", "HEAD").stdout.strip()
    (repo / "README.md").write_text("dirty  \n", encoding="utf-8")
    run(repo, "add", "README.md")
    run(repo, *config, "commit", "--quiet", "-m", "whitespace")
    head = run(repo, "rev-parse", "HEAD").stdout.strip()
    check = subprocess.run(
        ["git", "diff", "--check", f"{base}...{head}"],
        cwd=repo,
        text=True,
        capture_output=True,
    )
    assert check.returncode != 0, "base-to-head diff check unexpectedly passed"
    assert "trailing whitespace" in check.stdout.lower()
    print("base-to-head whitespace check rejected the fixture")
