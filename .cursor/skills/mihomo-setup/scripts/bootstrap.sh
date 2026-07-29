#!/usr/bin/env bash
# Bootstrap a workdir: mihomo binary + urls.txt → config/ + mihomo.sh
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKDIR="${1:-.}"
WORKDIR="$(cd "$WORKDIR" && pwd)"

URLS_FILE="${MIHOMO_URLS:-$WORKDIR/urls.txt}"
CONF_DIR="$WORKDIR/config"
TMPL="$SKILL_DIR/templates/config.yaml.tmpl"
CTRL_SRC="$SKILL_DIR/scripts/mihomo.sh"

die() { echo "error: $*" >&2; exit 1; }

[[ -f "$URLS_FILE" ]] || die "urls.txt not found at $URLS_FILE"
[[ -f "$TMPL" ]] || die "template missing: $TMPL"
[[ -f "$CTRL_SRC" ]] || die "control script missing: $CTRL_SRC"

find_bin() {
  if [[ -n "${MIHOMO_BIN:-}" ]]; then
    echo "$MIHOMO_BIN"
    return
  fi
  local f
  for f in "$WORKDIR"/mihomo*; do
    [[ -e "$f" ]] || continue
    [[ "$f" == *.sh ]] && continue
    [[ -f "$f" ]] || continue
    echo "$f"
    return
  done
  return 1
}

BIN="$(find_bin)" || die "no mihomo binary in $WORKDIR
Download from https://wiki.metacubex.one/en/startup/ then place it here (or set MIHOMO_BIN=...)"
chmod +x "$BIN"

mapfile -t URLS < <(grep -vE '^\s*(#|$)' "$URLS_FILE" || true)
[[ ${#URLS[@]} -gt 0 ]] || die "no URLs in $URLS_FILE"

mkdir -p "$CONF_DIR"

URLS_JSON="$(mktemp)"
trap 'rm -f "$URLS_JSON"' EXIT
python3 - "$URLS_JSON" "${URLS[@]}" <<'PY'
import json, sys
path = sys.argv[1]
urls = sys.argv[2:]
open(path, "w", encoding="utf-8").write(json.dumps(urls, ensure_ascii=False))
PY

export BOOTSTRAP_TMPL="$TMPL"
export BOOTSTRAP_OUT="$CONF_DIR/config.yaml"
export BOOTSTRAP_URLS_JSON="$URLS_JSON"

python3 - <<'PY'
import json, os, pathlib, sys

urls = json.loads(pathlib.Path(os.environ["BOOTSTRAP_URLS_JSON"]).read_text(encoding="utf-8"))
if not urls:
    sys.exit("error: empty url list")

providers_lines = ["proxy-providers:"]
use_lines = []
auto_blocks = []
select_autos = []

for i, url in enumerate(urls, 1):
    name = f"provider{i}"
    use_lines.append(f"      - {name}")
    select_autos.append(f"      - AUTO-{name}")
    providers_lines += [
        f"  {name}:",
        "    type: http",
        f'    url: "{url}"',
        f"    path: ./providers/{name}.yaml",
        "    interval: 86400",
        "    proxy: DIRECT",
        "    health-check:",
        "      enable: true",
        "      url: https://www.gstatic.com/generate_204",
        "      interval: 600",
        "    override:",
        f'      additional-prefix: "[{name}] "',
    ]
    auto_blocks += [
        f"  - name: AUTO-{name}",
        "    type: url-test",
        "    use:",
        f"      - {name}",
        "    url: https://www.gstatic.com/generate_204",
        "    interval: 300",
        "    tolerance: 50",
        "",
    ]

groups_lines = [
    "proxy-groups:",
    "  - name: PROXY",
    "    type: select",
    "    use:",
    *use_lines,
    "    proxies:",
    *select_autos,
    "      - AUTO",
    "      - DIRECT",
    "",
    "  - name: AUTO",
    "    type: url-test",
    "    use:",
    *use_lines,
    "    url: https://www.gstatic.com/generate_204",
    "    interval: 300",
    "    tolerance: 50",
    "",
    *auto_blocks,
]

tmpl = pathlib.Path(os.environ["BOOTSTRAP_TMPL"]).read_text(encoding="utf-8")
text = tmpl.replace("# {{PROXY_PROVIDERS}}", "\n".join(providers_lines) + "\n")
text = text.replace("# {{PROXY_GROUPS}}", "\n".join(groups_lines) + "\n")
out = pathlib.Path(os.environ["BOOTSTRAP_OUT"])
out.write_text(text, encoding="utf-8")
print(f"wrote {out}")
PY

cp "$CTRL_SRC" "$WORKDIR/mihomo.sh"
chmod +x "$WORKDIR/mihomo.sh"

echo "bootstrap ok"
echo "  workdir : $WORKDIR"
echo "  binary  : $BIN"
echo "  urls    : ${#URLS[@]} from $URLS_FILE"
echo "  config  : $CONF_DIR/config.yaml"
echo "  control : $WORKDIR/mihomo.sh"
echo
echo "Next:"
echo "  cd \"$WORKDIR\" && ./mihomo.sh test && ./mihomo.sh start && ./mihomo.sh bench"
