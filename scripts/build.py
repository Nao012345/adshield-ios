"""Generate dist/*.txt from filters/ (refuses to build when validation fails).

Usage:
    python scripts/build.py          # write dist/
    python scripts/build.py --check  # exit 1 if dist/ is not up to date
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import adshield_repo as repo  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="verify dist/ matches the sources")
    args = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        if args.check:
            stale = repo.stale_dist_files(ROOT)
            if stale:
                print("dist/ is out of date; run: python scripts/build.py")
                for name in stale:
                    print("  stale:", name)
                return 1
            print("dist/ is up to date")
            return 0
        for name in repo.write_dist(ROOT):
            print("wrote dist/" + name)
        return 0
    except repo.BuildError as exc:
        print(exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
