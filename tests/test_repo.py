"""Integration tests against the real repository content (filters/, dist/, site/)."""
import shutil
import tempfile
import unittest
from pathlib import Path

import helpers
import adshield_repo as repo
import filterlib as fl
import make_site

ROOT = helpers.ROOT


def fixture_urls(name):
    lines = (helpers.FIXTURES / name).read_text(encoding="utf-8").splitlines()
    return [l.strip() for l in lines if l.strip() and not l.startswith("#")]


def dist_rules(name="adshield-all.txt"):
    return fl.parse_list_text((ROOT / "dist" / name).read_text(encoding="utf-8"))


class RepositoryTest(unittest.TestCase):
    def test_production_sources_validate(self):
        report = repo.validate_repo(ROOT)
        self.assertEqual(report.errors, [])

    def test_dist_is_up_to_date(self):
        self.assertEqual(repo.stale_dist_files(ROOT), [], "run: python scripts/build.py")

    def test_every_dist_rule_passes_ios_policy(self):
        for path in sorted((ROOT / "dist").glob("*.txt")):
            for rule in fl.parse_list_text(path.read_text(encoding="utf-8")):
                self.assertEqual(rule.errors, [], f"{path.name}: {rule.raw}")

    def test_dist_files_are_ascii_lf(self):
        for path in sorted((ROOT / "dist").glob("*.txt")):
            data = path.read_bytes()
            self.assertTrue(data.isascii(), path.name)
            self.assertNotIn(b"\r", data, path.name)

    def test_critical_urls_are_never_blocked(self):
        rules = dist_rules()
        for url in fixture_urls("must_not_block.txt"):
            blocker = fl.is_blocked(rules, url)
            self.assertIsNone(blocker, f"{url} blocked by {blocker.raw if blocker else ''}")

    def test_target_urls_are_blocked(self):
        rules = dist_rules()
        for url in fixture_urls("should_block.txt"):
            self.assertIsNotNone(fl.is_blocked(rules, url), url)

    def test_video_lists_never_block_network(self):
        """Policy (spec 4-B): no network blocking on video sites until verified on device."""
        config = repo.load_config(ROOT)
        video = next(b for b in config["bundles"] if b["id"] == "video")
        for path in video["sources"]:
            for e in fl.parse_source_text((ROOT / path).read_text(encoding="utf-8"), path):
                self.assertFalse(e.rule.kind == "network", f"{path}:{e.lineno}: {e.rule.raw}")


class MakeSiteTest(unittest.TestCase):
    def setUp(self):
        self.out = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.out, ignore_errors=True)

    def test_refuses_placeholder_owner(self):
        config = repo.load_config(ROOT)
        if config["github_owner"] != "OWNER":
            self.skipTest("owner already configured")
        with self.assertRaises(make_site.SiteError):
            make_site.make_site(ROOT, self.out / "site")

    def test_site_contains_lists_and_substituted_pages(self):
        out = self.out / "site"
        make_site.make_site(ROOT, out, owner="tester")
        for name in ("adshield-core.txt", "adshield-all.txt", "index.html", "test/index.html",
                     "test/canary/core.js", "test/canary/control.js"):
            self.assertTrue((out / name).is_file(), name)
        index = (out / "index.html").read_text(encoding="utf-8")
        self.assertIn("https://tester.github.io/adshield-ios/adshield-all.txt", index)
        self.assertNotIn("{{", index)
        test_page = (out / "test" / "index.html").read_text(encoding="utf-8")
        self.assertIn("cdn.jsdelivr.net/gh/tester/adshield-ios@", test_page)
        self.assertNotIn("{{", test_page)

    def test_every_bundle_has_a_canary_script(self):
        config = repo.load_config(ROOT)
        for bundle in config["bundles"]:
            self.assertTrue((ROOT / "site" / "test" / "canary" / f"{bundle['id']}.js").is_file(), bundle["id"])


if __name__ == "__main__":
    unittest.main()
