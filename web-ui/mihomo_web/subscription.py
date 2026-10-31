"""Subscription provider status and refresh via mihomo REST API (stdlib only)."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

SUBSCRIPTION_VEHICLE_TYPES = frozenset({"HTTP", "File", "Inline"})


def api_base() -> str:
    return os.environ.get("MIHOMO_API", "http://127.0.0.1:9090").rstrip("/")


def _get_json(url: str, timeout: float = 15) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.load(resp)


def _put(url: str, timeout: float = 120) -> None:
    req = urllib.request.Request(url, method="PUT")
    urllib.request.urlopen(req, timeout=timeout).read()


def _parse_updated_at(raw: str | None) -> float | None:
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except ValueError:
        return None


def format_age(seconds: float | None) -> str:
    if seconds is None:
        return "unknown"
    if seconds < 0:
        seconds = 0
    if seconds < 45:
        return f"{int(seconds)}s ago"
    if seconds < 90:
        return "1m ago"
    minutes = int(seconds // 60)
    if minutes < 60:
        return f"{minutes}m ago"
    hours = int(minutes // 60)
    if hours < 48:
        rem = minutes % 60
        return f"{hours}h {rem}m ago" if rem else f"{hours}h ago"
    days = int(hours // 24)
    return f"{days}d ago"


def list_subscription_providers(api: str | None = None) -> list[dict]:
    api = (api or api_base()).rstrip("/")
    data = _get_json(f"{api}/providers/proxies")
    now = time.time()
    rows: list[dict] = []

    for name, meta in sorted((data.get("providers") or {}).items()):
        vehicle = (meta.get("vehicleType") or "").strip()
        if vehicle and vehicle not in SUBSCRIPTION_VEHICLE_TYPES:
            continue
        # Skip synthetic groups like PROXY (Compatible)
        if vehicle == "Compatible":
            continue

        updated_raw = meta.get("updatedAt")
        updated_ts = _parse_updated_at(updated_raw)
        age_s = (now - updated_ts) if updated_ts is not None else None
        rows.append(
            {
                "name": name,
                "vehicle_type": vehicle or "?",
                "updated_at": updated_raw,
                "updated_at_unix": updated_ts,
                "age_seconds": age_s,
                "age_human": format_age(age_s),
                "proxy_count": len(meta.get("proxies") or []),
                "subscription_info": meta.get("subscriptionInfo"),
            }
        )
    return rows


def refresh_providers(
    names: list[str] | None = None, api: str | None = None
) -> list[dict]:
    api = (api or api_base()).rstrip("/")
    available = {r["name"]: r for r in list_subscription_providers(api)}
    if not available:
        raise RuntimeError("no subscription proxy-providers found (is mihomo running?)")

    targets = names if names else list(available.keys())
    for name in targets:
        if name not in available:
            hints = [n for n in available if name.lower() in n.lower()][:5]
            msg = f"unknown provider {name!r}"
            if hints:
                msg += f"; did you mean: {', '.join(hints)}"
            raise RuntimeError(msg)

    for name in targets:
        url = f"{api}/providers/proxies/{urllib.parse.quote(name, safe='')}"
        try:
            _put(url)
        except urllib.error.URLError as e:
            raise RuntimeError(f"refresh failed for {name!r}: {e}") from e

    return list_subscription_providers(api)


def format_status_text(providers: list[dict], *, title: str = "Subscription providers") -> str:
    lines = [title, ""]
    lines.append(f"{'PROVIDER':<14} {'UPDATED':<12} {'PROXIES':>7}  LAST REFRESH (UTC)")
    lines.append("-" * 72)
    for p in providers:
        utc = "—"
        if p.get("updated_at"):
            ts = _parse_updated_at(p["updated_at"])
            if ts is not None:
                utc = datetime.fromtimestamp(ts, tz=timezone.utc).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
        lines.append(
            f"{p['name']:<14} {p['age_human']:<12} {p['proxy_count']:>7}  {utc}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mihomo subscription provider status/refresh")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_status = sub.add_parser("status", help="Show time since last provider fetch")
    p_status.add_argument("--json", action="store_true")

    p_refresh = sub.add_parser("refresh", help="PUT /providers/proxies/<name> to fetch now")
    p_refresh.add_argument(
        "providers",
        nargs="*",
        help="Provider names (default: all subscription providers)",
    )
    p_refresh.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)
    api = api_base()

    try:
        if args.cmd == "status":
            rows = list_subscription_providers(api)
            if args.json:
                print(json.dumps({"providers": rows}, indent=2))
            else:
                print(format_status_text(rows))
            return 0

        rows = refresh_providers(args.providers or None, api)
        if args.json:
            print(json.dumps({"providers": rows, "refreshed": True}, indent=2))
        else:
            print(format_status_text(rows, title="Refreshed subscription providers"))
        return 0
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(
            f"error: mihomo API not reachable at {api} (is it running? try: mihomo start)",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
