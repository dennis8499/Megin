#!/usr/bin/env python3
"""Owner validation for requirements-discovery contracts."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from urllib.parse import unquote, urlparse


DEFAULT_SKILL_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FILES = {
    "SKILL.md",
    "agents/openai.yaml",
    "references/quality-contract.md",
    "references/high-risk-contract.md",
    "references/delivery-protocol.md",
    "references/requirements-analysis-template.md",
    "references/behavior-evaluation.md",
    "scripts/validate_contracts.py",
    "scripts/test_validate_contracts.py",
    "scripts/behavior-evaluation-report.md",
}
AUTHORITY_OWNERS = {
    "requirements-entrypoint": "SKILL.md",
    "requirements-quality": "references/quality-contract.md",
    "requirements-high-risk": "references/high-risk-contract.md",
    "requirements-delivery": "references/delivery-protocol.md",
    "requirements-document-shape": "references/requirements-analysis-template.md",
}
STATES = {
    "Draft—Not ready",
    "Blocked",
    "Candidate—Awaiting confirmation",
    "Ready",
}
ID_FAMILIES = {"BR", "UR", "FR", "NFR", "TR", "CR", "AC"}
LINK_RE = re.compile(r"!?(?<!\\)\[[^\]]*\]\(([^)]+)\)")
AUTHORITY_RE = re.compile(r"<!--\s*authority:\s*([a-z0-9-]+)\s*-->")


def _text(root: Path, relative: str) -> str:
    return (root / relative).read_text(encoding="utf-8")


def _frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}
    result: dict[str, str] = {}
    for line in text[4:end].splitlines():
        key, separator, value = line.partition(":")
        if separator:
            result[key.strip()] = value.strip()
    return result


def _local_target(source: Path, raw: str) -> Path | None:
    target = raw.strip().strip("<>")
    parsed = urlparse(target)
    if parsed.scheme or target.startswith("#"):
        return None
    path = unquote(parsed.path)
    return (source.parent / path).resolve(strict=False) if path else None


def validate_all(skill_root: Path | None = None) -> list[str]:
    root = (skill_root or DEFAULT_SKILL_ROOT).resolve()
    errors: list[str] = []
    for relative in sorted(REQUIRED_FILES):
        if not (root / relative).is_file():
            errors.append(f"missing required file: {relative}")
    if errors:
        return errors

    authorities: dict[str, list[str]] = {}
    for path in sorted(root.rglob("*.md")):
        relative = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8")
        if "TODO" in text or "TBD" in text:
            errors.append(f"unfinished marker: {relative}")
        for marker in AUTHORITY_RE.findall(text):
            authorities.setdefault(marker, []).append(relative)
        for raw in LINK_RE.findall(text):
            target = _local_target(path, raw)
            if target is not None and not target.exists():
                errors.append(f"broken local link in {relative}: {raw}")

    for authority, owner in AUTHORITY_OWNERS.items():
        actual = authorities.get(authority, [])
        if actual != [owner]:
            errors.append(f"authority {authority} must be owned only by {owner}: {actual}")
    for authority, owners in sorted(authorities.items()):
        if len(owners) > 1:
            errors.append(f"duplicate authority {authority}: {owners}")

    frontmatter = _frontmatter(root / "SKILL.md")
    if frontmatter.get("name") != "requirements-discovery":
        errors.append("SKILL.md name drifted")
    description = frontmatter.get("description", "")
    if not description.startswith("探索"):
        errors.append("SKILL.md description must lead with 探索")
    for discriminator in ("純實作", "知識解說", "故障診斷"):
        if discriminator not in description:
            errors.append(f"description lacks invocation discriminator: {discriminator}")

    skill = _text(root, "SKILL.md")
    if "frontier" not in skill or "一次詢問一項" not in skill:
        errors.append("entrypoint lost frontier or one-question contract")
    for number in range(1, 14):
        if not re.search(rf"(?m)^{number}\. ", skill):
            errors.append(f"coverage map missing item {number}")
    if skill.count("(references/high-risk-contract.md)") < 2:
        errors.append("high-risk contract must load in risk discovery and final quality branches")
    for required in ("完成條件：", "影響程度 × 不確定性 × 不可逆性", "已確認", "未知", "矛盾", "不適用"):
        if required not in skill:
            errors.append(f"entrypoint missing exploration invariant: {required}")

    quality = _text(root, "references/quality-contract.md")
    for version in ("ISO/IEC/IEEE 29148:2018", "2025，Av.2.0"):
        if version not in quality:
            errors.append(f"quality source version drifted: {version}")
    for url in (
        "https://www.iso.org/standard/72089.html",
        "https://www.iiba.org/globalassets/business-analysis-resources/the-business-analysis-standard/files/the-business-analysis-standard.pdf",
    ):
        if url not in quality:
            errors.append(f"quality source link missing: {url}")
    for verdict in ("通過", "未通過", "無法完成"):
        if verdict not in quality:
            errors.append(f"binary quality verdict missing: {verdict}")
    if "司法管轄區、適用框架" in quality:
        errors.append("general quality contract duplicates high-risk criteria")

    high_risk = _text(root, "references/high-risk-contract.md")
    for required in ("司法管轄區", "一手來源", "人工審查", "CR-*", "無法完成"):
        if required not in high_risk:
            errors.append(f"high-risk contract missing criterion: {required}")

    delivery = _text(root, "references/delivery-protocol.md")
    for state in sorted(STATES):
        if f"- `{state}`：" not in delivery:
            errors.append(f"delivery state missing: {state}")
    for required in ("完整 bytes", "精確建議路徑", "create-only", "唯一問題"):
        if required not in delivery:
            errors.append(f"delivery protocol missing gate: {required}")

    template = _text(root, "references/requirements-analysis-template.md")
    for family in sorted(ID_FAMILIES):
        classification = f"- `{family}-*`："
        example = f"### {family}-001"
        if classification not in template and example not in template:
            errors.append(f"template missing ID family: {family}")
    for heading in (
        "## 1. 執行摘要",
        "## 2. 利害關係人與角色",
        "## 3. 範圍與優先順序",
        "## 4. 使用者與業務旅程",
        "## 5. 需求",
        "## 6. 驗收情境",
        "## 7. 成功指標",
        "## 8. 追溯矩陣",
        "## 9. 已確認決策、假設與依賴",
        "## 10. 完整性與開放事項",
    ):
        if heading not in template:
            errors.append(f"template heading missing: {heading}")

    yaml = _text(root, "agents/openai.yaml")
    if "allow_implicit_invocation: true" not in yaml:
        errors.append("openai.yaml must preserve implicit invocation")
    if "$requirements-discovery" not in yaml:
        errors.append("openai.yaml default prompt must name the skill")
    if 'short_description: "探索' not in yaml:
        errors.append("openai.yaml short description must lead with 探索")

    behavior = _text(root, "references/behavior-evaluation.md")
    for index in range(1, 9):
        if f"EVAL-REQ-{index:03d}" not in behavior:
            errors.append(f"behavior contract missing EVAL-REQ-{index:03d}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill-root", type=Path)
    args = parser.parse_args(argv)
    errors = validate_all(args.skill_root)
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    print("requirements-discovery contracts: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
