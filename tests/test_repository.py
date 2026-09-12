"""Offline checks; these do not claim installed-tool or physical-flow coverage."""

import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
SKILLS = [ROOT / "SKILL.md", *sorted((ROOT / "flow").glob("*/SKILL.md")),
          *sorted((ROOT / "tools").glob("*/SKILL.md"))]
DOCS = [ROOT / "README.md", ROOT / "AGENTS.md", ROOT / "SKILL.md",
        *sorted((ROOT / "flow").rglob("*.md")),
        *sorted((ROOT / "tools").rglob("*.md")),
        *sorted((ROOT / "examples").rglob("*.md"))]


class RepositoryTests(unittest.TestCase):
    def test_demo_uses_inline_video_attachment(self):
        readme = (ROOT / "README.md").read_text()
        demo = readme.split("## Demo\n", 1)[1].split("\n## ", 1)[0]
        self.assertRegex(
            demo,
            r"(?m)^https://github\.com/user-attachments/assets/"
            r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$",
        )
        self.assertNotIn("](examples/backend/gcd/media/demo.mp4)", demo)

    def test_skill_frontmatter(self):
        self.assertEqual(len(SKILLS), 7)
        names = set()
        for path in SKILLS:
            with self.subTest(path=path.relative_to(ROOT)):
                front = path.read_text().split("---\n", 2)
                self.assertEqual(len(front), 3)
                self.assertEqual(front[0], "")
                fields = dict(line.split(": ", 1) for line in front[1].strip().splitlines())
                self.assertEqual(set(fields), {"name", "description"})
                self.assertRegex(fields["name"], r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
                self.assertLessEqual(len(fields["name"]), 64)
                self.assertTrue(0 < len(fields["description"]) <= 1024)
                self.assertNotIn(fields["name"], names)
                names.add(fields["name"])
                self.assertTrue(front[2].strip())

    def test_relative_document_links_exist(self):
        for path in DOCS:
            for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", path.read_text()):
                if "://" in target or target.startswith("#"):
                    continue
                with self.subTest(source=path.relative_to(ROOT), target=target):
                    destination = (path.parent / target.split("#", 1)[0]).resolve()
                    self.assertTrue(destination.is_relative_to(ROOT))
                    self.assertTrue(destination.is_file())

    def test_no_machine_specific_paths(self):
        for path in DOCS:
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertNotRegex(path.read_text(), r"/Users/|/home/runner/|/opt/homebrew/")

    def test_package_pins_and_no_submodule_manifest(self):
        manifest = json.loads((ROOT / "toolchain.json").read_text())
        self.assertEqual(manifest["schema_version"], 1)
        self.assertRegex(manifest["nixpkgs"], r"/[0-9a-f]{40}$")
        self.assertRegex(manifest["kepler_formal"]["installable"], r"rev=[0-9a-f]{40}&submodules=1#kepler-formal$")
        self.assertEqual(manifest["kepler_formal"]["cache"], "https://keplertech.cachix.org")
        self.assertRegex(manifest["gcd"]["fixture_revision"], r"^[0-9a-f]{40}$")
        self.assertFalse((ROOT / ".gitmodules").exists())
        self.assertIn(manifest["kepler_formal"]["installable"],
                      (ROOT / "tools/kepler-formal/install.md").read_text())
        requirements = (ROOT / "tools/python-requirements.txt").read_text().splitlines()
        self.assertEqual(set(requirements),
                         {f"{key}=={value}" for key, value in manifest["python_packages"].items()})


if __name__ == "__main__":
    unittest.main()
