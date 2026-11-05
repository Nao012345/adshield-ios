"""Detect rules that Brave's default lists already cover.

AdShield should only *complement* Brave's built-in lists, so any production
rule that is an exact duplicate (or is covered by a broader upstream rule) is
reported so it can be removed.
"""
from __future__ import annotations

from dataclasses import dataclass

import filterlib as fl


@dataclass
class Finding:
    rule: fl.Rule
    kind: str  # "exact" | "covered"
    by: str


def _anchored_host(rule: fl.Rule) -> str | None:
    """Host of a pure ``||host^`` rule, else None."""
    p = rule.pattern or ""
    if not p.startswith("||"):
        return None
    host = p[2:]
    if host.endswith("^"):
        host = host[:-1]
    if not host or any(c in host for c in "/*^|?:"):
        return None
    return host.lower()


def _host_covers(parent: str, child: str) -> bool:
    return child == parent or child.endswith("." + parent)


def compare(ours: list[fl.Rule], theirs: list[fl.Rule]) -> list[Finding]:
    keys = {}
    host_rules: dict[str, list[fl.Rule]] = {}
    generic_selectors: dict[str, fl.Rule] = {}
    specific_selectors: dict[str, list[fl.Rule]] = {}
    for r in theirs:
        if r.errors and "non-ascii" not in r.errors:
            continue
        keys.setdefault(r.key, r)
        if r.kind == "network" and not r.domains and not r.excluded_domains:
            host = _anchored_host(r)
            if host:
                host_rules.setdefault(host, []).append(r)
        elif r.kind == "cosmetic" and not r.excluded_domains:
            if not r.domains:
                generic_selectors.setdefault(r.selector, r)
            else:
                specific_selectors.setdefault(r.selector, []).append(r)

    findings: list[Finding] = []
    for r in ours:
        if r.is_exception:
            continue
        if r.key in keys:
            findings.append(Finding(r, "exact", keys[r.key].raw))
            continue
        if r.kind == "network":
            host = _anchored_host(r) or _host_prefix(r)
            if host:
                hit = _covering_host_rule(host, r, host_rules)
                if hit:
                    findings.append(Finding(r, "covered", hit.raw))
        elif r.kind == "cosmetic" and r.selector in generic_selectors:
            findings.append(Finding(r, "covered", generic_selectors[r.selector].raw))
        elif r.kind == "cosmetic" and r.domains and not r.excluded_domains:
            for cand in specific_selectors.get(r.selector, []):
                if all(any(_host_covers(p, d) for p in cand.domains) for d in r.domains):
                    findings.append(Finding(r, "covered", cand.raw))
                    break
    return findings


def _host_prefix(rule: fl.Rule) -> str | None:
    p = rule.pattern or ""
    if not p.startswith("||"):
        return None
    m = fl.HOST_PART_RE.match(p[2:])
    if not m or "*" in m.group(0):
        return None
    return m.group(0).lower().rstrip(".")


def _covering_host_rule(host: str, rule: fl.Rule, host_rules: dict) -> fl.Rule | None:
    ours_opts = {k for k in rule.options if k != "domain"}
    labels = host.split(".")
    for i in range(len(labels) - 1):
        parent = ".".join(labels[i:])
        for cand in host_rules.get(parent, []):
            cand_opts = set(cand.options)
            if cand_opts <= ours_opts and "match-case" not in cand_opts:
                return cand
    return None
