"""Rebuild the distributable archive from the canonical Skills source."""

from __future__ import annotations

import os
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / ".agents" / "skills" / "megin" / "scripts"))
from validate_skills import package_files  # noqa: E402


def main() -> int:
    source = ROOT / ".agents" / "skills"
    archive = ROOT / "megin-skills.zip"
    temporary = archive.with_suffix(".zip.tmp")
    files = package_files(source)
    try:
        with zipfile.ZipFile(
            temporary,
            "w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=9,
        ) as bundle:
            for name in sorted(files):
                bundle.writestr(name, files[name])
        os.replace(temporary, archive)
    finally:
        if temporary.exists():
            temporary.unlink()
    print(f"rebuilt {archive.name} with {len(files)} entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
