"""Unit tests for the rule parser and the iOS-Brave compatibility policy.

The policy mirrors brave/adblock-rust src/content_blocking.rs: rules that the
iOS content-blocker conversion rejects (or that need features we refuse to rely
on, such as scriptlets) must be reported as errors.
"""
import unittest

import helpers  # noqa: F401  (sets sys.path)
import filterlib as fl


def errors(line):
    rule = fl.parse_line(line)
    assert rule is not None, line
    return rule.errors


class ParseBasicsTest(unittest.TestCase):
    def test_blank_and_comment_lines_are_not_rules(self):
        self.assertIsNone(fl.parse_line(""))
        self.assertIsNone(fl.parse_line("   "))
        self.assertIsNone(fl.parse_line("! comment"))
        self.assertIsNone(fl.parse_line("[Adblock Plus 2.0]"))

    def test_network_rule_kind_and_options(self):
        rule = fl.parse_line("||ads.example.com^$third-party,script")
        self.assertEqual(rule.kind, "network")
        self.assertEqual(rule.pattern, "||ads.example.com^")
        self.assertEqual(rule.options, {"third-party": None, "script": None})
        self.assertEqual(rule.errors, [])

    def test_network_exception_kind(self):
        rule = fl.parse_line("@@||example.com/ads.js^$script")
        self.assertEqual(rule.kind, "network-exception")
        self.assertEqual(rule.errors, [])

    def test_cosmetic_rule_with_domains(self):
        rule = fl.parse_line("b.example.com,a.example.com##.ad-banner")
        self.assertEqual(rule.kind, "cosmetic")
        self.assertEqual(rule.domains, ("a.example.com", "b.example.com"))
        self.assertEqual(rule.selector, ".ad-banner")
        self.assertEqual(rule.errors, [])

    def test_generic_cosmetic_rule(self):
        rule = fl.parse_line("##.adsbygoogle")
        self.assertEqual(rule.kind, "cosmetic")
        self.assertEqual(rule.domains, ())
        self.assertEqual(rule.errors, [])

    def test_cosmetic_exception_kind(self):
        rule = fl.parse_line("example.com#@#.ad-banner")
        self.assertEqual(rule.kind, "cosmetic-exception")
        self.assertEqual(rule.errors, [])

    def test_hash_inside_url_is_not_cosmetic(self):
        rule = fl.parse_line("||example.com/page#anchor")
        self.assertEqual(rule.kind, "network")


class IosCompatibilityTest(unittest.TestCase):
    def test_scriptlet_rejected(self):
        self.assertIn("scriptlet", errors("example.com##+js(set-constant, a, 1)"))

    def test_adguard_scriptlet_rejected(self):
        self.assertIn("unsupported-cosmetic-syntax", errors("example.com#%#//scriptlet('abort-on-property-read', 'x')"))

    def test_procedural_rejected(self):
        self.assertIn("procedural", errors("example.com##div:has-text(Sponsored)"))
        self.assertIn("procedural", errors("example.com##.ad:upward(2)"))

    def test_has_pseudo_rejected_until_verified(self):
        self.assertIn("has-pseudo-unverified", errors("example.com##div:has(> .ad)"))

    def test_style_action_rejected(self):
        self.assertIn("style-action", errors("example.com##body:style(overflow: auto !important)"))

    def test_remove_action_rejected(self):
        self.assertIn("procedural", errors("example.com##.ad:remove()"))

    def test_html_filter_rejected(self):
        self.assertIn("html-filter", errors("example.com##^script:has-text(ad)"))
        self.assertIn("html-filter", errors("example.com$$script[tag-content=\"ad\"]"))

    def test_extended_css_markers_rejected(self):
        self.assertIn("unsupported-cosmetic-syntax", errors("example.com#?#.ad"))
        self.assertIn("unsupported-cosmetic-syntax", errors("example.com#$#.ad { display: none; }"))

    def test_regex_network_rule_rejected(self):
        self.assertIn("regex-rule", errors("/ads[0-9]+\\.js/$script"))

    def test_unsupported_network_options_rejected(self):
        self.assertIn("unsupported-option:redirect", errors("||example.com/ad.js$script,redirect=noopjs"))
        self.assertIn("unsupported-option:csp", errors("||example.com^$csp=script-src 'none'"))
        self.assertIn("unsupported-option:removeparam", errors("||example.com^$removeparam=utm_source"))
        self.assertIn("unsupported-option:generichide", errors("@@||example.com^$generichide"))
        self.assertIn("unsupported-option:from", errors("||ads.example.com^$from=example.org"))
        self.assertIn("unsupported-option:badfilter", errors("||ads.example.com^$badfilter"))

    def test_unknown_option_rejected(self):
        self.assertIn("unknown-option:frobnicate", errors("||ads.example.com^$frobnicate"))

    def test_navigation_blocking_types_rejected(self):
        self.assertIn("unsafe-type:document", errors("||ads.example.com^$document"))
        self.assertIn("unsafe-type:popup", errors("||ads.example.com^$popup"))

    def test_only_unsupported_types_rejected(self):
        self.assertIn("no-supported-type", errors("||ads.example.com^$websocket"))

    def test_mixed_domain_include_exclude_rejected(self):
        self.assertIn("mixed-include-exclude", errors("||ads.example.com^$domain=a.com|~b.a.com"))
        self.assertIn("mixed-include-exclude", errors("a.com,~b.a.com##.ad"))

    def test_entity_domain_rejected(self):
        self.assertIn("entity-domain", errors("example.*##.ad"))

    def test_non_ascii_rejected(self):
        self.assertIn("non-ascii", errors("例え.jp##.ad"))
        self.assertIn("non-ascii", errors("example.com##div[title=\"広告\"]"))

    def test_too_broad_network_rule_rejected(self):
        self.assertIn("too-broad", errors("ad"))
        self.assertIn("too-broad", errors("*$script"))

    def test_invalid_domain_rejected(self):
        self.assertIn("invalid-domain", errors("Example.COM##.ad"))
        self.assertIn("invalid-domain", errors("||ads.example.com^$domain=bad_domain!"))

    def test_dangerous_selector_rejected(self):
        for sel in ("html", "body", ":root", "*", "head"):
            self.assertIn("dangerous-selector", errors("example.com##" + sel), sel)

    def test_css_injection_selector_rejected(self):
        self.assertIn("invalid-selector", errors("example.com##.ad{display:block}"))
        self.assertIn("invalid-selector", errors("example.com##div[class=\"ad\""))

    def test_generic_cosmetic_exception_rejected(self):
        self.assertIn("generic-cosmetic-exception", errors("#@#.ad"))

    def test_generic_network_pattern_warns(self):
        rule = fl.parse_line("/ads/banner_")
        self.assertEqual(rule.errors, [])
        self.assertIn("generic-pattern", rule.warnings)


class DedupeKeyTest(unittest.TestCase):
    def test_option_aliases_and_order_normalized(self):
        a = fl.parse_line("||ads.example.com^$3p,script")
        b = fl.parse_line("||ads.example.com^$script,third-party")
        self.assertEqual(a.key, b.key)

    def test_domain_order_normalized(self):
        a = fl.parse_line("a.com,b.com##.ad")
        b = fl.parse_line("b.com,a.com##.ad")
        self.assertEqual(a.key, b.key)

    def test_block_and_exception_differ(self):
        a = fl.parse_line("||ads.example.com^")
        b = fl.parse_line("@@||ads.example.com^")
        self.assertNotEqual(a.key, b.key)


class NetworkMatchTest(unittest.TestCase):
    def match(self, line, url):
        return fl.network_matches(fl.parse_line(line), url)

    def test_hostname_anchor_matches_subdomains(self):
        self.assertTrue(self.match("||ads.example.com^", "https://ads.example.com/x.js"))
        self.assertTrue(self.match("||example.com^", "https://cdn.example.com/x.js"))

    def test_hostname_anchor_does_not_match_lookalike_hosts(self):
        self.assertFalse(self.match("||example.com^", "https://notexample.com/x.js"))
        self.assertFalse(self.match("||example.com^", "https://example.com.evil.net/"))

    def test_separator_and_wildcard(self):
        self.assertTrue(self.match("||example.com/ads/*.js", "https://example.com/ads/a/b.js"))
        self.assertFalse(self.match("||example.com/ads^", "https://example.com/adsx"))
        self.assertTrue(self.match("||example.com/ads^", "https://example.com/ads?x=1"))

    def test_plain_substring(self):
        self.assertTrue(self.match("/ads/banner_", "https://x.com/ads/banner_1.png"))
        self.assertFalse(self.match("/ads/banner_", "https://x.com/news/"))


class LicenseTest(unittest.TestCase):
    def test_compatible_licenses(self):
        self.assertTrue(fl.license_reuse_allowed("GPL-3.0", "GPL-3.0"))
        self.assertTrue(fl.license_reuse_allowed("MPL-2.0", "GPL-3.0"))
        self.assertTrue(fl.license_reuse_allowed("CC0-1.0", "GPL-3.0"))

    def test_incompatible_or_unknown_licenses(self):
        self.assertFalse(fl.license_reuse_allowed("CC-BY-NC-4.0", "GPL-3.0"))
        self.assertFalse(fl.license_reuse_allowed("NOASSERTION", "GPL-3.0"))
        self.assertFalse(fl.license_reuse_allowed("GPL-3.0", "MIT"))


class SourceFileTest(unittest.TestCase):
    def test_source_directive_tracks_provenance(self):
        text = "! @source: uassets\n||ads.example.com^\n! @source: original\nexample.com##.ad\n"
        entries = fl.parse_source_text(text, "x.txt")
        self.assertEqual([(e.rule.raw, e.source) for e in entries],
                         [("||ads.example.com^", "uassets"), ("example.com##.ad", "original")])
        self.assertEqual(entries[0].lineno, 2)

    def test_default_source_is_original(self):
        entries = fl.parse_source_text("||ads.example.com^\n", "x.txt")
        self.assertEqual(entries[0].source, "original")


if __name__ == "__main__":
    unittest.main()
