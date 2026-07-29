#!/usr/bin/env bash
# Install user-wide shell helpers: mihomo, proxy-on, proxy-off
# Idempotent: re-running updates the managed block in place.
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKDIR="${1:-.}"
WORKDIR="$(cd "$WORKDIR" && pwd)"

BEGIN_MARK="# >>> mihomo-setup >>>"
END_MARK="# <<< mihomo-setup <<<"

die() { echo "error: $*" >&2; exit 1; }

[[ -x "$WORKDIR/mihomo.sh" || -f "$WORKDIR/mihomo.sh" ]] || \
  die "mihomo.sh not found in $WORKDIR (run bootstrap.sh first)"

usage() {
  cat <<EOF
Usage: $(basename "$0") [workdir] [--bash|--zsh|--both] [--uninstall]

Installs shell functions into ~/.bashrc and/or ~/.zshrc:
  mihomo ...   → \$MIHOMO_HOME/mihomo.sh
  proxy-on     → export http(s)_proxy / all_proxy
  proxy-off    → unset proxy env vars

Default: install into both rc files if they exist (create if missing for your login shell).
EOF
}

DO_BASH=0
DO_ZSH=0
UNINSTALL=0
EXPLICIT=0

for arg in "${@:2}"; do
  case "$arg" in
    --bash) DO_BASH=1; EXPLICIT=1 ;;
    --zsh)  DO_ZSH=1; EXPLICIT=1 ;;
    --both) DO_BASH=1; DO_ZSH=1; EXPLICIT=1 ;;
    --uninstall) UNINSTALL=1 ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown option: $arg" ;;
  esac
done

if [[ "$EXPLICIT" -eq 0 ]]; then
  DO_BASH=1
  DO_ZSH=1
fi

BLOCK_CONTENT="$(cat <<EOF
$BEGIN_MARK
# Managed by mihomo-setup — do not edit inside this block; re-run install-shell.sh
export MIHOMO_HOME="$WORKDIR"
mihomo() { "\$MIHOMO_HOME/mihomo.sh" "\$@"; }
proxy-on() {
  export http_proxy=http://127.0.0.1:7890
  export https_proxy=http://127.0.0.1:7890
  export HTTP_PROXY=http://127.0.0.1:7890
  export HTTPS_PROXY=http://127.0.0.1:7890
  export all_proxy=socks5://127.0.0.1:7891
  export ALL_PROXY=socks5://127.0.0.1:7891
  export no_proxy=localhost,127.0.0.1,::1
  export NO_PROXY=localhost,127.0.0.1,::1
  echo "proxy on -> http://127.0.0.1:7890 (socks 7891)"
}
proxy-off() {
  unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY
  unset all_proxy ALL_PROXY no_proxy NO_PROXY
  echo "proxy off"
}
$END_MARK
EOF
)"

remove_block() {
  local file="$1"
  [[ -f "$file" ]] || return 0
  if ! grep -qF "$BEGIN_MARK" "$file" 2>/dev/null; then
    return 0
  fi
  local tmp
  tmp="$(mktemp)"
  awk -v b="$BEGIN_MARK" -v e="$END_MARK" '
    $0 == b {skip=1; next}
    $0 == e {skip=0; next}
    !skip {print}
  ' "$file" >"$tmp"
  # trim trailing blank lines left by removal, keep one newline at EOF
  python3 - "$tmp" "$file" <<'PY'
import pathlib, sys
src, dst = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
text = src.read_text(encoding="utf-8")
text = text.rstrip() + ("\n" if text.strip() else "")
dst.write_text(text, encoding="utf-8")
src.unlink()
PY
  echo "removed mihomo-setup block from $file"
}

install_block() {
  local file="$1"
  mkdir -p "$(dirname "$file")"
  touch "$file"
  remove_block "$file"
  # ensure separating newline
  if [[ -s "$file" ]] && [[ "$(tail -c1 "$file" | wc -l)" -eq 0 ]]; then
    echo >>"$file"
  elif [[ -s "$file" ]]; then
    echo >>"$file"
  fi
  printf '%s\n' "$BLOCK_CONTENT" >>"$file"
  echo "installed mihomo-setup block into $file"
}

if [[ "$UNINSTALL" -eq 1 ]]; then
  [[ "$DO_BASH" -eq 1 ]] && remove_block "$HOME/.bashrc"
  [[ "$DO_ZSH" -eq 1 ]] && remove_block "$HOME/.zshrc"
  echo "done (uninstall). Open a new shell or: source ~/.bashrc  /  source ~/.zshrc"
  exit 0
fi

[[ "$DO_BASH" -eq 1 ]] && install_block "$HOME/.bashrc"
[[ "$DO_ZSH" -eq 1 ]] && install_block "$HOME/.zshrc"

cat <<EOF

Shell helpers installed. Reload with:
  source ~/.zshrc    # or: source ~/.bashrc

Then:
  mihomo start
  mihomo bench
  proxy-on
  curl -I https://www.google.com
  proxy-off

MIHOMO_HOME=$WORKDIR
EOF
