"""Tests for tools/check_profile.py."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import check_profile as cp  # noqa: E402

GOOD_README = """# Profile

[A project](https://github.com/Amz34/graphwright) and
[the site](https://amz34.github.io) plus [mail](mailto:someone@example.com).

| Repo | What it does | Why it matters |
|---|---|---|
| [**archivepilot**](https://github.com/Amz34/archivepilot) | Local archive | Private by default |

""" + ("Filler paragraph. " * 60)


class ExtractLinksTests(unittest.TestCase):
    def test_extracts_markdown_autolink_and_image(self):
        text = "[a](https://x.test) <https://y.test> <img src=\"assets/p.jpg\">"
        self.assertEqual(cp.extract_links(text), ["https://x.test", "https://y.test", "assets/p.jpg"])

    def test_ignores_plain_text_urls(self):
        self.assertEqual(cp.extract_links("see https://x.test now"), [])


class CheckTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "assets").mkdir()
        (self.root / "assets" / "p.jpg").write_bytes(b"\xff\xd8\xff")

    def tearDown(self):
        self._tmp.cleanup()

    def manifest(self, *names):
        base = {"amz34/archivepilot", "amz34/graphwright"}
        return base | {f"amz34/{n}".lower() for n in names}

    def test_clean_readme_passes(self):
        self.assertEqual(cp.check(GOOD_README, self.root, self.manifest("archivepilot")), [])

    def test_missing_local_asset_is_reported(self):
        text = GOOD_README.replace("# Profile", "# Profile\n\n![hero](assets/missing-hero.jpg)")
        problems = cp.check(text, self.root, self.manifest("archivepilot"))
        self.assertTrue(any(p.startswith("missing local asset") for p in problems), problems)

    def test_existing_local_asset_resolves(self):
        text = GOOD_README.replace("# Profile", "# Profile\n\n![hero](assets/p.jpg)")
        self.assertEqual(cp.check(text, self.root, self.manifest("archivepilot")), [])

    def test_private_or_renamed_repo_is_reported(self):
        problems = cp.check(GOOD_README, self.root, set())
        self.assertTrue(any("unlisted Amz34 repository" in p for p in problems), problems)

    def test_insecure_http_link_is_reported(self):
        text = GOOD_README.replace("https://amz34.github.io", "http://amz34.github.io")
        problems = cp.check(text, self.root, self.manifest("archivepilot"))
        self.assertTrue(any("insecure http link" in p for p in problems), problems)

    def test_relative_non_mailto_link_is_reported(self):
        text = GOOD_README.replace("[the site](https://amz34.github.io)", "[the site](notes.txt)")
        problems = cp.check(text, self.root, self.manifest("archivepilot"))
        self.assertTrue(any("no local file" in p for p in problems), problems)

    def test_duplicate_repository_link_is_reported(self):
        text = GOOD_README + "\n[again](https://github.com/Amz34/archivepilot)\n"
        problems = cp.check(text, self.root, self.manifest("archivepilot"))
        self.assertTrue(any("linked twice" in p for p in problems), problems)

    def test_placeholder_is_reported(self):
        text = GOOD_README.replace("Local archive", "Local archive TODO")
        problems = cp.check(text, self.root, self.manifest("archivepilot"))
        self.assertTrue(any("placeholder text" in p for p in problems), problems)

    def test_unbalanced_fence_is_reported(self):
        text = GOOD_README + "\n```bash\nls\n"
        problems = cp.check(text, self.root, self.manifest("archivepilot"))
        self.assertTrue(any("unbalanced code fence" in p for p in problems), problems)

    def test_two_column_table_row_is_reported(self):
        text = GOOD_README.replace("| Repo | What it does | Why it matters |", "| Repo | What |")
        text = text.replace(
            "| [**archivepilot**](https://github.com/Amz34/archivepilot) | Local archive | Private by default |",
            "| [**archivepilot**](https://github.com/Amz34/archivepilot) | Local archive |",
        )
        problems = cp.check(text, self.root, self.manifest("archivepilot"))
        self.assertTrue(any("3 columns" in p for p in problems), problems)

    def test_truncated_readme_is_reported(self):
        problems = cp.check("# Profile", self.root, self.manifest("archivepilot"))
        self.assertTrue(any("truncated" in p for p in problems), problems)


class ManifestTests(unittest.TestCase):
    def test_manifest_ignores_comments_and_normalises_case(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "m.txt"
            path.write_text("# comment\nAmz34/ArchivePilot\n\n", encoding="utf-8")
            self.assertEqual(cp.load_manifest(path), {"amz34/archivepilot"})

    def test_missing_manifest_is_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(cp.load_manifest(Path(tmp) / "nope.txt"), set())


class MainTests(unittest.TestCase):
    def test_missing_readme_returns_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(cp.main([str(Path(tmp) / "absent.md")]), 2)

    def test_empty_manifest_returns_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            readme = root / "README.md"
            readme.write_text(GOOD_README, encoding="utf-8")
            (root / "tools").mkdir()
            (root / "tools" / "public_repos.txt").write_text("# none\n", encoding="utf-8")
            (root / "assets" / "p.jpg").parent.mkdir(parents=True, exist_ok=True)
            self.assertEqual(cp.main([str(readme), "--manifest", "tools/public_repos.txt"]), 2)

    def test_clean_manifested_readme_returns_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "assets").mkdir()
            (root / "assets" / "p.jpg").write_bytes(b"\xff\xd8\xff")
            (root / "tools").mkdir()
            (root / "tools" / "public_repos.txt").write_text("archivepilot\ngraphwright\n", encoding="utf-8")
            (root / "README.md").write_text(GOOD_README, encoding="utf-8")
            self.assertEqual(cp.main([str(root / "README.md"), "--manifest", "tools/public_repos.txt"]), 0)

    def test_private_link_returns_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "assets").mkdir()
            (root / "assets" / "p.jpg").write_bytes(b"\xff\xd8\xff")
            (root / "tools").mkdir()
            (root / "tools" / "public_repos.txt").write_text("archivepilot\n", encoding="utf-8")
            bad = GOOD_README.replace("https://github.com/Amz34/archivepilot", "https://github.com/Amz34/voice-clone-assistant")
            (root / "README.md").write_text(bad, encoding="utf-8")
            self.assertEqual(cp.main([str(root / "README.md"), "--manifest", "tools/public_repos.txt"]), 1)


if __name__ == "__main__":
    unittest.main()
