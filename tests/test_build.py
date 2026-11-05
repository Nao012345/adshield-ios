"""Tests for repository validation and dist generation (scripts/adshield_repo.py)."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import helpers  # noqa: F401
import adshield_repo as repo


def write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8", newline="\n")


def make_repo(root: Path, core="||ads.example.com^$third-party\n", video="m.example.tv##.video-ad\n",
              sources=None, expires="1 day"):
    config = {
        "project": "AdShield iOS",
        "github_owner": "tester",
        "repo_name": "adshield-ios",
        "license": "GPL-3.0",
        "expires": expires,
        "bundles": [
            {"id": "core", "file": "adshield-core.txt", "title": "AdShield iOS - Core",
             "description": "Core list", "sources": ["filters/core.txt"]},
            {"id": "video", "file": "adshield-video.txt", "title": "AdShield iOS - Video",
             "description": "Video list", "sources": ["filters/video/x.txt"]},
            {"id": "all", "file": "adshield-all.txt", "title": "AdShield iOS - All",
             "description": "Everything", "sources": "*"},
        ],
    }
    write(root, "build.json", json.dumps(config))
    write(root, "VERSION", "0.1.0\n")
    write(root, "filters/core.txt", "! Core\n" + core)
    write(root, "filters/video/x.txt", video)
    write(root, "upstream/sources.json", json.dumps(sources or {"sources": [
        {"id": "original", "license": "GPL-3.0"},
        {"id": "uassets", "license": "GPL-3.0"},
        {"id": "nc-list", "license": "CC-BY-NC-4.0"},
    ]}))


class RepoTestCase(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)


class ValidateTest(RepoTestCase):
    def test_clean_repo_has_no_errors(self):
        make_repo(self.root)
        report = repo.validate_repo(self.root)
        self.assertEqual(report.errors, [])

    def test_incompatible_rule_reported_with_location(self):
        make_repo(self.root, core="example.com##+js(noeval)\n")
        report = repo.validate_repo(self.root)
        self.assertEqual(len(report.errors), 1)
        self.assertIn("filters/core.txt:2", report.errors[0])
        self.assertIn("scriptlet", report.errors[0])

    def test_duplicate_within_file_reported(self):
        make_repo(self.root, core="||ads.example.com^$3p\n||ads.example.com^$third-party\n")
        report = repo.validate_repo(self.root)
        self.assertTrue(any("duplicate" in e for e in report.errors), report.errors)

    def test_duplicate_across_files_reported(self):
        make_repo(self.root, video="||ads.example.com^$third-party\n")
        report = repo.validate_repo(self.root)
        self.assertTrue(any("duplicate" in e and "filters/core.txt:2" in e for e in report.errors), report.errors)

    def test_unknown_source_id_reported(self):
        make_repo(self.root, core="! @source: mystery\n||ads.example.com^\n")
        report = repo.validate_repo(self.root)
        self.assertTrue(any("unknown source 'mystery'" in e for e in report.errors), report.errors)

    def test_license_incompatible_source_reported(self):
        make_repo(self.root, core="! @source: nc-list\n||ads.example.com^\n")
        report = repo.validate_repo(self.root)
        self.assertTrue(any("license" in e and "nc-list" in e for e in report.errors), report.errors)

    def test_invalid_expires_reported(self):
        make_repo(self.root, expires="30 days")
        report = repo.validate_repo(self.root)
        self.assertTrue(any("Expires" in e for e in report.errors), report.errors)

    def test_utf8_bom_reported(self):
        make_repo(self.root)
        (self.root / "filters/core.txt").write_bytes(b"\xef\xbb\xbf||ads.example.com^\n")
        report = repo.validate_repo(self.root)
        self.assertTrue(any("BOM" in e for e in report.errors), report.errors)


class BuildTest(RepoTestCase):
    def build(self):
        return repo.build_outputs(self.root)

    def test_header_metadata_readable_by_adblock_rust(self):
        make_repo(self.root)
        text = self.build()["adshield-core.txt"]
        self.assertTrue(text.startswith("[Adblock Plus 2.0]\n"))
        # adblock-rust reads metadata only from the leading comment block within 1024 bytes.
        head = text.encode()[:1024].decode()
        block = []
        for line in head.splitlines():
            if not (line.startswith("!") or line.startswith("[")):
                break
            block.append(line)
        joined = "\n".join(block)
        self.assertIn("! Title: AdShield iOS - Core", joined)
        self.assertIn("! Expires: 1 day", joined)
        self.assertIn("! Version: 0.1.0", joined)
        self.assertIn("! Homepage: https://github.com/tester/adshield-ios", joined)

    def test_output_is_ascii_lf_and_deterministic(self):
        make_repo(self.root, core="! 日本語のコメント\n||ads.example.com^$third-party\n")
        first = self.build()
        second = self.build()
        self.assertEqual(first, second)
        for text in first.values():
            self.assertTrue(text.isascii())
            self.assertNotIn("\r", text)
            self.assertTrue(text.endswith("\n"))

    def test_source_comments_are_not_copied(self):
        make_repo(self.root, core="! 日本語のコメント\n||ads.example.com^$third-party\n")
        text = self.build()["adshield-core.txt"]
        self.assertNotIn("日本語", text)

    def test_all_bundle_contains_every_rule(self):
        make_repo(self.root)
        out = self.build()
        all_text = out["adshield-all.txt"]
        self.assertIn("||ads.example.com^$third-party", all_text)
        self.assertIn("m.example.tv##.video-ad", all_text)

    def test_bundle_only_contains_its_sources(self):
        make_repo(self.root)
        out = self.build()
        self.assertNotIn("m.example.tv##.video-ad", out["adshield-core.txt"])

    def test_canary_rules_are_per_bundle(self):
        make_repo(self.root)
        out = self.build()
        core = out["adshield-core.txt"]
        self.assertIn("tester.github.io##.adshield-canary-core", core)
        self.assertIn("||cdn.jsdelivr.net/gh/tester/adshield-ios@*/site/test/canary/core.js", core)
        self.assertNotIn("adshield-canary-video", core)
        all_text = out["adshield-all.txt"]
        for bundle in ("core", "video", "all"):
            self.assertIn(".adshield-canary-" + bundle, all_text)

    def test_generated_rules_pass_ios_checks(self):
        make_repo(self.root)
        import filterlib as fl
        for name, text in self.build().items():
            for rule in fl.parse_list_text(text):
                self.assertEqual(rule.errors, [], (name, rule.raw))

    def test_build_refuses_invalid_sources(self):
        make_repo(self.root, core="example.com##+js(noeval)\n")
        with self.assertRaises(repo.BuildError):
            self.build()

    def test_content_hash_changes_with_rules(self):
        make_repo(self.root)
        a = self.build()["adshield-core.txt"]
        write(self.root, "filters/core.txt", "||ads2.example.com^$third-party\n")
        b = self.build()["adshield-core.txt"]
        hash_a = [l for l in a.splitlines() if l.startswith("! Content-Hash:")]
        hash_b = [l for l in b.splitlines() if l.startswith("! Content-Hash:")]
        self.assertEqual(len(hash_a), 1)
        self.assertNotEqual(hash_a, hash_b)

    def test_write_and_check_detect_stale_dist(self):
        make_repo(self.root)
        repo.write_dist(self.root)
        self.assertEqual(repo.stale_dist_files(self.root), [])
        write(self.root, "filters/core.txt", "||ads2.example.com^$third-party\n")
        self.assertIn("adshield-core.txt", repo.stale_dist_files(self.root))


if __name__ == "__main__":
    unittest.main()
