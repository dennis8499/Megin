#!/usr/bin/env python3
"""Small, dependency-free Gherkin contract parser used by Megin v3.

The target repository may use ``behave``, Cucumber, pytest-bdd, or another
runner.  Megin only owns the portable contract checks here: every scenario has
an ID and executable steps, and the runner command is supplied by the approved
plan.  Keeping this parser dependency-free lets the plugin run before a target
project has installed its own test stack.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


STEP_KEYWORDS = ("Given", "When", "Then", "And", "But")
_TAG_RE = re.compile(r"^\s*@([^\s]+)")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{1,127}$")
_INLINE_ID_RE = re.compile(r"^\[([A-Za-z0-9][A-Za-z0-9_.:-]{1,127})\]\s*(.*)$")


@dataclass(frozen=True)
class Scenario:
    """A stable, executable behavior scenario."""

    identifier: str
    title: str
    line: int
    steps: tuple[str, ...]
    tags: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.identifier,
            "title": self.title,
            "line": self.line,
            "steps": list(self.steps),
            "tags": list(self.tags),
        }


class GherkinError(ValueError):
    """Raised when a feature file cannot be used as a behavior contract."""


def _stable_id(feature: str, title: str, line: int) -> str:
    digest = hashlib.sha256(f"{feature}\n{title}\n{line}".encode("utf-8")).hexdigest()[:12]
    prefix = re.sub(r"[^A-Za-z0-9]+", "-", feature).strip("-").lower() or "feature"
    return f"BDD-{prefix}-{digest}"


def parse_feature(text: str, *, source: str = "feature") -> dict[str, object]:
    """Parse a Feature and Scenario outline without executing steps.

    A tag such as ``@BDD-LOGIN-001`` or an inline title such as
    ``Scenario: [BDD-LOGIN-001] user signs in`` supplies the stable ID.  If no
    ID is present, a deterministic ID is derived from the feature, title, and
    source line so a wording edit remains reviewable as a contract change.
    """

    lines = text.splitlines()
    feature_name: str | None = None
    feature_line = 0
    scenarios: list[Scenario] = []
    pending_tags: list[str] = []
    current_title: str | None = None
    current_line = 0
    current_steps: list[str] = []
    current_tags: list[str] = []

    def finish_scenario() -> None:
        nonlocal current_title, current_line, current_steps, current_tags
        if current_title is None:
            return
        if not current_steps:
            raise GherkinError(f"{source}:{current_line}: scenario has no Given/When/Then steps")
        inline = _INLINE_ID_RE.match(current_title)
        title = current_title
        identifier: str | None = None
        if inline:
            identifier, title = inline.group(1), inline.group(2).strip()
        for tag in current_tags:
            clean_tag = tag.lstrip("@")
            candidate = clean_tag
            if _ID_RE.fullmatch(candidate) and (clean_tag.upper().startswith("BDD-") or clean_tag.lower().startswith("id:")):
                identifier = candidate
                break
        identifier = identifier or _stable_id(feature_name or "feature", title, current_line)
        if not _ID_RE.fullmatch(identifier):
            raise GherkinError(f"{source}:{current_line}: invalid scenario ID {identifier!r}")
        scenarios.append(Scenario(identifier, title, current_line, tuple(current_steps), tuple(current_tags)))
        current_title = None
        current_line = 0
        current_steps = []
        current_tags = []

    for number, raw in enumerate(lines, 1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        tag_match = _TAG_RE.match(stripped)
        if tag_match:
            pending_tags.extend(item for item in stripped.split() if item.startswith("@"))
            continue
        if stripped.startswith("Feature:"):
            if feature_name is not None:
                raise GherkinError(f"{source}:{number}: more than one Feature is not supported")
            feature_name = stripped.split(":", 1)[1].strip()
            feature_line = number
            if not feature_name:
                raise GherkinError(f"{source}:{number}: Feature needs a name")
            continue
        if stripped.startswith("Background:") or stripped.startswith("Rule:"):
            # These constructs remain visible to the target runner, but the
            # portable contract parser does not try to flatten them.
            continue
        if stripped.startswith("Scenario:") or stripped.startswith("Scenario Outline:"):
            finish_scenario()
            current_title = stripped.split(":", 1)[1].strip()
            current_line = number
            current_tags = pending_tags
            pending_tags = []
            continue
        if any(stripped.startswith(keyword + " ") for keyword in STEP_KEYWORDS):
            if current_title is None:
                raise GherkinError(f"{source}:{number}: step appears outside a Scenario")
            current_steps.append(stripped)
            continue
        if stripped.startswith("Examples:") or stripped.startswith("|"):
            continue
        raise GherkinError(f"{source}:{number}: unsupported or malformed Gherkin line: {stripped!r}")

    finish_scenario()
    if feature_name is None:
        raise GherkinError(f"{source}:{feature_line or 1}: missing Feature declaration")
    if not scenarios:
        raise GherkinError(f"{source}:{feature_line}: feature has no Scenario")
    identifiers = [item.identifier for item in scenarios]
    if len(identifiers) != len(set(identifiers)):
        raise GherkinError(f"{source}: scenario IDs must be unique")
    return {
        "feature": feature_name,
        "source": source,
        "scenarios": [item.as_dict() for item in scenarios],
    }


def load_features(paths: Iterable[str | Path]) -> tuple[list[dict[str, object]], list[str]]:
    """Load and validate feature files, returning contracts and source digests."""

    contracts: list[dict[str, object]] = []
    digests: list[str] = []
    for value in paths:
        path = Path(value).expanduser().resolve()
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise GherkinError(f"cannot read feature file {path}: {exc}") from exc
        try:
            contract = parse_feature(raw.decode("utf-8"), source=str(path))
        except UnicodeDecodeError as exc:
            raise GherkinError(f"feature file is not UTF-8: {path}") from exc
        contracts.append(contract)
        digests.append(hashlib.sha256(raw).hexdigest())
    return contracts, digests


def flatten_scenarios(contracts: Iterable[dict[str, object]]) -> list[dict[str, object]]:
    """Return scenario records suitable for the v3 behavior contract."""

    result: list[dict[str, object]] = []
    for contract in contracts:
        source = str(contract.get("source", "feature"))
        for scenario in contract.get("scenarios", []):
            if not isinstance(scenario, dict):
                continue
            steps = list(scenario.get("steps", []))
            gherkin = "Feature: " + str(contract.get("feature", "Megin behavior")) + "\n\n"
            gherkin += "Scenario: [" + str(scenario.get("id")) + "] " + str(scenario.get("title", "behavior")) + "\n"
            gherkin += "\n".join("  " + str(step) for step in steps)
            result.append({
                "id": scenario.get("id"),
                "title": scenario.get("title"),
                "source": source,
                "steps": steps,
                "gherkin": gherkin,
                "automatic": True,
                "manual": [],
            })
    return result
