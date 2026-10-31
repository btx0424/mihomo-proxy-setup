"""FastAPI app — JSON API + single-page UI."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from mihomo_web import backend

STATIC = Path(__file__).resolve().parent / "static"

app = FastAPI(title="Mihomo Web UI", version="0.1.0")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


class SelectBody(BaseModel):
    group: str = "PROXY"
    node: str = Field(min_length=1)


class RefreshBody(BaseModel):
    providers: list[str] = Field(default_factory=list)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/meta")
def meta() -> dict:
    p = backend.paths()
    return {
        "mihomo_home": str(p.root),
        "api": p.api,
        "log_file": str(p.log_file),
        "bench_url": p.bench_url,
        "bench_timeout_ms": p.bench_timeout_ms,
    }


@app.get("/api/status")
def status() -> dict:
    return backend.run_script("status")


@app.post("/api/start")
def start() -> dict:
    return backend.run_script("start")


@app.post("/api/stop")
def stop() -> dict:
    return backend.run_script("stop")


@app.post("/api/restart")
def restart() -> dict:
    return backend.run_script("restart")


@app.post("/api/test")
def test_config() -> dict:
    return backend.run_script("test")


@app.get("/api/log")
def log_tail(lines: int = Query(default=80, ge=1, le=500)) -> dict:
    return {"text": backend.tail_log(lines)}


@app.get("/api/groups")
def groups() -> dict:
    try:
        return {"groups": backend.list_groups()}
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e


@app.get("/api/nodes")
def nodes(group: str = "PROXY") -> dict:
    try:
        return backend.list_nodes(group)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.get("/api/now")
def now(group: str = "PROXY") -> dict:
    try:
        return backend.current_selection(group)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e


@app.post("/api/bench")
def bench(group: str = "PROXY") -> dict:
    try:
        return backend.bench_group(group)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e


@app.post("/api/select")
def select(body: SelectBody) -> dict:
    try:
        return backend.select_node(body.group, body.node)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.get("/api/proxy-snippets")
def proxy_snippets() -> dict:
    return backend.proxy_snippets()


@app.post("/api/check")
def usage_check(
    direct: bool = False,
    timeout: float | None = Query(default=None, ge=1, le=120),
) -> dict:
    return backend.usage_check(direct=direct, timeout=timeout)


@app.get("/api/subscription")
def subscription_status() -> dict:
    try:
        return backend.subscription_status()
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e)) from e


@app.post("/api/subscription/refresh")
def subscription_refresh(body: RefreshBody | None = None) -> dict:
    try:
        names = body.providers if body and body.providers else None
        return backend.subscription_refresh(names)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e)) from e


@app.get("/api/binary")
def binary_status() -> dict:
    return backend.binary_status()


@app.post("/api/binary/update")
def binary_update(
    restart: bool = True,
    force: bool = False,
) -> dict:
    try:
        return backend.binary_update(restart=restart, force=force)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
