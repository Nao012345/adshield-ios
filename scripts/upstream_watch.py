"""Watch upstream filter projects for new commits (report only).

Never edits filters/: a change upstream only produces a report (and, in CI, an
issue) so a maintainer can review it by hand.

Usage:
    python scripts/upstream_watch.py [--report FILE] [--update-lock]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCK = ROOT / "upstream" / "lock.json"
SOURCES = ROOT / "upstream" / "sources.json"


@dataclass
class Change:
    source_id: str
    repo: str
    old_sha: str | None
    new_sha: str
    date: str


def parse_ls_remote(output: str) -> str:
    first = output.strip().split("\n", 1)[0]
    sha = first.split("\t", 1)[0].strip()
    if len(sha) != 40:
        raise ValueError(f"unexpected git ls-remote output: {output!r}")
    return sha


def git_fetch(repo: str, branch: str) -> dict:
    """Latest commit of a public GitHub branch via git (no API rate limit)."""
    out = subprocess.run(
        ["git", "ls-remote", f"https://github.com/{repo}.git", f"refs/heads/{branch}"],
        capture_output=True, text=True, timeout=60, check=True,
    ).stdout
    return {"sha": parse_ls_remote(out), "date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}


def check_sources(sources: list[dict], lock: dict, fetch=git_fetch, failures: list | None = None) -> list[Change]:
    """Compare upstream heads with the lock. Fetch errors go to ``failures``."""
    changes = []
    for src in sources:
        watch = src.get("watch")
        if not watch:
            continue
        try:
            latest = fetch(watch["repo"], watch["branch"])
        except Exception as exc:  # report and continue with the other sources
            if failures is None:
                raise
            failures.append((src["id"], str(exc)))
            continue
        old = lock.get(src["id"], {}).get("sha")
        if old != latest["sha"]:
            changes.append(Change(src["id"], watch["repo"], old, latest["sha"], latest["date"]))
    return changes


def render_report(changes: list[Change], sources: list[dict], failures: list | None = None) -> str:
    lines = ["# 上流フィルターの更新監視", ""]
    for source_id, err in failures or []:
        lines.append(f"- 取得失敗: {source_id} ({err})")
    if failures:
        lines.append("")
    if not changes:
        lines.append("前回の確認以降、監視対象に変更はありません。")
        return "\n".join(lines) + "\n"
    lines += [
        "以下の上流リポジトリに新しいコミットがあります。",
        "**自動では本番フィルターに反映しません。** 差分を読み、AdShield に必要な補完ルールだけを",
        "`staging/` で検証してから `filters/` に移してください。",
        "",
        "| ソース | リポジトリ | 差分 | 確認日時 (UTC) |",
        "|---|---|---|---|",
    ]
    for c in changes:
        if c.old_sha:
            diff = f"https://github.com/{c.repo}/compare/{c.old_sha}...{c.new_sha}"
        else:
            diff = f"https://github.com/{c.repo}/commit/{c.new_sha} (初回記録)"
        lines.append(f"| {c.source_id} | {c.repo} | {diff} | {c.date} |")
    lines += ["", "確認後に `python scripts/upstream_watch.py --update-lock` を実行してコミットしてください。"]
    return "\n".join(lines) + "\n"


def updated_lock(lock: dict, changes: list[Change]) -> dict:
    new = {k: dict(v) for k, v in lock.items()}
    for c in changes:
        new[c.source_id] = {"sha": c.new_sha, "date": c.date}
    return new


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--report", help="write the markdown report to this file")
    ap.add_argument("--update-lock", action="store_true", help="record current upstream commits")
    args = ap.parse_args(argv)

    sources = json.loads(SOURCES.read_text(encoding="utf-8"))["sources"]
    lock = json.loads(LOCK.read_text(encoding="utf-8")) if LOCK.is_file() else {}
    failures: list = []
    changes = check_sources(sources, lock, failures=failures)
    report = render_report(changes, sources, failures)
    if args.report:
        Path(args.report).write_text(report, encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print(report)
    if args.update_lock:
        LOCK.write_text(json.dumps(updated_lock(lock, changes), indent=2, sort_keys=True) + "\n",
                        encoding="utf-8", newline="\n")
    print(f"changes={len(changes)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
