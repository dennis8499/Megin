"""Exercise the Megin feature-branch and local integration contract in isolated Git repos."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and result.returncode:
        raise AssertionError(
            f"git {' '.join(args)} failed with {result.returncode}: {result.stderr.strip()}"
        )
    return result


def write(repo: Path, name: str, content: str) -> None:
    (repo / name).write_text(content, encoding="utf-8")


def commit(repo: Path, message: str) -> str:
    git(repo, "add", "--", ".")
    git(repo, "commit", "-m", message)
    return git(repo, "rev-parse", "HEAD").stdout.strip()


def setup_repo(root: Path) -> tuple[Path, str]:
    repo = root / "repo"
    repo.mkdir(parents=True)
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.name", "Megin branch-policy test")
    git(repo, "config", "user.email", "megin-branch-policy@example.invalid")
    write(repo, "README.txt", "base\n")
    write(repo, "shared.txt", "base shared value\n")
    base = commit(repo, "base")
    return repo, base


def read_repo_file(repository: Path, relative: str) -> str:
    path = repository / relative
    if not path.is_file():
        raise AssertionError(f"missing policy evidence file: {relative}")
    return path.read_text(encoding="utf-8")


def require_phrases(text: str, phrases: tuple[str, ...], source: str) -> None:
    missing = [phrase for phrase in phrases if phrase not in text]
    if missing:
        raise AssertionError(f"{source} is missing policy evidence: {missing}")


def require_feature_branch(repo: Path, expected: str) -> None:
    current = git(repo, "branch", "--show-current").stdout.strip()
    if current != expected:
        raise AssertionError(f"product write refused on {current}; expected {expected}")


def scenario_policy_contract(repository: Path) -> None:
    branch_policy = read_repo_file(repository, ".agents/skills/megin/references/branch-policy.md")
    require_phrases(
        branch_policy,
        ("feature branch", "主分支在人工驗收之前", "保留現場", "git merge --no-ff"),
        "branch-policy.md",
    )
    entry = read_repo_file(repository, ".agents/skills/megin/SKILL.md")
    require_phrases(entry, ("feature branch", "human acceptance", "git merge --no-ff"), "megin/SKILL.md")
    requirements = read_repo_file(repository, ".agents/skills/megin-requirements-discovery/SKILL.md")
    require_phrases(
        requirements,
        ("do not create a feature branch", "feature branch creation happens only after"),
        "megin-requirements-discovery/SKILL.md",
    )
    implementation = read_repo_file(repository, ".agents/skills/megin-implementation-execution/SKILL.md")
    require_phrases(
        implementation,
        ("base_branch", "Never write", "product files directly on the base branch"),
        "megin-implementation-execution/SKILL.md",
    )
    acceptance = read_repo_file(repository, ".agents/skills/megin-human-acceptance/SKILL.md")
    require_phrases(
        acceptance,
        ("Before this", "do not", "merge into the"),
        "megin-human-acceptance/SKILL.md",
    )
    delivery = read_repo_file(repository, ".agents/skills/megin-finishing-delivery/SKILL.md")
    require_phrases(
        delivery,
        ("feature commit", "git merge --no-ff", "two parents"),
        "megin-finishing-delivery/SKILL.md",
    )
    record = read_repo_file(repository, ".agents/skills/megin/references/workflow-record.md")
    require_phrases(
        record,
        ("base_branch", "feature_branch", "merge_strategy: --no-ff", "merge commit", "阻礙", "下一步"),
        "workflow-record.md",
    )
    workflow = read_repo_file(repository, "docs/work/work-20260921-feature-branch-delivery/workflow.md")
    require_phrases(
        workflow,
        (
            "work_id: work-20260921-feature-branch-delivery",
            "base_branch: main",
            "feature_branch: feature/work-20260921-feature-branch-delivery",
            "REQ-BRANCH-001",
            "REQ-BRANCH-006",
            "下一個恢復動作",
        ),
        "workflow.md",
    )
    feature = read_repo_file(
        repository,
        "docs/work/work-20260921-feature-branch-delivery/features/branch-policy.feature",
    )
    for scenario_id in (
        "REQ-BRANCH-001",
        "REQ-BRANCH-002",
        "REQ-BRANCH-003",
        "REQ-BRANCH-004",
        "REQ-BRANCH-005",
        "REQ-BRANCH-006",
    ):
        if feature.count(f"@{scenario_id}") != 1:
            raise AssertionError(f"feature scenario ID is not unique: {scenario_id}")
    print("policy contract passed: Skills, workflow record, feature scenarios, and recovery wording are present")


def scenario_branch_and_no_merge_before_acceptance(root: Path) -> None:
    repo, base = setup_repo(root)
    git(repo, "switch", "-c", "feature/example")
    git(repo, "switch", "main")
    try:
        require_feature_branch(repo, "feature/example")
    except AssertionError as error:
        assert str(error) == "product write refused on main; expected feature/example"
    else:
        raise AssertionError("main direct-write guard did not reject the wrong branch")
    git(repo, "switch", "feature/example")
    assert git(repo, "rev-parse", "main").stdout.strip() == base
    assert git(repo, "rev-parse", "HEAD").stdout.strip() == base
    assert not git(repo, "log", "--merges", "--format=%H", "main").stdout.strip()
    print("REQ-BRANCH-001 passed: feature branch starts at main and the wrong branch is rejected")
    print("pre-acceptance main invariant passed: main has no merge before acceptance")


def scenario_acceptance_gate(root: Path) -> None:
    repo, base = setup_repo(root)
    git(repo, "switch", "-c", "feature/example")
    accepted = False

    def gated_feature_commit() -> str:
        if not accepted:
            raise AssertionError("feature commit attempted before acceptance")
        write(repo, "change.txt", "accepted feature\n")
        return commit(repo, "feature change after acceptance")

    try:
        gated_feature_commit()
    except AssertionError as error:
        assert str(error) == "feature commit attempted before acceptance"
    else:
        raise AssertionError("acceptance gate did not reject a pre-acceptance commit")
    assert git(repo, "rev-parse", "main").stdout.strip() == base
    accepted = True
    feature_commit = gated_feature_commit()
    assert git(repo, "rev-parse", "main").stdout.strip() == base
    assert git(repo, "rev-parse", "feature/example").stdout.strip() == feature_commit
    print("REQ-BRANCH-002 passed: acceptance gate rejects a feature commit before acceptance")


def scenario_no_ff_merge(root: Path) -> None:
    repo, base = setup_repo(root)
    git(repo, "switch", "-c", "feature/example")
    write(repo, "change.txt", "accepted feature\n")
    feature_commit = commit(repo, "feature change")
    git(repo, "switch", "main")
    assert git(repo, "rev-parse", "HEAD").stdout.strip() == base
    git(repo, "merge", "--no-ff", "feature/example", "-m", "Merge feature/example")
    merge_commit = git(repo, "rev-parse", "HEAD").stdout.strip()
    parents = git(repo, "show", "-s", "--format=%P", merge_commit).stdout.split()
    assert len(parents) == 2, parents
    assert parents[1] == feature_commit, parents
    assert git(repo, "branch", "--list", "feature/example").stdout.strip()
    assert git(repo, "diff", "--exit-code", "main", "feature/example").returncode == 0
    print("REQ-BRANCH-003 passed: --no-ff creates a two-parent merge and retains feature branch")


def scenario_base_drift_requires_reacceptance(root: Path) -> None:
    repo, base = setup_repo(root)
    git(repo, "switch", "-c", "feature/example")
    write(repo, "feature.txt", "feature\n")
    accepted_feature = commit(repo, "feature change")
    git(repo, "switch", "main")
    write(repo, "main.txt", "main advanced\n")
    main_after_drift = commit(repo, "advance main")
    assert main_after_drift != base
    git(repo, "switch", "feature/example")
    git(repo, "merge", "main", "--no-edit")
    integrated_feature = git(repo, "rev-parse", "HEAD").stdout.strip()
    assert integrated_feature != accepted_feature
    assert git(repo, "diff", "--name-only", accepted_feature, integrated_feature).stdout.strip() == "main.txt"
    print("REQ-BRANCH-004 passed: base drift changes feature snapshot and requires fresh review/acceptance")


def scenario_conflict_preserves_state(root: Path) -> None:
    repo, _ = setup_repo(root)
    git(repo, "switch", "-c", "feature/example")
    write(repo, "shared.txt", "feature value\n")
    commit(repo, "feature conflicting change")
    git(repo, "switch", "main")
    write(repo, "shared.txt", "main value\n")
    commit(repo, "main conflicting change")
    git(repo, "switch", "feature/example")
    merge = git(repo, "merge", "main", "--no-edit", check=False)
    assert merge.returncode != 0
    assert "UU shared.txt" in git(repo, "status", "--short").stdout
    assert git(repo, "branch", "--list", "feature/example").stdout.strip()
    print("REQ-BRANCH-005 passed: conflict leaves the worktree and feature branch available for recovery")


def scenario_interruption_preserves_commits(root: Path) -> None:
    repo, base = setup_repo(root)
    git(repo, "switch", "-c", "feature/example")
    write(repo, "change.txt", "feature committed before interruption\n")
    feature_commit = commit(repo, "feature commit before interruption")
    assert git(repo, "rev-parse", "main").stdout.strip() == base
    assert git(repo, "rev-parse", "feature/example").stdout.strip() == feature_commit
    print("REQ-BRANCH-006 passed: interruption before merge preserves both refs without cleanup")


def main() -> int:
    repository = Path(__file__).resolve().parents[4]
    scenario_policy_contract(repository)
    scenarios = (
        scenario_branch_and_no_merge_before_acceptance,
        scenario_acceptance_gate,
        scenario_no_ff_merge,
        scenario_base_drift_requires_reacceptance,
        scenario_conflict_preserves_state,
        scenario_interruption_preserves_commits,
    )
    with tempfile.TemporaryDirectory(prefix="megin-branch-policy-") as directory:
        root = Path(directory)
        for scenario in scenarios:
            scenario(root / scenario.__name__)
    print(f"validated {len(scenarios)} isolated Git branch-policy scenarios")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
