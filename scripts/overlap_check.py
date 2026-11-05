"""Report production rules already covered by Brave's default lists.

Downloads the lists in upstream/baselines.json (public URLs from Brave's
filter list catalog) and compares them with filters/. Report only unless
--fail-on-overlap is given.

Usage:
    python scripts/overlap_check.py [--summary FILE] [--fail-on-overlap]
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import adshield_repo as repo  # noqa: E402
import filterlib as fl  # noqa: E402
import overlap  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def download(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "adshield-ios-overlap-check"})
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 (URLs from repo config)
        return resp.read().decode("utf-8", errors="replace")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--summary", help="append the markdown report to this file")
    ap.add_argument("--fail-on-overlap", action="store_true")
    args = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")

    report = repo.validate_repo(ROOT)
    ours = [(e, e.rule) for entries in report.entries.values() for e in entries]
    baselines = json.loads((ROOT / "upstream" / "baselines.json").read_text(encoding="utf-8"))["lists"]

    lines = ["# Brave 標準リストとの重複チェック", ""]
    total = 0
    loc = {id(r): f"{e.path}:{e.lineno}" for e, r in ours}
    for bl in baselines:
        theirs = []
        failed = []
        for url in bl["urls"]:
            try:
                theirs.extend(fl.parse_list_text(download(url)))
            except Exception as exc:  # network errors are reported, not fatal
                failed.append(f"{url} ({exc})")
        findings = overlap.compare([r for _, r in ours], theirs)
        total += len(findings)
        lines.append(f"## {bl['name']}（{len(theirs)} ルール{'、既定で有効' if bl.get('default_enabled') else ''}）")
        for f in failed:
            lines.append(f"- 取得失敗: {f}")
        if not findings:
            lines.append("- 重複なし")
        for f in findings:
            lines.append(f"- {f.kind}: `{f.rule.raw}` ({loc[id(f.rule)]}) ← `{f.by}`")
        lines.append("")
    lines.append(f"合計 {total} 件")
    text = "\n".join(lines) + "\n"
    print(text)
    if args.summary:
        with open(args.summary, "a", encoding="utf-8") as fh:
            fh.write(text)
    return 1 if (args.fail_on_overlap and total) else 0


if __name__ == "__main__":
    sys.exit(main())
