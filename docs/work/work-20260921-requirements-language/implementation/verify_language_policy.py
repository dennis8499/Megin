"""Focused static checks for the requirements and output-language behavior contract."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
SKILLS = ROOT / ".agents" / "skills"
POLICY = SKILLS / "megin" / "references" / "language-policy.md"
WORKFLOW_RECORD = SKILLS / "megin" / "references" / "workflow-record.md"
FEATURE = Path(__file__).resolve().parents[1] / "features" / "language-policy.feature"

EXPECTED_SKILLS = (
    "megin",
    "megin-requirements-discovery",
    "megin-technical-planning",
    "megin-behavior-contract",
    "megin-bug-diagnosis",
    "megin-project-knowledge",
    "megin-implementation-execution",
    "megin-test-driven-development",
    "megin-code-review",
    "megin-verification-before-completion",
    "megin-human-acceptance",
    "megin-finishing-delivery",
)


def main() -> int:
    errors: list[str] = []
    policy = POLICY.read_text(encoding="utf-8")
    workflow_record = WORKFLOW_RECORD.read_text(encoding="utf-8")
    feature = FEATURE.read_text(encoding="utf-8")

    required_policy_phrases = (
        "Traditional Chinese",
        "status: awaiting_user",
        "create a planning",
        "Gherkin",
    )
    for phrase in required_policy_phrases:
        if phrase not in policy:
            errors.append(f"language policy is missing: {phrase}")

    if "繁體中文" not in workflow_record or "status: awaiting_user" not in workflow_record:
        errors.append("workflow record template does not carry the language or waiting policy")

    for marker in ("@REQ-LANG-001", "@REQ-LANG-002", "@REQ-LANG-003", "@REQ-LANG-004", "Quartz.Net"):
        if marker not in feature:
            errors.append(f"behavior feature is missing: {marker}")

    for name in EXPECTED_SKILLS:
        skill = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
        if name != "megin" and "language-policy.md" not in skill:
            errors.append(f"{name}: missing language-policy reference")
    entry = (SKILLS / "megin" / "SKILL.md").read_text(encoding="utf-8")
    for phrase in ("language-policy.md", "status: awaiting_user", "major unknown"):
        if phrase not in entry:
            errors.append(f"megin entry is missing: {phrase}")
    classify_at = entry.find("Classify the request")
    active_record_at = entry.find("If one active Megin record exists")
    if classify_at < 0 or active_record_at < 0 or classify_at > active_record_at:
        errors.append("megin entry must classify before creating a new requirements record")
    for phrase in ("pure explanation or review", "without a delivery record", "authorized repair"):
        if phrase not in entry:
            errors.append(f"megin routing rule is missing: {phrase}")

    requirements = (SKILLS / "megin-requirements-discovery" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    for phrase in ("exactly one", "Traditional Chinese", "status: awaiting_user", "do not claim"):
        if phrase not in requirements:
            errors.append(f"requirements discovery is missing: {phrase}")

    planning = (SKILLS / "megin-technical-planning" / "SKILL.md").read_text(encoding="utf-8")
    for phrase in ("major unknown", "return to requirements discovery", "do not write"):
        if phrase not in planning:
            errors.append(f"technical planning is missing: {phrase}")

    if errors:
        print("\n".join(errors))
        return 1
    print(f"validated language policy references for {len(EXPECTED_SKILLS)} Skills")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
