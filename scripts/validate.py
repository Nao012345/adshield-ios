"""Validate production filter sources (syntax, iOS compatibility, duplicates, licenses).

Usage:
    python scripts/validate.py            # production sources (filters/)
    python scripts/validate.py --staging  # also report on staging/ candidates

Exit code 1 when production sources have errors. Staging findings never fail.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import adshield_repo as repo  # noqa: E402
import filterlib as fl  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def staging_report(root: Path) -> list[str]:
    lines = []
    for path in sorted((root / "staging").rglob("*.txt")):
        rel = path.relative_to(root).as_posix()
        for e in fl.parse_source_text(path.read_text(encoding="utf-8"), rel):
            status = "OK " if not e.rule.errors else "NG "
            detail = ", ".join(e.rule.errors) if e.rule.errors else "iOS conversion policy OK"
            lines.append(f"{status}{rel}:{e.lineno}: {detail}: {e.rule.raw}")
    return lines


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--staging", action="store_true")
    args = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")

    report = repo.validate_repo(ROOT)
    rules = sum(len(v) for v in report.entries.values())
    for w in report.warnings:
        print("warning:", w)
    for e in report.errors:
        print("error:", e)
    config = repo.load_config(ROOT)
    if config["github_owner"] == "OWNER":
        print("warning: build.json github_owner is still the placeholder 'OWNER'")
    if args.staging:
        print("\n# staging/ (not published)")
        for line in staging_report(ROOT):
            print(line)
    print(f"\n{rules} production rules, {len(report.errors)} errors, {len(report.warnings)} warnings")
    return 1 if report.errors else 0


if __name__ == "__main__":
    sys.exit(main())
