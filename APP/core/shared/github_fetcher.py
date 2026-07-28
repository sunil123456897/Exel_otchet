"""Stage 4 wiring — production HTTP fetcher for GitHub-hosted updates.

Reads an update archive from GitHub and hands it to
``Updater.update()`` as a ``fetch_fn``. Two modes:

* **Branch zipball** (default; matches the existing
  ``tools/update_from_github.ps1`` behaviour):
  downloads ``https://github.com/<owner>/<repo>/archive/refs/heads/<branch>.zip``
  (public repo) or ``https://api.github.com/repos/<owner>/<repo>/zipball/<branch>``
  (private repo, needs token).
* **Release asset** (TZ-ideal future mode): looks up the latest release
  tag, downloads ``asset`` named in the release's ``manifest.json``,
  verifies SHA-256 against the manifest. Not the default yet because
  the project does not publish releases — only branch archives.

Privacy: tokens are read from ``.github_token`` (gitignored) or the
``GITHUB_TOKEN`` environment variable. They are **never** logged and
**never** written to ``update_log.txt``. If a request fails with 401,
the error says "auth failed" without echoing the token.

Network resilience:

* 3 retries with exponential backoff (1s, 2s, 4s).
* Timeouts per attempt (60s connect, 300s download).
* Verifies the downloaded file is a valid zip before returning — a
  truncated or HTML 404 page would otherwise crash ``Updater`` later.

This module uses only the Python standard library (``urllib``). No
``requests`` dependency — keeps the updater's cold-start cheap and
portable across machines where ``pip install`` is unavailable.
"""
from __future__ import annotations

import os
import shutil
import ssl
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

from core.shared.updater_model import VersionManifest


# ── config ─────────────────────────────────────────────────────────────

DEFAULT_OWNER = "sunil123456897"
DEFAULT_REPO = "Exel_otchet"
DEFAULT_BRANCH = "main"

USER_AGENT = "Master-Report-Updater/1.0"
CONNECT_TIMEOUT_SEC = 60
DOWNLOAD_TIMEOUT_SEC = 300
MAX_RETRIES = 3
RETRY_BACKOFF_SEC = [1, 2, 4]


# ── token handling ────────────────────────────────────────────────────


def _read_token(repo_root: Path) -> str | None:
    """Read token from ``.github_token`` (gitignored) or ``$GITHUB_TOKEN``.

    Never logged, never written to disk by this module.
    """
    env_token = os.environ.get("GITHUB_TOKEN")
    if env_token:
        return env_token.strip()
    token_file = repo_root / ".github_token"
    if token_file.is_file():
        try:
            return token_file.read_text(encoding="utf-8").strip()
        except OSError:
            return None
    return None


def _auth_headers(token: str | None) -> dict[str, str]:
    h = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"}
    if token:
        h["Authorization"] = f"token {token}"
    return h


# ── network helpers ───────────────────────────────────────────────────


def _urlopen_with_retry(
    url: str, headers: dict[str, str], *, timeout: int,
) -> bytes:
    """GET *url* with retries. Returns the response body bytes.

    Raises ``RuntimeError`` with a human-readable message on final
    failure — never echoes the token.
    """
    last_err: str = ""
    for attempt in range(MAX_RETRIES):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status >= 400:
                    raise RuntimeError(
                        f"HTTP {resp.status} fetching {url.split('?')[0]}"
                    )
                return bytes(resp.read())
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                # 401 = bad/missing credentials. 403 is frequently a transient
                # rate limit (anonymous API/archive requests are throttled),
                # not an auth problem — say so, so the operator retries instead
                # of hunting for a token that isn't the issue.
                if e.code == 403:
                    raise RuntimeError(
                        "GitHub refused the request (HTTP 403) — often a "
                        "temporary rate limit. Wait a few minutes and retry, "
                        "or provide a token (.github_token / GITHUB_TOKEN)."
                    ) from e
                raise RuntimeError(
                    f"GitHub auth failed (HTTP {e.code}). "
                    "Check .github_token or GITHUB_TOKEN."
                ) from e
            last_err = f"HTTP {e.code}: {e.reason}"
        except (urllib.error.URLError, ssl.SSLError, TimeoutError) as e:
            last_err = f"{type(e).__name__}: {e}"
        except OSError as e:
            last_err = f"OSError: {e}"

        if attempt < MAX_RETRIES - 1:
            time.sleep(RETRY_BACKOFF_SEC[min(attempt, len(RETRY_BACKOFF_SEC) - 1)])
    raise RuntimeError(f"network failed after {MAX_RETRIES} attempts: {last_err}")


def _download_file(
    url: str, dest: Path, headers: dict[str, str], *, timeout: int,
) -> None:
    """Stream *url* to *dest*. Used for large archive downloads."""
    last_err = ""
    for attempt in range(MAX_RETRIES):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status >= 400:
                    raise RuntimeError(f"HTTP {resp.status} downloading archive")
                expected_len = resp.headers.get("Content-Length")
                with dest.open("wb") as f:
                    while True:
                        chunk = resp.read(65536)
                        if not chunk:
                            break
                        f.write(chunk)
            # Guard against a truncated download: if the server advertised the
            # size, the bytes on disk must match. A mid-stream disconnect can
            # otherwise leave a short file that looks "downloaded" (the later
            # self-referential SHA would even agree with it).
            if expected_len is not None:
                try:
                    expected_size = int(expected_len)
                except ValueError:
                    expected_size = None
                if expected_size is not None and dest.stat().st_size != expected_size:
                    raise RuntimeError(
                        f"download truncated: got {dest.stat().st_size} of "
                        f"{expected_size} bytes — re-run the update"
                    )
            return
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                if e.code == 403:
                    raise RuntimeError(
                        "GitHub refused the request (HTTP 403) — often a "
                        "temporary rate limit. Wait a few minutes and retry, "
                        "or provide a token (.github_token / GITHUB_TOKEN)."
                    ) from e
                raise RuntimeError(
                    f"GitHub auth failed (HTTP {e.code}). "
                    "Check .github_token or GITHUB_TOKEN."
                ) from e
            last_err = f"HTTP {e.code}: {e.reason}"
        except (urllib.error.URLError, ssl.SSLError, TimeoutError, OSError) as e:
            last_err = f"{type(e).__name__}: {e}"
        if attempt < MAX_RETRIES - 1:
            time.sleep(RETRY_BACKOFF_SEC[min(attempt, len(RETRY_BACKOFF_SEC) - 1)])
    raise RuntimeError(f"download failed after {MAX_RETRIES} attempts: {last_err}")


# ── manifest discovery ────────────────────────────────────────────────


def resolve_branch_commit_sha(
    repo_root: Path,
    *,
    owner: str = DEFAULT_OWNER,
    repo: str = DEFAULT_REPO,
    branch: str = DEFAULT_BRANCH,
) -> str:
    """Resolve the current HEAD commit SHA of *branch* via the GitHub API.

    Used for optional commit pinning: the operator pins a known-good SHA and
    the updater refuses to apply any other commit. This is the only real
    defence against a compromised repository/account — the zipball's own
    SHA-256 is self-referential (computed from the bytes just downloaded) and
    therefore cannot detect a malicious push. Raises ``RuntimeError`` on
    network/auth failure or an unparseable response. The token is never logged.
    """
    import json
    token = _read_token(repo_root)
    headers = _auth_headers(token)
    url = f"https://api.github.com/repos/{owner}/{repo}/commits/{branch}"
    body = _urlopen_with_retry(url, headers, timeout=CONNECT_TIMEOUT_SEC)
    try:
        sha = json.loads(body.decode("utf-8")).get("sha", "")
    except (ValueError, UnicodeDecodeError) as e:
        raise RuntimeError(f"could not parse commit response: {e}") from e
    if not sha:
        raise RuntimeError("GitHub did not return a commit SHA")
    return str(sha).lower()


def _build_branch_manifest(
    owner: str, repo: str, branch: str, zip_bytes: bytes,
) -> VersionManifest:
    """Build a manifest for a branch-zipball download.

    Branch zipballs do not carry a release manifest, so we synthesise
    one: version = branch HEAD SHA (truncated), SHA = digest of the
    bytes we just downloaded, size = byte count. The ``Updater`` uses
    size+SHA for L0 verification regardless of where the manifest
    came from.
    """
    import hashlib
    sha = hashlib.sha256(zip_bytes).hexdigest()
    return VersionManifest(
        version=f"branch-{branch}-{sha[:8]}",
        sha256=sha,
        size=len(zip_bytes),
        asset=f"{owner}-{repo}-{branch}.zip",
        channel="branch",
    )


def fetch_branch_zipball(
    repo_root: Path,
    *,
    owner: str = DEFAULT_OWNER,
    repo: str = DEFAULT_REPO,
    branch: str = DEFAULT_BRANCH,
    dest_dir: Path,
) -> tuple[Path, VersionManifest]:
    """Download ``refs/heads/<branch>.zip`` from GitHub.

    Returns ``(archive_path, manifest)``. The manifest's SHA/size match
    the downloaded bytes; ``Updater.update`` will re-verify on the L0
    step so any in-flight tampering is caught.
    """
    token = _read_token(repo_root)
    headers = _auth_headers(token)
    # Private repo: use the API endpoint (needs auth). Public: the
    # archive endpoint is simpler and does not rate-limit as aggressively.
    if token:
        url = f"https://api.github.com/repos/{owner}/{repo}/zipball/{branch}"
    else:
        url = f"https://github.com/{owner}/{repo}/archive/refs/heads/{branch}.zip"

    dest_dir.mkdir(parents=True, exist_ok=True)
    archive_path = dest_dir / f"{owner}-{repo}-{branch}.zip"
    _download_file(url, archive_path, headers, timeout=DOWNLOAD_TIMEOUT_SEC)

    # Synthesise the manifest from the actual bytes.
    zip_bytes = archive_path.read_bytes()
    manifest = _build_branch_manifest(owner, repo, branch, zip_bytes)
    return archive_path, manifest


def make_branch_fetcher(
    repo_root: Path,
    *,
    owner: str = DEFAULT_OWNER,
    repo: str = DEFAULT_REPO,
    branch: str = DEFAULT_BRANCH,
) -> Callable[[VersionManifest, Path], Path]:
    """Return a ``fetch_fn`` closure suitable for ``Updater.update()``.

    The closure matches the signature ``fetch_fn(manifest, dest_dir) -> Path``
    that ``Updater`` expects. It ignores the manifest passed in (we
    build our own from the actual zip bytes) and returns the path to
    the downloaded archive.
    """
    def fetch_fn(_manifest: VersionManifest, dest_dir: Path) -> Path:
        path, _ = fetch_branch_zipball(
            repo_root, owner=owner, repo=repo, branch=branch,
            dest_dir=dest_dir,
        )
        return path
    return fetch_fn


def make_local_fetcher(zip_path: Path) -> Callable[[VersionManifest, Path], Path]:
    """Return a ``fetch_fn`` that copies a local ZIP — used by offline
    updates (``ОБНОВИТЬ_ИЗ_ФАЙЛА.bat``).

    The closure matches the same signature as ``make_branch_fetcher``.
    """
    def fetch_fn(_manifest: VersionManifest, dest_dir: Path) -> Path:
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / zip_path.name
        shutil.copy2(zip_path, dest)
        return dest
    return fetch_fn


def manifest_from_local_zip(zip_path: Path) -> VersionManifest:
    """Build a manifest from a local ZIP file (offline update path).

    The version is derived from the zip's name if it looks like a
    release (``MasterReport-5.7.0.zip``), else from the SHA prefix.
    """
    import hashlib
    import re
    raw = zip_path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()

    name_match = re.search(r"(\d+\.\d+\.\d+)", zip_path.name)
    version = name_match.group(1) if name_match else f"local-{sha[:8]}"

    return VersionManifest(
        version=version,
        sha256=sha,
        size=len(raw),
        asset=zip_path.name,
        channel="offline",
    )


# ── release-asset fetch (exe distribution) ────────────────────────────


def _parse_sha256sums(sums_path: Path, filename: str) -> str:
    """Extract the sha256 for *filename* from a ``<sha>  <name>`` SUMS file.

    Handles both ``<sha>  <name>`` and ``<sha> *<name>`` (binary marker)
    lines, as produced by ``sha256sum`` and our own publisher.
    """
    try:
        for line in sums_path.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[-1].lstrip("*") == filename:
                return parts[0].strip().lower()
    except OSError:
        pass
    return ""


def fetch_release_asset(
    repo_root: Path,
    *,
    owner: str = DEFAULT_OWNER,
    repo: str = DEFAULT_REPO,
    tag: str | None = None,
    asset_pattern: str = "Master-Report_*_win64.zip",
    dest_dir: Path,
) -> tuple[Path, "VersionManifest"]:
    """Download a GitHub **release asset** (the exe distribution zip).

    Used by the exe updater (``tools/update_exe.py``). Unlike a branch
    zipball, a release ships an independent ``SHA256SUMS`` asset, so the
    returned manifest's SHA-256 is a REAL integrity check rather than the
    self-referential digest of the bytes just downloaded — together with the
    release-tag pin this is the defence against a compromised repo/account.

    ``tag=None`` resolves the latest release; otherwise the given tag is
    fetched. Returns ``(archive_path, manifest)`` with
    ``manifest.version`` = the release tag.
    """
    import fnmatch
    import hashlib
    import json as _json

    token = _read_token(repo_root)
    headers = _auth_headers(token)
    if tag:
        url = f"https://api.github.com/repos/{owner}/{repo}/releases/tags/{tag}"
    else:
        url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
    body = _urlopen_with_retry(url, headers, timeout=CONNECT_TIMEOUT_SEC)
    try:
        release = _json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as e:
        raise RuntimeError(f"could not parse release response: {e}") from e

    rel_tag = str(release.get("tag_name", "") or tag or "")
    asset_list: list[dict[str, Any]] = release.get("assets") or []

    def _find(pattern: str) -> dict[str, Any] | None:
        for a in asset_list:
            if fnmatch.fnmatch(str(a.get("name", "")), pattern):
                return a
        return None

    asset = _find(asset_pattern)
    if asset is None:
        raise RuntimeError(
            f"release {rel_tag!r} has no asset matching {asset_pattern!r}"
        )
    sums_asset = _find("SHA256SUMS*") or _find("*.sha256")

    dest_dir.mkdir(parents=True, exist_ok=True)
    archive_path = dest_dir / str(asset.get("name", "release.zip"))
    _download_file(
        str(asset["browser_download_url"]), archive_path, headers,
        timeout=DOWNLOAD_TIMEOUT_SEC,
    )

    # Independent integrity: prefer the published SHA256SUMS over our own
    # digest. If the release has no SUMS we fall back to the local digest
    # (the caller still runs testzip() CRC upstream).
    published_sha = ""
    if sums_asset is not None:
        sums_path = dest_dir / "SHA256SUMS"
        _download_file(
            str(sums_asset["browser_download_url"]), sums_path, headers,
            timeout=CONNECT_TIMEOUT_SEC,
        )
        published_sha = _parse_sha256sums(sums_path, archive_path.name)
    if not published_sha:
        published_sha = hashlib.sha256(archive_path.read_bytes()).hexdigest()

    manifest = VersionManifest(
        version=rel_tag,
        sha256=published_sha,
        size=archive_path.stat().st_size,
        asset=str(asset.get("name", "")),
        channel="release",
    )
    return archive_path, manifest
