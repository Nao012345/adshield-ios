"""Assemble the GitHub Pages site: dist/*.txt + site/ pages with placeholders filled.

Usage:
    python scripts/make_site.py --out _site [--owner NAME]

Placeholders in site/*.html and site/**/*.js: {{OWNER}} {{REPO}} {{VERSION}} {{PAGES_BASE}}
Refuses to run while build.json still has the placeholder owner 'OWNER'.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import adshield_repo as repo  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TEMPLATED = {".html", ".js", ".txt", ".md"}


class SiteError(Exception):
    pass


def make_site(root: Path, out: Path, owner: str | None = None) -> list[str]:
    root, out = Path(root), Path(out)
    config = repo.load_config(root)
    owner = owner or config["github_owner"]
    if owner == "OWNER":
        raise SiteError("build.json github_owner is still 'OWNER'; set your GitHub user name first")
    name = config["repo_name"]
    values = {
        "{{OWNER}}": owner,
        "{{REPO}}": name,
        "{{VERSION}}": repo.read_version(root),
        "{{PAGES_BASE}}": f"https://{owner.lower()}.github.io/{name}/",
    }
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    written = []
    for src in sorted((root / "site").rglob("*")):
        if not src.is_file():
            continue
        rel = src.relative_to(root / "site")
        dst = out / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.suffix in TEMPLATED:
            text = src.read_text(encoding="utf-8")
            for key, value in values.items():
                text = text.replace(key, value)
            dst.write_text(text, encoding="utf-8", newline="\n")
        else:
            shutil.copyfile(src, dst)
        written.append(rel.as_posix())
    for txt in sorted((root / "dist").glob("*.txt")):
        shutil.copyfile(txt, out / txt.name)
        written.append(txt.name)
    (out / ".nojekyll").write_text("", encoding="utf-8")
    return written


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="_site")
    ap.add_argument("--owner", help="override build.json github_owner")
    args = ap.parse_args(argv)
    try:
        for rel in make_site(ROOT, Path(args.out), args.owner):
            print("site:", rel)
    except SiteError as exc:
        print("error:", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
