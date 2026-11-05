"""Repository-level operations: validation of sources and generation of dist/.

Used by scripts/validate.py and scripts/build.py (thin CLIs) and by the tests.
Standard library only.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import filterlib as fl

EXPIRES_RE = re.compile(r"^(\d+) (hour|hours|day|days)$")
# WebKit content blockers accept at most 150,000 rules per list; stay far below.
MAX_RULES_PER_BUNDLE = 50_000


class BuildError(Exception):
    pass


@dataclass
class Report:
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    entries: dict = field(default_factory=dict)  # path -> list[SourceEntry]


def load_config(root: Path) -> dict:
    return json.loads((root / "build.json").read_text(encoding="utf-8"))


def load_sources(root: Path) -> dict:
    data = json.loads((root / "upstream" / "sources.json").read_text(encoding="utf-8"))
    return {s["id"]: s for s in data["sources"]}


def read_version(root: Path) -> str:
    return (root / "VERSION").read_text(encoding="utf-8").strip()


def production_paths(config: dict) -> list[str]:
    seen: list[str] = []
    for bundle in config["bundles"]:
        if bundle["sources"] == "*":
            continue
        for path in bundle["sources"]:
            if path not in seen:
                seen.append(path)
    return seen


def bundle_paths(config: dict, bundle: dict) -> list[str]:
    return production_paths(config) if bundle["sources"] == "*" else list(bundle["sources"])


def bundle_ids_for_canary(config: dict, bundle: dict) -> list[str]:
    if bundle["sources"] == "*":
        return [b["id"] for b in config["bundles"]]
    return [bundle["id"]]


def pages_host(config: dict) -> str:
    return f"{config['github_owner'].lower()}.github.io"


def canary_rules(config: dict, bundle_id: str) -> list[str]:
    """Rules that only affect the project's own install-check page."""
    owner, name = config["github_owner"], config["repo_name"]
    return [
        f"||cdn.jsdelivr.net/gh/{owner}/{name}@*/site/test/canary/{bundle_id}.js^",
        f"{pages_host(config)}##.adshield-canary-{bundle_id}",
    ]


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------

def validate_config(config: dict, root: Path, report: Report) -> None:
    m = EXPIRES_RE.match(config.get("expires", ""))
    if not m:
        report.errors.append(f"build.json: Expires '{config.get('expires')}' must be '<n> hours' or '<n> days'")
    else:
        n, unit = int(m.group(1)), m.group(2)
        limit = 14 if unit.startswith("day") else 336
        if not 1 <= n <= limit:
            report.errors.append(f"build.json: Expires '{config['expires']}' outside adblock-rust range (1-14 days / 1-336 hours)")
    files = set()
    for bundle in config["bundles"]:
        for key in ("title", "description"):
            if not bundle.get(key, "").isascii():
                report.errors.append(f"build.json: bundle '{bundle['id']}' {key} must be ASCII")
        if bundle["file"] in files:
            report.errors.append(f"build.json: duplicate output file {bundle['file']}")
        files.add(bundle["file"])
        if bundle["sources"] != "*":
            for path in bundle["sources"]:
                if not (root / path).is_file():
                    report.errors.append(f"build.json: missing source file {path}")


def validate_repo(root: Path) -> Report:
    root = Path(root)
    report = Report()
    config = load_config(root)
    validate_config(config, root, report)
    sources = load_sources(root)
    seen: dict = {}

    for path in production_paths(config):
        file = root / path
        if not file.is_file():
            continue
        data = file.read_bytes()
        if data.startswith(b"\xef\xbb\xbf"):
            report.errors.append(f"{path}: UTF-8 BOM is not allowed")
            data = data[3:]
        entries = fl.parse_source_text(data.decode("utf-8"), path)
        report.entries[path] = entries
        for e in entries:
            loc = f"{path}:{e.lineno}"
            if e.rule.errors:
                report.errors.append(f"{loc}: {', '.join(e.rule.errors)}: {e.rule.raw}")
            for w in e.rule.warnings:
                report.warnings.append(f"{loc}: {w}: {e.rule.raw}")
            src = sources.get(e.source)
            if src is None:
                report.errors.append(f"{loc}: unknown source '{e.source}' (add it to upstream/sources.json)")
            elif not fl.license_reuse_allowed(src.get("license", ""), config["license"]):
                report.errors.append(f"{loc}: license of source '{e.source}' ({src.get('license')}) "
                                     f"is not compatible with {config['license']}")
            if e.rule.key in seen:
                report.errors.append(f"{loc}: duplicate of {seen[e.rule.key]}: {e.rule.raw}")
            else:
                seen[e.rule.key] = loc
    return report


# --------------------------------------------------------------------------
# Build
# --------------------------------------------------------------------------

def render_bundle(config: dict, bundle: dict, report: Report, version: str) -> str:
    body: list[str] = []
    keys: set = set()
    count = 0
    sections = [(path, [e.rule for e in report.entries.get(path, [])]) for path in bundle_paths(config, bundle)]
    canaries = []
    for bid in bundle_ids_for_canary(config, bundle):
        canaries.extend(fl.parse_line(r) for r in canary_rules(config, bid))
    sections.append(("generated: install check canary (affects only the project's test page)", canaries))

    for title, rules in sections:
        lines = []
        for rule in rules:
            if rule.key in keys:
                continue
            keys.add(rule.key)
            lines.append(rule.raw)
        if lines:
            body.append(f"! ---- {title} ----")
            body.extend(lines)
            count += len(lines)

    if count > MAX_RULES_PER_BUNDLE:
        raise BuildError(f"{bundle['file']}: {count} rules exceeds {MAX_RULES_PER_BUNDLE}")
    digest = hashlib.sha256("\n".join(body).encode("utf-8")).hexdigest()[:16]
    owner, name = config["github_owner"], config["repo_name"]
    header = [
        "[Adblock Plus 2.0]",
        f"! Title: {bundle['title']}",
        f"! Description: {bundle['description']}",
        f"! Version: {version}",
        f"! Expires: {config['expires']}",
        f"! Homepage: https://github.com/{owner}/{name}",
        f"! License: {config['license']} (https://github.com/{owner}/{name}/blob/main/LICENSE)",
        f"! Content-Hash: sha256:{digest}",
        f"! Rules: {count}",
        "! Generated by scripts/build.py - do not edit; edit filters/ instead.",
        "!",
    ]
    return "\n".join(header + body) + "\n"


def build_outputs(root: Path) -> dict:
    root = Path(root)
    report = validate_repo(root)
    if report.errors:
        raise BuildError("validation failed:\n" + "\n".join(report.errors))
    config = load_config(root)
    version = read_version(root)
    return {b["file"]: render_bundle(config, b, report, version) for b in config["bundles"]}


def write_dist(root: Path) -> list[str]:
    root = Path(root)
    outputs = build_outputs(root)
    dist = root / "dist"
    dist.mkdir(exist_ok=True)
    for name, text in outputs.items():
        (dist / name).write_text(text, encoding="utf-8", newline="\n")
    return sorted(outputs)


def stale_dist_files(root: Path) -> list[str]:
    root = Path(root)
    stale = []
    for name, text in build_outputs(root).items():
        path = root / "dist" / name
        if not path.is_file() or path.read_bytes() != text.encode("utf-8"):
            stale.append(name)
    return stale
