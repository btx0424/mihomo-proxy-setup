"""Thin wrappers around mihomo.sh and the mihomo REST API (mirrors mihomo.sh)."""

from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

SELECTOR_TYPES = frozenset({"Selector", "URLTest", "Fallback", "LoadBalance"})


@dataclass(frozen=True)
class Paths:
    root: Path
    script: Path
    conf_dir: Path
    log_file: Path
    api: str
    bench_url: str
    bench_timeout_ms: int


def mihomo_home() -> Path:
    if env := os.environ.get("MIHOMO_HOME"):
        return Path(env).resolve()
    # web-ui/mihomo_web/backend.py -> repo root
    return Path(__file__).resolve().parents[2]


def paths() -> Paths:
    root = mihomo_home()
    conf = Path(os.environ.get("MIHOMO_CONF", root / "config"))
    return Paths(
        root=root,
        script=root / "mihomo.sh",
        conf_dir=conf,
        log_file=Path(os.environ.get("MIHOMO_LOG", conf / "mihomo.log")),
        api=os.environ.get("MIHOMO_API", "http://127.0.0.1:9090").rstrip("/"),
        bench_url=os.environ.get(
            "MIHOMO_BENCH_URL", "https://www.gstatic.com/generate_204"
        ),
        bench_timeout_ms=int(os.environ.get("MIHOMO_BENCH_TIMEOUT", "5000")),
    )


def run_script(command: str, *args: str) -> dict:
    p = paths()
    if not p.script.is_file():
        return {
            "ok": False,
            "returncode": 127,
            "stdout": "",
            "stderr": f"mihomo.sh not found at {p.script}",
        }
    proc = subprocess.run(
        [str(p.script), command, *args],
        cwd=p.root,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def _api_json(url: str, timeout: float = 10) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.load(resp)


def _ensure_api() -> None:
    p = paths()
    try:
        urllib.request.urlopen(p.api, timeout=2).read()
    except (urllib.error.URLError, TimeoutError) as e:
        raise RuntimeError(
            f"mihomo API not reachable at {p.api} (is it running? try: mihomo start)"
        ) from e


def list_groups() -> list[dict]:
    _ensure_api()
    p = paths()
    data = _api_json(f"{p.api}/proxies")
    rows: list[dict] = []
    for name, proxy in sorted((data.get("proxies") or {}).items()):
        if proxy.get("type") not in SELECTOR_TYPES:
            continue
        rows.append(
            {
                "name": name,
                "type": proxy.get("type", ""),
                "now": proxy.get("now", ""),
            }
        )
    return rows


def list_nodes(group: str = "PROXY") -> dict:
    _ensure_api()
    p = paths()
    url = f"{p.api}/proxies/{urllib.parse.quote(group, safe='')}"
    try:
        proxy = _api_json(url)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"cannot read group {group!r}: {e}") from e
    members = proxy.get("all") or []
    now = proxy.get("now", "")
    return {
        "group": group,
        "type": proxy.get("type", ""),
        "now": now,
        "members": [
            {"name": name, "current": name == now} for name in members
        ],
    }


def current_selection(group: str = "PROXY") -> dict:
    _ensure_api()
    p = paths()
    url = f"{p.api}/proxies/{urllib.parse.quote(group, safe='')}"
    proxy = _api_json(url)
    chain = [{"group": group, "now": proxy.get("now", "")}]
    now = proxy.get("now")
    if now:
        all_proxies = _api_json(f"{p.api}/proxies").get("proxies") or {}
        leaf = all_proxies.get(now)
        if leaf and leaf.get("type") in SELECTOR_TYPES and leaf.get("now"):
            chain.append({"group": now, "now": leaf.get("now", "")})
    return {"chain": chain}


def bench_group(group: str = "PROXY") -> dict:
    _ensure_api()
    p = paths()
    gurl = f"{p.api}/proxies/{urllib.parse.quote(group, safe='')}"
    try:
        g = _api_json(gurl)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"cannot read group {group!r}: {e}") from e
    now = g.get("now", "")

    delay_url = (
        f"{p.api}/group/{urllib.parse.quote(group, safe='')}/delay"
        f"?url={urllib.parse.quote(p.bench_url, safe='')}"
        f"&timeout={p.bench_timeout_ms}"
    )
    timeout_s = max(60, int(p.bench_timeout_ms / 1000 * 120))
    try:
        delays = _api_json(delay_url, timeout=timeout_s)
    except (urllib.error.URLError, TimeoutError) as e:
        raise RuntimeError(f"delay test failed: {e}") from e

    ok: list[dict] = []
    bad: list[dict] = []
    for name, val in delays.items():
        if isinstance(val, dict):
            delay = val.get("delay") or 0
            msg = val.get("message") or ""
        elif isinstance(val, int):
            delay, msg = val, ""
        else:
            delay, msg = 0, str(val)
        row = {
            "name": name,
            "delay_ms": delay if delay and delay > 0 else 0,
            "message": msg,
            "current": name == now,
        }
        if row["delay_ms"] > 0:
            ok.append(row)
        else:
            bad.append(row)
    ok.sort(key=lambda r: r["delay_ms"])
    bad.sort(key=lambda r: r["name"])
    return {
        "group": group,
        "current": now,
        "ok": ok,
        "failed": bad,
        "summary": {
            "ok": len(ok),
            "fail": len(bad),
            "total": len(delays),
        },
        "fastest": ok[0] if ok else None,
    }


def select_node(group: str, node: str) -> dict:
    _ensure_api()
    p = paths()
    proxies = _api_json(f"{p.api}/proxies").get("proxies") or {}
    if group not in proxies:
        raise RuntimeError(f"unknown group {group!r}")
    members = proxies[group].get("all") or []
    if node not in members:
        hints = [m for m in members if node.lower() in m.lower()][:8]
        msg = f"{node!r} is not a member of {group!r}"
        if hints:
            msg += "; did you mean: " + ", ".join(hints)
        raise RuntimeError(msg)

    req = urllib.request.Request(
        f"{p.api}/proxies/{urllib.parse.quote(group, safe='')}",
        data=json.dumps({"name": node}).encode(),
        headers={"Content-Type": "application/json"},
        method="PUT",
    )
    try:
        urllib.request.urlopen(req, timeout=10).read()
    except urllib.error.URLError as e:
        raise RuntimeError(f"select failed: {e}") from e

    cur = _api_json(
        f"{p.api}/proxies/{urllib.parse.quote(group, safe='')}"
    ).get("now")
    return {"group": group, "now": cur}


def tail_log(lines: int = 80) -> str:
    p = paths()
    if not p.log_file.is_file():
        return ""
    text = p.log_file.read_text(errors="replace")
    chunk = text.splitlines()[-lines:]
    return "\n".join(chunk)


def proxy_snippets() -> dict:
    mixed = os.environ.get("MIHOMO_MIXED_PORT", "7890")
    socks = os.environ.get("MIHOMO_SOCKS_PORT", "7891")
    on = (
        f"export http_proxy=http://127.0.0.1:{mixed}\n"
        f"export https_proxy=http://127.0.0.1:{mixed}\n"
        f"export HTTP_PROXY=http://127.0.0.1:{mixed}\n"
        f"export HTTPS_PROXY=http://127.0.0.1:{mixed}\n"
        f"export all_proxy=socks5://127.0.0.1:{socks}\n"
        f"export ALL_PROXY=socks5://127.0.0.1:{socks}\n"
        f"export no_proxy=localhost,127.0.0.1,::1\n"
        f"export NO_PROXY=localhost,127.0.0.1,::1"
    )
    off = (
        "unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY\n"
        "unset all_proxy ALL_PROXY no_proxy NO_PROXY"
    )
    return {
        "on_shell": on,
        "off_shell": off,
        "on_one_liner": f"proxy-on  # or source your ~/.zshrc helpers",
        "mixed_port": mixed,
        "socks_port": socks,
    }


def usage_check(*, direct: bool = False, timeout: float | None = None) -> dict:
    from mihomo_web.usage_probes import format_text, run_checks

    report = run_checks(direct=direct, timeout=timeout)
    report["text"] = format_text(report)
    return report


def subscription_status() -> dict:
    from mihomo_web.subscription import format_status_text, list_subscription_providers

    p = paths()
    rows = list_subscription_providers(p.api)
    return {
        "providers": rows,
        "text": format_status_text(rows),
    }


def subscription_refresh(names: list[str] | None = None) -> dict:
    from mihomo_web.subscription import format_status_text, refresh_providers

    p = paths()
    rows = refresh_providers(names, p.api)
    return {
        "providers": rows,
        "text": format_status_text(rows, title="Refreshed subscription providers"),
    }


def binary_status() -> dict:
    from mihomo_web.binary_update import binary_status as _status

    return _status(paths().root)


def binary_update(*, restart: bool = False, force: bool = False) -> dict:
    from mihomo_web.binary_update import update_binary

    return update_binary(restart=restart, force=force, root=paths().root)
