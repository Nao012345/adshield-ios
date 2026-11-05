"""AdShield iOS filter library.

Parses Adblock-Plus-style filter rules and checks them against the subset that
Brave for iOS can apply. The checks mirror brave/adblock-rust
``src/content_blocking.rs`` (the converter Brave iOS uses to turn filter lists
into WebKit content-blocker rules) plus a stricter project policy:

* no scriptlets / procedural filters / HTML filters (we never rely on JS),
* no navigation-blocking types (``document``, ``popup``),
* ASCII only (the converter rejects non-ASCII rules).

Standard library only, Python 3.10+.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# --------------------------------------------------------------------------
# Option tables (network rules)
# --------------------------------------------------------------------------

# Resource types the iOS converter maps to WebKit resource types.
SUPPORTED_TYPES = {
    "script": "script",
    "image": "image",
    "stylesheet": "stylesheet",
    "css": "stylesheet",
    "font": "font",
    "media": "media",
    "subdocument": "subdocument",
    "frame": "subdocument",
    "xmlhttprequest": "xmlhttprequest",
    "xhr": "xmlhttprequest",
}
# Types that the converter silently drops (rule rejected if nothing else remains).
DROPPED_TYPES = {"object", "other", "ping", "beacon", "websocket"}
# Types we refuse for safety: they can block page navigation.
UNSAFE_TYPES = {"document", "doc", "popup", "popunder", "all"}

PARTY_OPTIONS = {
    "third-party": "third-party",
    "3p": "third-party",
    "~first-party": "third-party",
    "~1p": "third-party",
    "first-party": "first-party",
    "1p": "first-party",
    "~third-party": "first-party",
    "~3p": "first-party",
}
FLAG_OPTIONS = {"match-case": "match-case", "important": "important"}

# Options the converter rejects or that change semantics beyond blocking.
UNSUPPORTED_OPTIONS = {
    "redirect", "redirect-rule", "rewrite", "csp", "removeparam", "queryprune",
    "generichide", "ghide", "elemhide", "ehide", "specifichide", "shide",
    "badfilter", "replace", "header", "permissions", "uritransform", "urlskip",
    "cname", "empty", "mp4", "inline-script", "inline-font", "from", "to",
    "denyallow", "method", "strict1p", "strict3p", "jsonprune", "hls",
    "network", "content", "jsinject", "urlblock", "stealth", "cookie",
    "app", "extension", "genericblock", "ipaddress", "reason",
}

PROCEDURAL_OPERATORS = (
    ":has-text(", ":-abp-has(", ":-abp-contains(", ":-abp-properties(",
    ":contains(", ":matches-css(", ":matches-css-before(", ":matches-css-after(",
    ":matches-attr(", ":matches-path(", ":matches-prop(", ":matches-media(",
    ":min-text-length(", ":upward(", ":xpath(", ":watch-attr(", ":watch-attrs(",
    ":others(", ":remove(", ":remove-attr(", ":remove-class(", ":shadow(",
    ":if(", ":if-not(", ":nth-ancestor(",
)
DANGEROUS_SELECTORS = {"html", "body", "head", ":root", "*", "html > body", "html>body"}

DOMAIN_RE = re.compile(r"^(?:\*\.)?[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)*$")
COSMETIC_RE = re.compile(r"^([^#\s]*?)(#@?[$?%]?#)(.*)$")
HOST_PART_RE = re.compile(r"^[a-z0-9.*-]+", re.IGNORECASE)

# --------------------------------------------------------------------------
# License compatibility (reuse of third-party rules inside our list)
# --------------------------------------------------------------------------

# Licenses whose material may be included in a work distributed under the key.
COMPATIBLE_LICENSES = {
    "GPL-3.0": {"GPL-3.0", "GPL-3.0-only", "GPL-3.0-or-later", "GPL-2.0-or-later",
                "MPL-2.0", "LGPL-3.0", "LGPL-2.1-or-later", "MIT", "BSD-2-Clause",
                "BSD-3-Clause", "ISC", "Apache-2.0", "CC0-1.0", "Unlicense"},
    "MIT": {"MIT", "BSD-2-Clause", "BSD-3-Clause", "ISC", "CC0-1.0", "Unlicense"},
}


def license_reuse_allowed(source_license: str, our_license: str) -> bool:
    """True when rules under ``source_license`` may be copied into our list."""
    key = "GPL-3.0" if our_license in {"GPL-3.0", "GPL-3.0-only", "GPL-3.0-or-later"} else our_license
    return source_license in COMPATIBLE_LICENSES.get(key, set())


# --------------------------------------------------------------------------
# Rule model
# --------------------------------------------------------------------------

@dataclass
class Rule:
    raw: str
    kind: str  # network | network-exception | cosmetic | cosmetic-exception | unsupported
    pattern: str | None = None
    options: dict = field(default_factory=dict)
    domains: tuple = ()
    excluded_domains: tuple = ()
    selector: str | None = None
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    key: tuple = ()

    @property
    def is_network(self) -> bool:
        return self.kind in ("network", "network-exception")

    @property
    def is_exception(self) -> bool:
        return self.kind.endswith("-exception")


@dataclass
class SourceEntry:
    rule: Rule
    path: str
    lineno: int
    source: str


def _is_comment(line: str) -> bool:
    return line.startswith("!") or line.startswith("[") or line.startswith("# ") or line == "#"


def parse_line(line: str) -> Rule | None:
    """Parse one filter line. Returns None for blanks, comments and headers."""
    line = line.strip()
    if not line or _is_comment(line):
        return None
    rule = _parse_cosmetic(line) or _parse_network(line)
    if not line.isascii():
        rule.errors.insert(0, "non-ascii")
    return rule


def _check_domain_list(rule: Rule, names: list[str]) -> tuple[tuple, tuple]:
    include, exclude = [], []
    for name in names:
        neg = name.startswith("~")
        name = name[1:] if neg else name
        if name.endswith(".*"):
            _add(rule.errors, "entity-domain")
            continue
        if not DOMAIN_RE.match(name):
            if name.isascii():
                _add(rule.errors, "invalid-domain")
            continue
        (exclude if neg else include).append(name)
    if include and exclude:
        _add(rule.errors, "mixed-include-exclude")
    return tuple(sorted(set(include))), tuple(sorted(set(exclude)))


def _add(lst: list, item: str) -> None:
    if item not in lst:
        lst.append(item)


def _parse_cosmetic(line: str) -> Rule | None:
    if "$$" in line or "$@$" in line:
        head = line.split("$$", 1)[0].split("$@$", 1)[0]
        if "/" not in head and "^" not in head:
            return Rule(raw=line, kind="unsupported", errors=["html-filter"], key=("raw", line))
    m = COSMETIC_RE.match(line)
    if not m:
        return None
    domain_part, marker, selector = m.group(1), m.group(2), m.group(3).strip()
    exception = marker.startswith("#@")
    rule = Rule(raw=line, kind="cosmetic-exception" if exception else "cosmetic", selector=selector)
    names = [d.strip() for d in domain_part.split(",") if d.strip()]
    rule.domains, rule.excluded_domains = _check_domain_list(rule, names)

    if marker not in ("##", "#@#"):
        _add(rule.errors, "unsupported-cosmetic-syntax")
    elif selector.startswith("+js("):
        _add(rule.errors, "scriptlet")
    elif selector.startswith("^"):
        _add(rule.errors, "html-filter")
    else:
        _check_selector(rule, selector)

    if exception and not names:
        _add(rule.errors, "generic-cosmetic-exception")
    rule.key = ("cosmetic", exception, rule.domains, rule.excluded_domains, selector)
    return rule


def _check_selector(rule: Rule, selector: str) -> None:
    low = selector.lower()
    if not selector:
        _add(rule.errors, "invalid-selector")
        return
    if ":style(" in low:
        _add(rule.errors, "style-action")
    if any(op in low for op in PROCEDURAL_OPERATORS):
        _add(rule.errors, "procedural")
    if ":has(" in low:
        _add(rule.errors, "has-pseudo-unverified")
    if low.strip() in DANGEROUS_SELECTORS:
        _add(rule.errors, "dangerous-selector")
    if "{" in selector or "}" in selector or "<" in selector or not _balanced(selector):
        _add(rule.errors, "invalid-selector")


def _balanced(text: str) -> bool:
    stack: list[str] = []
    quote = None
    pairs = {")": "(", "]": "["}
    i = 0
    while i < len(text):
        c = text[i]
        if quote:
            if c == "\\":
                i += 1
            elif c == quote:
                quote = None
        elif c in "\"'":
            quote = c
        elif c in "([":
            stack.append(c)
        elif c in ")]":
            if not stack or stack.pop() != pairs[c]:
                return False
        i += 1
    return quote is None and not stack


def _split_options(body: str) -> tuple[str, str | None]:
    idx = body.rfind("$")
    if idx <= 0:
        return body, None
    candidate = body[idx + 1:]
    if not candidate or not re.match(r"^~?[a-z0-9-]+(=|,|$)", candidate, re.IGNORECASE):
        return body, None
    return body[:idx], candidate


def _parse_network(line: str) -> Rule:
    exception = line.startswith("@@")
    body = line[2:] if exception else line
    pattern, opt_text = _split_options(body)
    rule = Rule(raw=line, kind="network-exception" if exception else "network", pattern=pattern)

    if len(pattern) >= 2 and pattern.startswith("/") and pattern.endswith("/"):
        _add(rule.errors, "regex-rule")

    options: dict = {}
    types: set[str] = set()
    had_type = False
    if opt_text:
        for raw_opt in opt_text.split(","):
            raw_opt = raw_opt.strip()
            name, _, value = raw_opt.partition("=")
            lname = name.lower()
            base = lname.lstrip("~")
            if lname == "domain":
                names = [d.strip() for d in value.split("|") if d.strip()]
                inc, exc = _check_domain_list(rule, names)
                rule.domains, rule.excluded_domains = inc, exc
                options["domain"] = "|".join(list(inc) + ["~" + d for d in exc])
            elif lname in PARTY_OPTIONS:
                options[PARTY_OPTIONS[lname]] = None
            elif lname in FLAG_OPTIONS:
                options[FLAG_OPTIONS[lname]] = None
            elif base in SUPPORTED_TYPES or base in DROPPED_TYPES or base in UNSAFE_TYPES:
                had_type = True
                if lname.startswith("~"):
                    _add(rule.errors, "negated-type-unverified")
                elif base in UNSAFE_TYPES:
                    _add(rule.errors, "unsafe-type:" + base)
                elif base in SUPPORTED_TYPES:
                    types.add(SUPPORTED_TYPES[base])
                    options[SUPPORTED_TYPES[base]] = None
                else:
                    _add(rule.warnings, "dropped-type:" + base)
            elif base in UNSUPPORTED_OPTIONS:
                _add(rule.errors, "unsupported-option:" + base)
            else:
                _add(rule.errors, "unknown-option:" + base)
    if had_type and not types and not any(e.startswith(("unsafe-type", "negated")) for e in rule.errors):
        _add(rule.errors, "no-supported-type")
    rule.options = options

    core = pattern.replace("||", "").replace("|", "").replace("^", "").replace("*", "")
    if len(core) < 4 and not rule.domains:
        _add(rule.errors, "too-broad")

    if pattern.startswith("||"):
        host = HOST_PART_RE.match(pattern[2:])
        host_text = host.group(0).rstrip(".") if host else ""
        if not host_text or not re.search(r"[a-z0-9]\.[a-z0-9*]", host_text, re.IGNORECASE):
            if "regex-rule" not in rule.errors and "too-broad" not in rule.errors:
                _add(rule.errors, "invalid-host-anchor")
    elif not rule.domains and not pattern.startswith("|") and "regex-rule" not in rule.errors:
        _add(rule.warnings, "generic-pattern")

    rule.key = ("network", exception, pattern.lower() if "match-case" not in options else pattern,
                tuple(sorted(options.items(), key=lambda kv: kv[0])))
    return rule


# --------------------------------------------------------------------------
# Matching (used by safety tests; ignores resource types = conservative)
# --------------------------------------------------------------------------

_regex_cache: dict[str, re.Pattern] = {}


def pattern_to_regex(pattern: str) -> re.Pattern:
    cached = _regex_cache.get(pattern)
    if cached:
        return cached
    p = pattern
    prefix, suffix = "", ""
    if p.startswith("||"):
        prefix = r"^[a-z][a-z0-9+.\-]*://(?:[^/?#]*\.)?"
        p = p[2:]
    elif p.startswith("|"):
        prefix = "^"
        p = p[1:]
    if p.endswith("|"):
        suffix = "$"
        p = p[:-1]
    out = []
    for ch in p:
        if ch == "*":
            out.append(".*")
        elif ch == "^":
            out.append(r"(?:[^\w.%\-]|$)")
        else:
            out.append(re.escape(ch))
    compiled = re.compile(prefix + "".join(out) + suffix, re.IGNORECASE)
    _regex_cache[pattern] = compiled
    return compiled


def _host_matches(host: str, domain: str) -> bool:
    return host == domain or host.endswith("." + domain)


def network_matches(rule: Rule, url: str, page_host: str | None = None) -> bool:
    """Does ``rule`` (network) match ``url``?

    If ``page_host`` is None the ``domain=`` restriction is treated as satisfied
    (worst case), so safety checks stay conservative.
    """
    if not rule.is_network or rule.pattern is None or rule.errors and "regex-rule" in rule.errors:
        return False
    if page_host is not None:
        if rule.domains and not any(_host_matches(page_host, d) for d in rule.domains):
            return False
        if any(_host_matches(page_host, d) for d in rule.excluded_domains):
            return False
    return bool(pattern_to_regex(rule.pattern).search(url))


def is_blocked(rules: list[Rule], url: str, page_host: str | None = None) -> Rule | None:
    """Return the blocking rule for ``url`` (None when allowed or excepted)."""
    blocker = None
    for rule in rules:
        if rule.kind == "network" and network_matches(rule, url, page_host):
            blocker = rule
            break
    if blocker is None:
        return None
    for rule in rules:
        if rule.kind == "network-exception" and network_matches(rule, url, page_host):
            return None
    return blocker


# --------------------------------------------------------------------------
# Source files
# --------------------------------------------------------------------------

DIRECTIVE_RE = re.compile(r"^!\s*@(\w+)\s*:\s*(.*?)\s*$")


def parse_source_text(text: str, path: str) -> list[SourceEntry]:
    """Parse a source filter file, tracking ``! @source: <id>`` provenance."""
    entries: list[SourceEntry] = []
    source = "original"
    for lineno, line in enumerate(text.splitlines(), start=1):
        d = DIRECTIVE_RE.match(line.strip())
        if d:
            if d.group(1) == "source":
                source = d.group(2)
            continue
        rule = parse_line(line)
        if rule is not None:
            entries.append(SourceEntry(rule=rule, path=path, lineno=lineno, source=source))
    return entries


def parse_list_text(text: str) -> list[Rule]:
    """Parse an arbitrary (upstream) list; unparseable lines are kept as rules with errors."""
    rules = []
    for line in text.splitlines():
        if line.startswith("!#"):  # uBO preprocessor directives
            continue
        rule = parse_line(line)
        if rule is not None:
            rules.append(rule)
    return rules
