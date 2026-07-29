#!/usr/bin/env bash
# Convenient control script for local mihomo
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

resolve_bin() {
  if [[ -n "${MIHOMO_BIN:-}" ]]; then
    echo "$MIHOMO_BIN"
    return
  fi
  local f
  for f in "$ROOT"/mihomo*; do
    [[ -e "$f" ]] || continue
    [[ "$f" == *.sh ]] && continue
    [[ -f "$f" && -x "$f" ]] || continue
    echo "$f"
    return
  done
  # Non-executable fallback (caller will chmod / error later)
  for f in "$ROOT"/mihomo*; do
    [[ -e "$f" ]] || continue
    [[ "$f" == *.sh ]] && continue
    [[ -f "$f" ]] || continue
    echo "$f"
    return
  done
  echo "$ROOT/mihomo"
}

BIN="$(resolve_bin)"
CONF_DIR="${MIHOMO_CONF:-$ROOT/config}"
PID_FILE="${MIHOMO_PID:-$CONF_DIR/mihomo.pid}"
LOG_FILE="${MIHOMO_LOG:-$CONF_DIR/mihomo.log}"
MIXED_PORT="${MIHOMO_MIXED_PORT:-7890}"
API="${MIHOMO_API:-http://127.0.0.1:9090}"
BENCH_URL="${MIHOMO_BENCH_URL:-https://www.gstatic.com/generate_204}"
BENCH_TIMEOUT_MS="${MIHOMO_BENCH_TIMEOUT:-5000}"

usage() {
  cat <<EOF
Usage: $(basename "$0") <command> [args]

Commands:
  start              Start mihomo in the background
  stop               Stop the running instance
  restart            Restart mihomo
  status             Show process / port / API status
  test               Validate config (-t)
  log                Tail the log file (Ctrl-C to quit)
  run                Run in foreground (logs to terminal)

  groups             List selectable proxy groups
  nodes [GROUP]      List members of a group (default: PROXY)
  bench [GROUP]      Latency-test nodes in a group and print a table
  select GROUP NODE  Switch GROUP to NODE (use exact name from \`nodes\`)
  now [GROUP]        Show current selection (default: PROXY)

Examples:
  $(basename "$0") bench
  $(basename "$0") bench AUTO
  $(basename "$0") nodes PROXY
  $(basename "$0") select PROXY 'AUTO'
  $(basename "$0") select PROXY '[provider1] node-name'

Env overrides:
  MIHOMO_BIN            Binary path   (default: first mihomo* in $ROOT)
  MIHOMO_CONF           Config dir    (default: $ROOT/config)
  MIHOMO_PID            PID file      (default: \$MIHOMO_CONF/mihomo.pid)
  MIHOMO_LOG            Log file      (default: \$MIHOMO_CONF/mihomo.log)
  MIHOMO_API            Controller    (default: http://127.0.0.1:9090)
  MIHOMO_BENCH_URL      Probe URL     (default: https://www.gstatic.com/generate_204)
  MIHOMO_BENCH_TIMEOUT  Timeout ms    (default: 5000)
EOF
}

ensure_api() {
  if ! curl -fsS -o /dev/null --max-time 2 "$API" 2>/dev/null; then
    echo "error: mihomo API not reachable at $API (is it running? try: $(basename "$0") start)" >&2
    exit 1
  fi
}

ensure_bin() {
  if [[ ! -x "$BIN" ]]; then
    echo "error: binary not found or not executable: $BIN" >&2
    exit 1
  fi
  if [[ ! -f "$CONF_DIR/config.yaml" ]]; then
    echo "error: config not found: $CONF_DIR/config.yaml" >&2
    exit 1
  fi
}

is_running() {
  if [[ -f "$PID_FILE" ]]; then
    local pid
    pid="$(cat "$PID_FILE" 2>/dev/null || true)"
    if [[ -n "${pid:-}" ]] && kill -0 "$pid" 2>/dev/null; then
      # Confirm it is actually our binary
      if [[ -r "/proc/$pid/cmdline" ]] && tr '\0' ' ' <"/proc/$pid/cmdline" | grep -q mihomo; then
        return 0
      fi
    fi
  fi
  # Fallback: look for process using our config dir
  pgrep -f "$BIN -d $CONF_DIR" >/dev/null 2>&1
}

pid_of() {
  if [[ -f "$PID_FILE" ]]; then
    local pid
    pid="$(cat "$PID_FILE" 2>/dev/null || true)"
    if [[ -n "${pid:-}" ]] && kill -0 "$pid" 2>/dev/null; then
      echo "$pid"
      return 0
    fi
  fi
  pgrep -f "$BIN -d $CONF_DIR" | head -n1
}

cmd_test() {
  ensure_bin
  "$BIN" -t -d "$CONF_DIR"
}

cmd_start() {
  ensure_bin
  if is_running; then
    echo "mihomo already running (pid $(pid_of))"
    return 0
  fi

  mkdir -p "$CONF_DIR"
  # Clear stale pid
  rm -f "$PID_FILE"

  nohup "$BIN" -d "$CONF_DIR" >>"$LOG_FILE" 2>&1 &
  local pid=$!
  echo "$pid" >"$PID_FILE"

  # Wait briefly for listen
  local i
  for i in $(seq 1 20); do
    if ! kill -0 "$pid" 2>/dev/null; then
      echo "error: mihomo exited early; see $LOG_FILE" >&2
      rm -f "$PID_FILE"
      exit 1
    fi
    if ss -ltn 2>/dev/null | grep -q ":$MIXED_PORT " || \
       curl -fsS -o /dev/null --max-time 1 "$API" 2>/dev/null; then
      break
    fi
    sleep 0.25
  done

  echo "mihomo started (pid $pid)"
  echo "  mixed proxy : 127.0.0.1:$MIXED_PORT"
  echo "  API         : $API"
  echo "  log         : $LOG_FILE"
}

cmd_stop() {
  local pid
  pid="$(pid_of || true)"
  if [[ -z "${pid:-}" ]]; then
    echo "mihomo is not running"
    rm -f "$PID_FILE"
    return 0
  fi

  echo "stopping mihomo (pid $pid)..."
  kill "$pid" 2>/dev/null || true

  local i
  for i in $(seq 1 40); do
    if ! kill -0 "$pid" 2>/dev/null; then
      rm -f "$PID_FILE"
      echo "mihomo stopped"
      return 0
    fi
    sleep 0.25
  done

  echo "warning: graceful stop timed out, sending SIGKILL" >&2
  kill -9 "$pid" 2>/dev/null || true
  rm -f "$PID_FILE"
  echo "mihomo killed"
}

cmd_restart() {
  cmd_stop
  cmd_start
}

cmd_status() {
  if is_running; then
    echo "status : running (pid $(pid_of))"
  else
    echo "status : stopped"
  fi
  echo "binary : $BIN"
  echo "config : $CONF_DIR/config.yaml"
  echo "log    : $LOG_FILE"

  if command -v ss >/dev/null 2>&1; then
    echo "ports  :"
    ss -ltnp 2>/dev/null | grep -E ":(7890|7891|9090|1053) " || echo "  (none of 7890/7891/9090/1053 listening)"
  fi

  if curl -fsS -o /dev/null --max-time 2 "$API" 2>/dev/null; then
    echo "API    : up ($API)"
  else
    echo "API    : down"
  fi
}

cmd_log() {
  mkdir -p "$CONF_DIR"
  touch "$LOG_FILE"
  echo "tailing $LOG_FILE (Ctrl-C to quit)"
  tail -n 50 -F "$LOG_FILE"
}

cmd_run() {
  ensure_bin
  if is_running; then
    echo "error: already running in background (pid $(pid_of)); stop it first" >&2
    exit 1
  fi
  exec "$BIN" -d "$CONF_DIR"
}

cmd_groups() {
  ensure_api
  API="$API" python3 - <<'PY'
import json, os, urllib.request
api = os.environ["API"]
data = json.load(urllib.request.urlopen(f"{api}/proxies", timeout=10))
print(f"{'GROUP':<20} {'TYPE':<12} CURRENT")
print("-" * 72)
for name, p in sorted(data.get("proxies", {}).items()):
    if p.get("type") not in ("Selector", "URLTest", "Fallback", "LoadBalance"):
        continue
    print(f"{name:<20} {p.get('type',''):<12} {p.get('now','')}")
PY
}

cmd_nodes() {
  ensure_api
  local group="${1:-PROXY}"
  GROUP="$group" API="$API" python3 - <<'PY'
import json, os, urllib.parse, urllib.request
api, group = os.environ["API"], os.environ["GROUP"]
url = f"{api}/proxies/{urllib.parse.quote(group, safe='')}"
try:
    p = json.load(urllib.request.urlopen(url, timeout=10))
except Exception as e:
    raise SystemExit(f"error: cannot read group {group!r}: {e}")
members = p.get("all") or []
now = p.get("now", "")
print(f"group : {group}  ({p.get('type')})")
print(f"now   : {now}")
print(f"count : {len(members)}")
print("-" * 72)
for i, name in enumerate(members, 1):
    mark = "*" if name == now else " "
    print(f"{mark} {i:>3}  {name}")
PY
}

cmd_now() {
  ensure_api
  local group="${1:-PROXY}"
  GROUP="$group" API="$API" python3 - <<'PY'
import json, os, urllib.parse, urllib.request
api, group = os.environ["API"], os.environ["GROUP"]
url = f"{api}/proxies/{urllib.parse.quote(group, safe='')}"
p = json.load(urllib.request.urlopen(url, timeout=10))
print(f"{group} -> {p.get('now')}")
# If current is another group, show its leaf selection too
now = p.get("now")
if now and now in (json.load(urllib.request.urlopen(f"{api}/proxies", timeout=10)).get("proxies") or {}):
    leaf = json.load(urllib.request.urlopen(f"{api}/proxies/{urllib.parse.quote(now, safe='')}", timeout=10))
    if leaf.get("type") in ("Selector", "URLTest", "Fallback", "LoadBalance") and leaf.get("now"):
        print(f"{now} -> {leaf.get('now')}")
PY
}

cmd_bench() {
  ensure_api
  local group="${1:-PROXY}"
  echo "Latency testing group '$group' (timeout ${BENCH_TIMEOUT_MS}ms, url $BENCH_URL)..."
  echo "This may take a while."
  GROUP="$group" API="$API" BENCH_URL="$BENCH_URL" BENCH_TIMEOUT_MS="$BENCH_TIMEOUT_MS" python3 - <<'PY'
import json, os, urllib.parse, urllib.request

api = os.environ["API"]
group = os.environ["GROUP"]
bench_url = os.environ["BENCH_URL"]
timeout_ms = os.environ["BENCH_TIMEOUT_MS"]

# current selection
gurl = f"{api}/proxies/{urllib.parse.quote(group, safe='')}"
try:
    g = json.load(urllib.request.urlopen(gurl, timeout=10))
except Exception as e:
    raise SystemExit(f"error: cannot read group {group!r}: {e}")
now = g.get("now", "")

delay_url = (
    f"{api}/group/{urllib.parse.quote(group, safe='')}/delay"
    f"?url={urllib.parse.quote(bench_url, safe='')}&timeout={timeout_ms}"
)
# group delay can be slow
try:
    delays = json.load(urllib.request.urlopen(delay_url, timeout=max(60, int(timeout_ms) / 1000 * 120)))
except Exception as e:
    raise SystemExit(f"error: delay test failed: {e}")

rows = []
for name, val in delays.items():
    if isinstance(val, dict):
        # newer API may return {"delay": N, ...} or error object
        d = val.get("delay") or 0
        msg = val.get("message") or ""
    elif isinstance(val, int):
        d, msg = val, ""
    else:
        d, msg = 0, str(val)
    rows.append((d if d and d > 0 else 0, name, msg))

ok = sorted([r for r in rows if r[0] > 0], key=lambda x: x[0])
bad = sorted([r for r in rows if r[0] <= 0], key=lambda x: x[1])

print()
print(f"{'RANK':<6} {'DELAY':>8}  NODE")
print("-" * 72)
for i, (delay, name, _) in enumerate(ok, 1):
    mark = " *" if name == now else "  "
    print(f"{i:<6} {delay:>6} ms{mark} {name}")

if bad:
    print()
    print(f"FAILED / TIMEOUT ({len(bad)}):")
    print("-" * 72)
    for _, name, msg in bad:
        mark = " *" if name == now else "  "
        extra = f"  ({msg})" if msg else ""
        print(f"  ----{mark} {name}{extra}")

print()
print(f"summary: {len(ok)} ok / {len(bad)} fail / {len(rows)} total   current: {now or '(none)'}")
if ok:
    print(f"fastest: {ok[0][1]}  ({ok[0][0]} ms)")
    print(f"tip    : select with:  ./mihomo.sh select {group} '{ok[0][1]}'")
PY
}

cmd_select() {
  ensure_api
  if [[ $# -lt 2 ]]; then
    echo "usage: $(basename "$0") select GROUP NODE" >&2
    echo "example: $(basename "$0") select PROXY 'AUTO-ikuuu'" >&2
    exit 1
  fi
  local group="$1"
  shift
  local node="$*"
  GROUP="$group" NODE="$node" API="$API" python3 - <<'PY'
import json, os, urllib.parse, urllib.request

api, group, node = os.environ["API"], os.environ["GROUP"], os.environ["NODE"]
# validate group/node exist
proxies = json.load(urllib.request.urlopen(f"{api}/proxies", timeout=10)).get("proxies", {})
if group not in proxies:
    raise SystemExit(f"error: unknown group {group!r}")
members = proxies[group].get("all") or []
if node not in members:
    # helpful suggestions
    hints = [m for m in members if node.lower() in m.lower()][:8]
    msg = f"error: {node!r} is not a member of {group!r}"
    if hints:
        msg += "\nDid you mean:\n  " + "\n  ".join(hints)
    raise SystemExit(msg)

req = urllib.request.Request(
    f"{api}/proxies/{urllib.parse.quote(group, safe='')}",
    data=json.dumps({"name": node}).encode(),
    headers={"Content-Type": "application/json"},
    method="PUT",
)
try:
    urllib.request.urlopen(req, timeout=10).read()
except Exception as e:
    raise SystemExit(f"error: select failed: {e}")

# confirm
cur = json.load(urllib.request.urlopen(
    f"{api}/proxies/{urllib.parse.quote(group, safe='')}", timeout=10
)).get("now")
print(f"selected: {group} -> {cur}")
PY
}

main() {
  local cmd="${1:-}"
  case "$cmd" in
    start)   cmd_start ;;
    stop)    cmd_stop ;;
    restart) cmd_restart ;;
    status)  cmd_status ;;
    test)    cmd_test ;;
    log)     cmd_log ;;
    run)     cmd_run ;;
    groups)  cmd_groups ;;
    nodes)   shift; cmd_nodes "$@" ;;
    now)     shift; cmd_now "$@" ;;
    bench)   shift; cmd_bench "$@" ;;
    select)  shift; cmd_select "$@" ;;
    -h|--help|help|"") usage ;;
    *)
      echo "unknown command: $cmd" >&2
      usage >&2
      exit 1
      ;;
  esac
}

main "$@"
