"""Publish a built exe distribution as a GitHub Release (developer-side).

Pairs with ``tools/build_exe.py --zip`` and ``tools/update_exe.py``:

    1. python tools/build_exe.py --zip          # -> Master-Report_<ver>_win64.zip
    2. python tools/publish_release.py --zip build_exe/Master-Report_<ver>_win64.zip

This computes the zip's SHA-256, writes a ``SHA256SUMS`` file next to it, and
creates a GitHub Release (tag ``v<ver>``) with BOTH files attached. The exe
updater (``update_exe.py`` / ``ОБНОВИТЬ_EXE.bat``) then fetches the latest
release and verifies the download against ``SHA256SUMS`` — that published
checksum is the real integrity check (the zip's own digest is self-referential
and cannot detect a compromised/truncated download).

Requires the GitHub CLI (``gh``) authenticated (``gh auth login``). If ``gh``
is missing, the script prints the exact manual steps instead of failing.

Usage:
    python tools/publish_release.py --zip <zip> [--tag v5.7] [--notes "..."]
                                    [--repo sunil123456897/Exel_otchet]
"""
from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import subprocess
import sys
from pathlib import Path

DEFAULT_REPO = "sunil123456897/Exel_otchet"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _version_from_zip(zip_path: Path) -> str:
    m = re.search(r"Master-Report_([^_]+)_win64\.zip", zip_path.name)
    if m:
        return m.group(1)
    m = re.search(r"(\d+\.\d+(?:\.\d+)?)", zip_path.name)
    return m.group(1) if m else "0.0"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--zip", required=True, help="path to Master-Report_<ver>_win64.zip")
    ap.add_argument("--tag", default=None, help="release tag (default: v<version>)")
    ap.add_argument("--repo", default=DEFAULT_REPO, help="owner/repo")
    ap.add_argument("--notes", default="", help="release notes")
    ap.add_argument("--draft", action="store_true", help="create as draft")
    args = ap.parse_args()

    zip_path = Path(args.zip).resolve()
    if not zip_path.is_file():
        sys.exit(f"[publish] zip not found: {zip_path}")

    version = _version_from_zip(zip_path)
    tag = args.tag or f"v{version}"

    # Write SHA256SUMS in the `sha256sum` format the updater parses:
    # "<hex>  <filename>" (two spaces; the binary "*" marker also accepted).
    sha = _sha256(zip_path)
    sums_path = zip_path.parent / "SHA256SUMS"
    sums_path.write_text(f"{sha}  {zip_path.name}\n", encoding="utf-8")
    print(f"[publish] {zip_path.name}  sha256={sha[:16]}…")
    print(f"[publish] wrote {sums_path}")

    if shutil.which("gh") is None:
        print()
        print("[publish] GitHub CLI (gh) not found. Create the release manually:")
        print(f"  gh release create {tag} "
              f'"{zip_path}" "{sums_path}" '
              f'--repo {args.repo} --title "Master-Report {version}" '
              f'--notes "{args.notes or "exe distribution"}"')
        print("(or upload the two files via the GitHub web UI: "
              f"https://github.com/{args.repo}/releases/new?tag={tag})")
        return 0

    cmd = [
        "gh", "release", "create", tag,
        str(zip_path), str(sums_path),
        "--repo", args.repo,
        "--title", f"Master-Report {version}",
        "--notes", args.notes or f"Master-Report {version} — exe distribution",
    ]
    if args.draft:
        cmd.append("--draft")
    print(f"[publish] running: {' '.join(cmd)}")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        # Most common cause: the tag already exists. Tell the operator.
        print(f"[publish] gh failed (rc={result.returncode}). If the tag exists, "
              f"delete it first: gh release delete {tag} --repo {args.repo}")
        return result.returncode
    print(f"[publish] release {tag} published to {args.repo}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
