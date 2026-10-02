"""Static package check for the Megin Skills-only bundle.

This is a development validator, not a workflow runner. The installed workflow is driven by
the Skills and Markdown records; no Megin command is required at runtime.
"""

from __future__ import annotations

import re
import sys
import argparse
import hashlib
import os
import stat
import tempfile
import zipfile
from collections import Counter
from pathlib import Path


EXPECTED = (
    "megin",
    "megin-requirements-discovery",
    "megin-technical-planning",
    "megin-bug-diagnosis",
    "megin-project-knowledge",
    "megin-behavior-contract",
    "megin-implementation-execution",
    "megin-test-driven-development",
    "megin-code-review",
    "megin-verification-before-completion",
    "megin-human-acceptance",
    "megin-finishing-delivery",
)


def frontmatter(path: Path) -> tuple[str, str]:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"\A---\nname: ([^\n]+)\ndescription: ([^\n]+)\n---\n", text)
    if not match:
        raise ValueError(f"{path}: invalid frontmatter")
    return match.group(1).strip(), match.group(2).strip()


def package_files(root: Path) -> dict[str, bytes]:
    """Return the exact files that belong in the distributable archive."""
    repository = root.parent.parent
    readme = repository / "README.md"
    if readme.is_symlink():
        raise ValueError(f"package README must not be a symlink: {readme}")
    if not readme.is_file():
        raise ValueError(f"missing package README: {readme}")
    if root.is_symlink():
        raise ValueError(f"Skills root must not be a symlink: {root}")
    skills_root = root.resolve()

    files = {"README.md": readme.read_bytes()}
    version = repository / "VERSION"
    if version.is_file():
        files["VERSION"] = version.read_bytes()
    for name in EXPECTED:
        skill = root / name
        if skill.is_symlink():
            raise ValueError(f"Skill directory must not be a symlink: {skill}")
        skill_root = skill.resolve()
        if not skill_root.is_relative_to(skills_root):
            raise ValueError(f"Skill directory resolves outside Skills root: {skill}")
        for path in skill.rglob("*"):
            if path.is_symlink():
                raise ValueError(f"Skill resource must not be a symlink: {path}")
            if (path.is_file() and "__pycache__" not in path.parts
                    and path.suffix.lower() != ".pyc"):
                resolved = path.resolve()
                if not resolved.is_relative_to(skill_root):
                    raise ValueError(f"Skill resource resolves outside its directory: {path}")
                files[path.relative_to(root).as_posix()] = path.read_bytes()
    return files


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_archive(root: Path, archive: Path) -> None:
    """Build the bundle with stable entry order, timestamps, and Unix file modes."""
    files = package_files(root)
    archive.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w+b", dir=archive.parent, prefix=f".{archive.name}.", suffix=".tmp",
        delete=False,
    ) as temporary:
        temporary_path = Path(temporary.name)
    try:
        with zipfile.ZipFile(temporary_path, "w", compression=zipfile.ZIP_STORED) as bundle:
            for name in sorted(files):
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | 0o644) << 16
                info.compress_type = zipfile.ZIP_STORED
                bundle.writestr(info, files[name])
        os.replace(temporary_path, archive)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def validate_archive(root: Path, archive: Path) -> list[str]:
    errors: list[str] = []
    try:
        expected = package_files(root)
    except (OSError, ValueError) as exc:
        return [str(exc)]

    try:
        with zipfile.ZipFile(archive) as bundle:
            names = bundle.namelist()
            counts = Counter(names)
            duplicates = sorted(name for name, count in counts.items() if count > 1)
            actual = set(names)
            missing = sorted(set(expected) - actual)
            extra = sorted(actual - set(expected))
            if duplicates:
                errors.append(f"duplicate archive entries: {duplicates}")
            if missing:
                errors.append(f"missing archive entries: {missing}")
            if extra:
                errors.append(f"unexpected archive entries: {extra}")
            for name in sorted(set(expected) & actual):
                actual_digest = digest(bundle.read(name))
                expected_digest = digest(expected[name])
                if actual_digest != expected_digest:
                    errors.append(
                        f"archive content drift for {name}: "
                        f"expected {expected_digest}, got {actual_digest}"
                    )
                info = bundle.getinfo(name)
                mode = (info.external_attr >> 16) & 0o777777
                if info.create_system != 3 or mode != (stat.S_IFREG | 0o644):
                    errors.append(f"archive entry mode differs from 100644 for {name}")
                if info.date_time != (1980, 1, 1, 0, 0, 0):
                    errors.append(f"archive entry timestamp is not reproducible for {name}")
    except FileNotFoundError:
        errors.append(f"missing archive: {archive}")
    except (OSError, zipfile.BadZipFile) as exc:
        errors.append(f"invalid archive {archive}: {exc}")
    return errors


def validate(root: Path) -> list[str]:
    errors: list[str] = []
    for name in EXPECTED:
        skill = root / name
        if not skill.is_dir():
            errors.append(f"missing skill directory: {name}")
            continue
        entry = skill / "SKILL.md"
        metadata = skill / "agents" / "openai.yaml"
        if not entry.is_file():
            errors.append(f"{name}: missing SKILL.md")
            continue
        try:
            declared, description = frontmatter(entry)
        except (OSError, ValueError) as exc:
            errors.append(str(exc))
            continue
        if declared != name:
            errors.append(f"{entry}: name {declared!r} does not match directory")
        if len(description) < 20:
            errors.append(f"{entry}: description is too short for discovery")
        if "group-workspace.md" not in entry.read_text(encoding="utf-8"):
            errors.append(f"{entry}: missing Group workspace contract reference")
        if not metadata.is_file():
            errors.append(f"{name}: missing agents/openai.yaml")
        elif "allow_implicit_invocation: true" not in metadata.read_text(encoding="utf-8"):
            errors.append(f"{metadata}: implicit invocation is not enabled")
    # Keep legacy markers split so the Skills bundle itself does not carry a
    # discoverable reference to a retired runtime entry point.
    forbidden = (
        "plugins" + "/megin",
        "megin" + "_v3.py",
        "bin" + "/megin",
        "hooks" + "/hooks.json",
        "delivery-run/" + "v3",
    )
    for name in EXPECTED:
        for path in (root / name).rglob("*"):
            if path.is_file() and path.name != "validate_skills.py":
                text = path.read_text(encoding="utf-8", errors="replace")
                for token in forbidden:
                    if token in text:
                        errors.append(f"{path}: forbidden legacy reference {token}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the Megin Skills source and archive")
    parser.add_argument(
        "--archive",
        type=Path,
        help="also verify the exact distributable archive against the source tree",
    )
    parser.add_argument(
        "--build-archive",
        type=Path,
        help="rebuild the distributable archive with deterministic paths, times, and modes",
    )
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1].parent
    errors = validate(root)
    if args.build_archive:
        try:
            build_archive(root, args.build_archive)
        except (OSError, ValueError) as exc:
            errors.append(f"could not build archive: {exc}")
    if args.archive:
        errors.extend(validate_archive(root, args.archive))
    elif args.build_archive:
        errors.extend(validate_archive(root, args.build_archive))
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"validated {len(EXPECTED)} Megin Skills")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
