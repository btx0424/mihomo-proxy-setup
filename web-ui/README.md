# Mihomo web UI (optional)

Local-only dashboard for the same commands as `./mihomo.sh` — start/stop, groups, nodes, bench, select, log tail, and copy-paste `proxy-on` / `proxy-off` snippets.

## Run

From the repo root (with `MIHOMO_HOME` set by shell helpers, or inferred automatically):

```bash
cd web-ui
uv sync
uv run mihomo-web
```

Or via the control script (after `uv sync` once):

```bash
mihomo web
```

Open **http://127.0.0.1:8765** in a browser on the same machine.

## Environment

Uses the same variables as `mihomo.sh`: `MIHOMO_HOME`, `MIHOMO_API`, `MIHOMO_CONF`, `MIHOMO_LOG`, `MIHOMO_BENCH_URL`, `MIHOMO_BENCH_TIMEOUT`.

Optional UI-only:

| Variable | Default |
|----------|---------|
| `MIHOMO_WEB_HOST` | `127.0.0.1` |
| `MIHOMO_WEB_PORT` | `8765` |

The server binds to localhost only by default.

## Usage checks

Same as `mihomo check` — runs probes in parallel through the local mixed port (`127.0.0.1:7890` by default):

- Google (`generate_204` + www)
- GitHub (site, raw file, git smart HTTP / clone path)
- Hugging Face (site, API, small download; auth if `HF_TOKEN` or `HUGGING_FACE_HUB_TOKEN` is set)

Optional env: `MIHOMO_CHECK_PROXY`, `MIHOMO_CHECK_TIMEOUT` (seconds, default 15).

## Subscription refresh

**Subscription** panel shows **since refresh** per provider (from mihomo `updatedAt`). **Refresh all** / per-row **Refresh** maps to `mihomo refresh`. To change subscription URLs, edit `urls.txt` and re-run bootstrap — not the refresh button.

**Update mihomo** (Daemon section) downloads the matching GitHub release asset for your OS/arch, replaces the binary, and restarts the daemon by default. Downloads use `127.0.0.1:7890` as HTTP proxy unless `MIHOMO_UPDATE_PROXY=...` or `MIHOMO_USE_LOCAL_PROXY=0`.
