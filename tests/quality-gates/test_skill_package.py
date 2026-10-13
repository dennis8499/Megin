"""Release artifacts must be self-contained, exact and reproducible."""
import posixpath
import re
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILLS = ROOT / '.agents/skills'
sys.path.insert(0, str(SKILLS / 'megin/scripts'))
import validate_skills as package


class SkillPackageTests(unittest.TestCase):
    def test_unpacked_documentation_has_no_broken_local_links(self):
        files = package.package_files(SKILLS)
        self.assertIn('OPERATIONS.md', set(files))
        for name, data in files.items():
            if not name.endswith('.md'):
                continue
            for target in re.findall(r'\]\(([^)]+)\)', data.decode('utf-8')):
                target = target.split('#', 1)[0].strip('<>')
                if not target or '://' in target:
                    continue
                resolved = posixpath.normpath(posixpath.join(posixpath.dirname(name), target))
                self.assertIn(resolved, set(files), (name, target))

    def test_archive_is_reproducible_and_rejects_tampered_resource(self):
        with tempfile.TemporaryDirectory() as temporary:
            first, second = (Path(temporary) / name for name in ('first.zip', 'second.zip'))
            package.build_archive(SKILLS, first)
            package.build_archive(SKILLS, second)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(package.validate_archive(SKILLS, first), [])
            with zipfile.ZipFile(second, 'a') as bundle:
                bundle.writestr('unexpected-resource.txt', 'unreviewed')
            self.assertTrue(any('unexpected archive entries' in error
                                for error in package.validate_archive(SKILLS, second)))


if __name__ == '__main__':
    unittest.main()
