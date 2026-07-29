#!/usr/bin/env bash
# One-shot setup: bootstrap config from urls.txt, then install shell helpers.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_SCRIPTS="$ROOT/.cursor/skills/mihomo-setup/scripts"

die() { echo "error: $*" >&2; exit 1; }

[[ -d "$SKILL_SCRIPTS" ]] || die "skill scripts missing at $SKILL_SCRIPTS"
[[ -f "$ROOT/urls.txt" ]] || die "create $ROOT/urls.txt (one subscription URL per line) first"

if [[ -z "${MIHOMO_BIN:-}" ]] && \
   [[ -z "$(find "$ROOT" -maxdepth 1 -type f -name 'mihomo*' ! -name '*.sh' 2>/dev/null | head -1)" ]]; then
  die "no mihomo binary in $ROOT
Download from https://wiki.metacubex.one/en/startup/ and place it in this directory"
fi

echo "==> Bootstrap (config + mihomo.sh)"
bash "$SKILL_SCRIPTS/bootstrap.sh" "$ROOT"

echo
echo "==> Install shell helpers (~/.bashrc / ~/.zshrc)"
bash "$SKILL_SCRIPTS/install-shell.sh" "$ROOT" --both

cat <<EOF

==> Almost done

1. Reload your shell:
     source ~/.zshrc    # zsh
     # or: source ~/.bashrc

2. Start mihomo and pick a working node:
     mihomo test
     mihomo start
     mihomo bench
     mihomo select PROXY 'AUTO'

3. Enable proxy for this terminal, then test:
     proxy-on
     curl -I --max-time 20 https://www.google.com

See README.md for the full guide.
EOF
