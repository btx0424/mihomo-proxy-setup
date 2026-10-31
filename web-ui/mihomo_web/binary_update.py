"""Download and replace the local mihomo binary from GitHub releases (stdlib only)."""

from __future__ import annotations

import argparse
import gzip
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

GITHUB_REPO = "MetaCubeX/mihomo"
API_LATEST = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"


def mihomo_home() -> Path:
    if env := os.environ.get("MIHOMO_HOME"):
        return Path(env).resolve()
    return Path.cwd().resolve()


def resolve_binary(root: Path | None = None) -> Path:
    root = root or mihomo_home()
    if env := os.environ.get("MIHOMO_BIN"):
        return Path(env).resolve()
    for f in sorted(root.glob("mihomo*")):
        if f.name.endswith(".sh") or not f.is_file():
            continue
        if os.access(f, os.X_OK):
            return f.resolve()
    for f in sorted(root.glob("mihomo*")):
        if f.name.endswith(".sh") or not f.is_file():
            continue
        return f.resolve()
    raise RuntimeError(
        f"no mihomo binary in {root} (download from https://wiki.metacubex.one/en/startup/)"
    )


def platform_tuple() -> tuple[str, str]:
    sys_name = platform.system().lower()
    mach = platform.machine().lower()
    if sys_name == "darwin":
        goos = "darwin"
    elif sys_name == "linux":
        goos = "linux"
    elif sys_name == "windows":
        goos = "windows"
    else:
        raise RuntimeError(f"unsupported OS for auto-update: {platform.system()}")

    if mach in ("x86_64", "amd64"):
        goarch = "amd64"
    elif mach in ("aarch64", "arm64"):
        goarch = "arm64"
    elif mach in ("armv7l", "armv7"):
        goarch = "armv7"
    elif mach in ("386", "i686"):
        goarch = "386"
    else:
        raise RuntimeError(f"unsupported CPU for auto-update: {platform.machine()}")
    return goos, goarch


def read_installed_version(bin_path: Path) -> str | None:
    try:
        out = subprocess.run(
            [str(bin_path), "-v"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        text = (out.stdout or "") + (out.stderr or "")
    except (OSError, subprocess.TimeoutExpired):
        text = bin_path.name
    m = re.search(r"\bv([\d.]+)\b", text)
    return m.group(1) if m else None


def _build_opener() -> urllib.request.OpenerDirector:
    proxy = os.environ.get("MIHOMO_UPDATE_PROXY") or os.environ.get("MIHOMO_CHECK_PROXY")
    if not proxy and os.environ.get("MIHOMO_USE_LOCAL_PROXY", "1") == "1":
        port = os.environ.get("MIHOMO_MIXED_PORT", "7890")
        proxy = f"http://127.0.0.1:{port}"
    if proxy:
        return urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": proxy, "https": proxy})
        )
    return urllib.request.build_opener()


def fetch_latest_release(timeout: float = 30) -> dict:
    opener = _build_opener()
    req = urllib.request.Request(
        API_LATEST,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "mihomo-setup-update/1.0",
        },
    )
    with opener.open(req, timeout=timeout) as resp:
        return json.load(resp)


def pick_asset(release: dict, goos: str, goarch: str) -> dict:
    tag = release.get("tag_name", "")
    version = tag.lstrip("v")
    assets = release.get("assets") or []
    names = {a["name"]: a for a in assets if a.get("name")}

    preferred = [
        f"mihomo-{goos}-{goarch}-v{version}.gz",
        f"mihomo-{goos}-{goarch}-{tag}.gz",
    ]
    for name in preferred:
        if name in names:
            return names[name]

    pat = re.compile(
        rf"^mihomo-{re.escape(goos)}-{re.escape(goarch)}-(?!.*compatible).*\.gz$"
    )
    for a in assets:
        if pat.match(a.get("name", "")):
            return a
    raise RuntimeError(
        f"no .gz release asset for {goos}/{goarch} in {tag} "
        f"(see https://github.com/{GITHUB_REPO}/releases)"
    )


def normalize_version(v: str) -> tuple[int, ...]:
    parts: list[int] = []
    for piece in v.strip().lstrip("v").split("."):
        try:
            parts.append(int(re.match(r"\d+", piece).group(0)))  # type: ignore[union-attr]
        except (ValueError, AttributeError):
            parts.append(0)
    return tuple(parts)


def compare_versions(a: str, b: str) -> int:
    ta, tb = normalize_version(a), normalize_version(b)
    if ta < tb:
        return -1
    if ta > tb:
        return 1
    return 0


def download_asset(url: str, dest: Path, timeout: float = 300) -> None:
    opener = _build_opener()
    req = urllib.request.Request(url, headers={"User-Agent": "mihomo-setup-update/1.0"})
    with opener.open(req, timeout=timeout) as resp, dest.open("wb") as out:
        shutil.copyfileobj(resp, out)


def gunzip_file(src: Path, dest: Path) -> None:
    with gzip.open(src, "rb") as fin, dest.open("wb") as fout:
        shutil.copyfileobj(fin, fout)


def binary_status(root: Path | None = None) -> dict:
    root = root or mihomo_home()
    bin_path = resolve_binary(root)
    installed = read_installed_version(bin_path)
    goos, goarch = platform_tuple()
    try:
        release = fetch_latest_release()
        latest = (release.get("tag_name") or "").lstrip("v")
        asset = pick_asset(release, goos, goarch)
        update_available = (
            installed is not None
            and latest
            and compare_versions(installed, latest) < 0
        ) or (installed is None and bool(latest))
    except Exception as e:
        return {
            "binary": str(bin_path),
            "installed_version": installed,
            "latest_version": None,
            "update_available": False,
            "platform": f"{goos}/{goarch}",
            "error": str(e),
        }
    return {
        "binary": str(bin_path),
        "installed_version": installed,
        "latest_version": latest,
        "latest_tag": release.get("tag_name"),
        "update_available": update_available,
        "platform": f"{goos}/{goarch}",
        "asset_name": asset.get("name"),
        "release_url": release.get("html_url"),
    }


def update_binary(*, restart: bool = False, force: bool = False, root: Path | None = None) -> dict:
    root = root or mihomo_home()
    status = binary_status(root)
    if status.get("error"):
        raise RuntimeError(status["error"])

    bin_path = Path(status["binary"])
    installed = status.get("installed_version")
    latest = status.get("latest_version")
    if not latest:
        raise RuntimeError("could not determine latest release version")

    if (
        not force
        and installed
        and compare_versions(installed, latest) >= 0
    ):
        return {
            **status,
            "updated": False,
            "message": f"already at v{installed} (latest v{latest})",
        }

    release = fetch_latest_release()
    goos, goarch = platform_tuple()
    asset = pick_asset(release, goos, goarch)
    url = asset["browser_download_url"]

    was_running = _is_mihomo_running(root)
    script = root / "mihomo.sh"

    with tempfile.TemporaryDirectory(prefix="mihomo-update-") as tmp:
        tmpdir = Path(tmp)
        gz_path = tmpdir / asset["name"]
        new_bin = tmpdir / "mihomo-new"
        download_asset(url, gz_path)
        gunzip_file(gz_path, new_bin)
        new_bin.chmod(new_bin.stat().st_mode | 0o755)

        tag = release.get("tag_name", f"v{latest}").lstrip("v")
        target_name = f"mihomo-{goos}-{goarch}-v{tag}"
        target_path = root / target_name

        if was_running and script.is_file():
            subprocess.run([str(script), "stop"], check=False, cwd=root)

        backup = None
        if bin_path.exists():
            backup = bin_path.with_suffix(bin_path.suffix + f".bak.{int(time.time())}")
            shutil.copy2(bin_path, backup)

        shutil.copy2(new_bin, target_path)
        target_path.chmod(target_path.stat().st_mode | 0o755)

        if bin_path.resolve() != target_path.resolve() and bin_path.exists():
            try:
                bin_path.unlink()
            except OSError:
                pass

        os.environ["MIHOMO_BIN"] = str(target_path)

    new_installed = read_installed_version(target_path)
    result = {
        **binary_status(root),
        "updated": True,
        "previous_version": installed,
        "installed_version": new_installed,
        "backup": str(backup) if backup else None,
        "message": f"updated to v{new_installed or latest}",
    }

    if restart and was_running and script.is_file():
        proc = subprocess.run(
            [str(script), "restart"],
            capture_output=True,
            text=True,
            cwd=root,
        )
        result["restart"] = {
            "ok": proc.returncode == 0,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }
    elif was_running:
        result["restart_hint"] = "mihomo was running — run: mihomo restart"

    return result


def _is_mihomo_running(root: Path) -> bool:
    script = root / "mihomo.sh"
    if not script.is_file():
        return False
    proc = subprocess.run(
        [str(script), "status"],
        capture_output=True,
        text=True,
        cwd=root,
    )
    return "running" in (proc.stdout or "").lower()


def format_status_text(status: dict) -> str:
    lines = [
        f"binary   : {status.get('binary')}",
        f"platform : {status.get('platform')}",
        f"installed: v{status.get('installed_version') or '?'}",
    ]
    if status.get("error"):
        lines.append(f"latest   : (lookup failed) {status['error']}")
    else:
        lines.append(f"latest   : v{status.get('latest_version') or '?'}")
        if status.get("asset_name"):
            lines.append(f"asset    : {status['asset_name']}")
        if status.get("update_available"):
            lines.append("update   : available")
        else:
            lines.append("update   : up to date")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Update mihomo binary from GitHub releases")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_status = sub.add_parser("status", help="Show installed vs latest version")
    p_status.add_argument("--json", action="store_true")

    p_up = sub.add_parser("update", help="Download and install latest release")
    p_up.add_argument("--json", action="store_true")
    p_up.add_argument(
        "--restart",
        action="store_true",
        help="Restart mihomo if it was running before update",
    )
    p_up.add_argument(
        "--force",
        action="store_true",
        help="Re-download even if version matches",
    )

    args = parser.parse_args(argv)
    root = mihomo_home()

    try:
        if args.cmd == "status":
            st = binary_status(root)
            if args.json:
                print(json.dumps(st, indent=2))
            else:
                print(format_status_text(st))
            return 0

        result = update_binary(restart=args.restart, force=args.force, root=root)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(result.get("message", "done"))
            print(format_status_text(result))
            if result.get("restart_hint"):
                print(result["restart_hint"])
        return 0
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
