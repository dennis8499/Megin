from __future__ import annotations

import importlib.util
import tempfile
import warnings
import zipfile
from pathlib import Path


ROOT = Path(".agents/skills").resolve()
SCRIPT = ROOT / "megin" / "scripts" / "validate_skills.py"
spec = importlib.util.spec_from_file_location("validate_skills", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

with zipfile.ZipFile("megin-skills.zip") as source:
    entries = [(name, source.read(name)) for name in source.namelist()]


def write_archive(path: Path, transform) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as target:
            for name, data in transform(entries):
                target.writestr(name, data)


def missing(items):
    return list(items[1:])


def extra(items):
    return [*items, ("unexpected.txt", b"unexpected")]


def duplicate(items):
    return [*items, items[0]]


def drift(items):
    name, data = items[0]
    return [(name, data + b"drift"), *items[1:]]


with tempfile.TemporaryDirectory(prefix="megin-archive-negative-") as temp:
    temp_root = Path(temp)
    assert not module.validate_archive(ROOT, Path("megin-skills.zip"))
    for label, transform in (
        ("missing", missing),
        ("extra", extra),
        ("duplicate", duplicate),
        ("drift", drift),
    ):
        archive = temp_root / f"{label}.zip"
        write_archive(archive, transform)
        errors = module.validate_archive(ROOT, archive)
        assert errors, f"{label} archive unexpectedly passed"
        print(f"{label}: rejected")

print("negative archive cases passed")
