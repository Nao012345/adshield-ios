"""Tests for overlap detection against Brave's default lists and upstream watching."""
import unittest

import helpers  # noqa: F401
import filterlib as fl
import overlap
import upstream_watch as uw


def rules(text):
    return fl.parse_list_text(text)


class OverlapTest(unittest.TestCase):
    def test_exact_duplicate_found(self):
        ours = rules("||ads.example.com^$third-party\n")
        theirs = rules("||ads.example.com^$3p\n")
        found = overlap.compare(ours, theirs)
        self.assertEqual([(f.kind, f.rule.raw) for f in found], [("exact", "||ads.example.com^$third-party")])

    def test_subdomain_covered_by_parent_domain_rule(self):
        ours = rules("||cdn.ads.example.com^$third-party,script\n")
        theirs = rules("||ads.example.com^\n")
        found = overlap.compare(ours, theirs)
        self.assertEqual([f.kind for f in found], ["covered"])
        self.assertEqual(found[0].by, "||ads.example.com^")

    def test_not_covered_when_upstream_is_narrower(self):
        ours = rules("||ads.example.com^\n")
        theirs = rules("||ads.example.com^$script\n||cdn.ads.example.com^\n||ads.example.com^$domain=a.com\n")
        self.assertEqual(overlap.compare(ours, theirs), [])

    def test_cosmetic_covered_by_generic_rule(self):
        ours = rules("example.com##.ad-slot\n")
        theirs = rules("##.ad-slot\n")
        self.assertEqual([f.kind for f in overlap.compare(ours, theirs)], ["covered"])

    def test_cosmetic_covered_by_parent_domain_rule(self):
        ours = rules("m.youtube.com##ytm-ad\n")
        theirs = rules("example.org,youtube.com##ytm-ad\n")
        found = overlap.compare(ours, theirs)
        self.assertEqual([f.kind for f in found], ["covered"])

    def test_cosmetic_not_covered_by_unrelated_domain(self):
        ours = rules("m.youtube.com##ytm-ad\n")
        theirs = rules("example.org##ytm-ad\nyoutube.com,~m.youtube.com##ytm-ad\n")
        self.assertEqual(overlap.compare(ours, theirs), [])

    def test_exceptions_are_ignored(self):
        ours = rules("@@||example.com/ads.js^\n")
        theirs = rules("@@||example.com/ads.js^\n")
        self.assertEqual(overlap.compare(ours, theirs), [])

    def test_upstream_preprocessor_lines_skipped(self):
        theirs = rules("!#if env_mobile\n||ads.example.com^\n!#endif\n")
        self.assertEqual(len(theirs), 1)


class UpstreamWatchTest(unittest.TestCase):
    SOURCES = [
        {"id": "original", "license": "GPL-3.0"},
        {"id": "uassets", "license": "GPL-3.0", "watch": {"repo": "uBlockOrigin/uAssets", "branch": "master"}},
        {"id": "brave-lists", "license": "MPL-2.0", "watch": {"repo": "brave/adblock-lists", "branch": "master"}},
    ]

    def fake_fetch(self, repo, branch):
        return {"uBlockOrigin/uAssets": {"sha": "bbb", "date": "2026-11-05T00:00:00Z"},
                "brave/adblock-lists": {"sha": "ccc", "date": "2026-11-05T00:00:00Z"}}[repo]

    def test_detects_changed_and_new_sources(self):
        lock = {"uassets": {"sha": "aaa"}, "brave-lists": {"sha": "ccc"}}
        changes = uw.check_sources(self.SOURCES, lock, self.fake_fetch)
        self.assertEqual([(c.source_id, c.old_sha, c.new_sha) for c in changes], [("uassets", "aaa", "bbb")])

    def test_source_missing_from_lock_is_reported(self):
        changes = uw.check_sources(self.SOURCES, {}, self.fake_fetch)
        self.assertEqual(sorted(c.source_id for c in changes), ["brave-lists", "uassets"])

    def test_report_mentions_manual_review(self):
        changes = uw.check_sources(self.SOURCES, {"uassets": {"sha": "aaa"}}, self.fake_fetch)
        text = uw.render_report(changes, self.SOURCES)
        self.assertIn("uassets", text)
        self.assertIn("https://github.com/uBlockOrigin/uAssets/compare/aaa...bbb", text)
        self.assertIn("自動では本番フィルターに反映しません", text)

    def test_fetch_failure_is_reported_not_raised(self):
        def flaky(repo, branch):
            if repo == "uBlockOrigin/uAssets":
                raise OSError("network down")
            return self.fake_fetch(repo, branch)
        failures = []
        changes = uw.check_sources(self.SOURCES, {}, flaky, failures)
        self.assertEqual([c.source_id for c in changes], ["brave-lists"])
        self.assertEqual(failures, [("uassets", "network down")])
        text = uw.render_report(changes, self.SOURCES, failures)
        self.assertIn("取得失敗", text)
        self.assertIn("uassets", text)

    def test_parse_ls_remote_output(self):
        out = "0123456789abcdef0123456789abcdef01234567\trefs/heads/master\n"
        self.assertEqual(uw.parse_ls_remote(out), "0123456789abcdef0123456789abcdef01234567")
        with self.assertRaises(ValueError):
            uw.parse_ls_remote("")

    def test_updated_lock(self):
        changes = uw.check_sources(self.SOURCES, {"uassets": {"sha": "aaa"}}, self.fake_fetch)
        lock = uw.updated_lock({"uassets": {"sha": "aaa"}}, changes)
        self.assertEqual(lock["uassets"]["sha"], "bbb")
        self.assertEqual(lock["brave-lists"]["sha"], "ccc")


if __name__ == "__main__":
    unittest.main()
