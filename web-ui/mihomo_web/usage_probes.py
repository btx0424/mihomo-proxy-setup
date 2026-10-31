"""Parallel HTTP usage checks (Google, GitHub, Hugging Face) — stdlib only."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from typing import Callable

DEFAULT_TIMEOUT = float(os.environ.get("MIHOMO_CHECK_TIMEOUT", "15"))
USER_AGENT = os.environ.get(
    "MIHOMO_CHECK_UA",
    "mihomo-usage-check/1.0 (connectivity probe)",
)


@dataclass(frozen=True)
class Probe:
    id: str
    label: str
    url: str
    method: str = "GET"
    headers: tuple[tuple[str, str], ...] = ()
    expect_status: frozenset[int] = frozenset({200})
    validate: Callable[[int, bytes], str | None] | None = None
    skip_reason: str | None = None


def _mixed_proxy_url() -> str:
    port = os.environ.get("MIHOMO_MIXED_PORT", "7890")
    override = os.environ.get("MIHOMO_CHECK_PROXY")
    if override:
        return override
    return f"http://127.0.0.1:{port}"


def _hf_token() -> str | None:
    for key in ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN", "HUGGINGFACE_HUB_TOKEN"):
        val = os.environ.get(key, "").strip()
        if val:
            return val
    return None


def _validate_git_smart_http(_status: int, body: bytes) -> str | None:
    if b"service=git-upload-pack" in body or b"ref" in body.lower():
        return None
    if not body.strip():
        return "empty git smart HTTP response"
    return None


def _validate_hf_json(status: int, body: bytes) -> str | None:
    if status != 200:
        return f"HTTP {status}"
    try:
        json.loads(body.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as e:
        return f"invalid JSON: {e}"
    return None


def _validate_hf_whoami(_status: int, body: bytes) -> str | None:
    try:
        data = json.loads(body.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        return "invalid JSON from whoami"
    if not data.get("name") and not data.get("email"):
        return "whoami missing name/email"
    return None


def build_probes() -> list[Probe]:
    token = _hf_token()
    probes: list[Probe] = [
        Probe(
            id="google",
            label="Google",
            url="https://www.gstatic.com/generate_204",
            expect_status=frozenset({204}),
        ),
        Probe(
            id="google_www",
            label="Google (www)",
            url="https://www.google.com/",
            method="HEAD",
            expect_status=frozenset({200, 301, 302, 303, 307, 308}),
        ),
        Probe(
            id="github",
            label="GitHub",
            url="https://github.com/",
            method="HEAD",
            expect_status=frozenset({200, 301, 302, 303, 307, 308}),
        ),
        Probe(
            id="github_raw",
            label="GitHub raw",
            url="https://raw.githubusercontent.com/github/gitignore/main/README.md",
            expect_status=frozenset({200}),
        ),
        Probe(
            id="github_clone",
            label="GitHub clone (smart HTTP)",
            url="https://github.com/octocat/Hello-World.git/info/refs?service=git-upload-pack",
            headers=(("Accept", "*/*"),),
            expect_status=frozenset({200}),
            validate=_validate_git_smart_http,
        ),
        Probe(
            id="hf_site",
            label="Hugging Face",
            url="https://huggingface.co/",
            method="HEAD",
            expect_status=frozenset({200, 301, 302, 303, 307, 308}),
        ),
        Probe(
            id="hf_api",
            label="Hugging Face API",
            url="https://huggingface.co/api/models/gpt2",
            expect_status=frozenset({200}),
            validate=_validate_hf_json,
        ),
        Probe(
            id="hf_download",
            label="Hugging Face download",
            url="https://huggingface.co/hf-internal-testing/tiny-random-gpt2/resolve/main/config.json",
            headers=(("Range", "bytes=0-511"),),
            expect_status=frozenset({200, 206}),
        ),
    ]
    if token:
        probes.append(
            Probe(
                id="hf_auth",
                label="Hugging Face auth",
                url="https://huggingface.co/api/whoami-v2",
                headers=(("Authorization", f"Bearer {token}"),),
                expect_status=frozenset({200}),
                validate=_validate_hf_whoami,
            )
        )
    else:
        probes.append(
            Probe(
                id="hf_auth",
                label="Hugging Face auth",
                url="",
                skip_reason="set HF_TOKEN or HUGGING_FACE_HUB_TOKEN to test auth",
            )
        )
    return probes


@dataclass
class ProbeResult:
    id: str
    label: str
    ok: bool
    skipped: bool
    status: int | None
    latency_ms: int | None
    error: str | None
    url: str | None = None


def _run_one(
    probe: Probe,
    opener: urllib.request.OpenerDirector,
    timeout: float,
) -> ProbeResult:
    if probe.skip_reason:
        return ProbeResult(
            id=probe.id,
            label=probe.label,
            ok=True,
            skipped=True,
            status=None,
            latency_ms=None,
            error=probe.skip_reason,
            url=None,
        )

    req = urllib.request.Request(
        probe.url,
        method=probe.method,
        headers={"User-Agent": USER_AGENT, **dict(probe.headers)},
    )
    start = time.perf_counter()
    try:
        with opener.open(req, timeout=timeout) as resp:
            status = resp.status
            if probe.method == "HEAD" and probe.validate is None:
                body = b""
            else:
                body = resp.read(65536)
    except urllib.error.HTTPError as e:
        status = e.code
        if probe.method == "HEAD" and probe.validate is None:
            body = b""
        else:
            body = e.read(65536) if e.fp else b""
    except Exception as e:
        elapsed = int((time.perf_counter() - start) * 1000)
        return ProbeResult(
            id=probe.id,
            label=probe.label,
            ok=False,
            skipped=False,
            status=None,
            latency_ms=elapsed,
            error=str(e),
            url=probe.url,
        )

    elapsed = int((time.perf_counter() - start) * 1000)
    if status not in probe.expect_status:
        return ProbeResult(
            id=probe.id,
            label=probe.label,
            ok=False,
            skipped=False,
            status=status,
            latency_ms=elapsed,
            error=f"unexpected HTTP {status}",
            url=probe.url,
        )
    if probe.validate:
        msg = probe.validate(status, body)
        if msg:
            return ProbeResult(
                id=probe.id,
                label=probe.label,
                ok=False,
                skipped=False,
                status=status,
                latency_ms=elapsed,
                error=msg,
                url=probe.url,
            )

    return ProbeResult(
        id=probe.id,
        label=probe.label,
        ok=True,
        skipped=False,
        status=status,
        latency_ms=elapsed,
        error=None,
        url=probe.url,
    )


def run_checks(*, direct: bool = False, timeout: float | None = None) -> dict:
    timeout = timeout if timeout is not None else DEFAULT_TIMEOUT
    proxy_url = None if direct else _mixed_proxy_url()
    if proxy_url:
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})
        )
    else:
        opener = urllib.request.build_opener()

    probes = build_probes()
    t0 = time.perf_counter()
    results: list[ProbeResult] = []

    with ThreadPoolExecutor(max_workers=min(8, len(probes))) as pool:
        futures = {
            pool.submit(_run_one, p, opener, timeout): p for p in probes
        }
        for fut in as_completed(futures):
            results.append(fut.result())

    order = {p.id: i for i, p in enumerate(probes)}
    results.sort(key=lambda r: order.get(r.id, 999))

    ok = sum(1 for r in results if r.ok and not r.skipped)
    skipped = sum(1 for r in results if r.skipped)
    fail = sum(1 for r in results if not r.ok and not r.skipped)

    return {
        "direct": direct,
        "proxy": proxy_url,
        "timeout_s": timeout,
        "elapsed_ms": int((time.perf_counter() - t0) * 1000),
        "results": [asdict(r) for r in results],
        "summary": {"ok": ok, "fail": fail, "skipped": skipped, "total": len(results)},
    }


def format_text(report: dict) -> str:
    lines: list[str] = []
    via = "direct (no proxy)" if report["direct"] else report.get("proxy") or "direct"
    lines.append(f"Usage check via {via}  (timeout {report['timeout_s']}s per probe, parallel)")
    lines.append("")
    lines.append(f"{'STAT':<6} {'TIME':>7}  {'CHECK':<22} DETAIL")
    lines.append("-" * 72)
    for r in report["results"]:
        if r["skipped"]:
            stat = "SKIP"
            t = "   —"
            detail = r["error"] or ""
        elif r["ok"]:
            stat = "OK"
            t = f"{r['latency_ms']:>5}ms"
            detail = f"HTTP {r['status']}" if r["status"] else ""
        else:
            stat = "FAIL"
            t = f"{(r['latency_ms'] or 0):>5}ms" if r["latency_ms"] is not None else "   —"
            detail = r["error"] or f"HTTP {r['status']}"
        lines.append(f"{stat:<6} {t:>7}  {r['label']:<22} {detail}")
    s = report["summary"]
    lines.append("")
    lines.append(
        f"summary: {s['ok']} ok / {s['fail']} fail / {s['skipped']} skipped "
        f"({report['elapsed_ms']} ms wall)"
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Parallel usage connectivity checks via mihomo mixed port"
    )
    parser.add_argument(
        "--direct",
        action="store_true",
        help="Do not use local mihomo proxy (compare baseline)",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON report")
    parser.add_argument(
        "--timeout",
        type=float,
        default=None,
        help=f"Per-probe timeout seconds (default {DEFAULT_TIMEOUT})",
    )
    args = parser.parse_args(argv)

    report = run_checks(direct=args.direct, timeout=args.timeout)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(format_text(report))

    return 1 if report["summary"]["fail"] else 0


if __name__ == "__main__":
    sys.exit(main())
