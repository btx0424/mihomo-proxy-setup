# Mihomo quick setup

Turn a **Mihomo binary** + **subscription URLs** into a working local proxy, with simple shell commands (`mihomo`, `proxy-on`, `proxy-off`).

## What you need

| Item | Description |
|------|-------------|
| Mihomo binary | Download for your OS/arch from the official install page — **not** stored in git |
| `urls.txt` | One subscription URL per line (`#` comments OK) — **local only, gitignored** |

### Download the binary

1. Open **[mihomo install / precompiled binaries](https://wiki.metacubex.one/en/startup/)**.
2. Pick **Release (Stable)** → your OS (e.g. Linux) → arch (e.g. `amd64`). Prefer the compressed binary (`.gz`); use `compatible` / older-CPU builds if needed.
3. Unpack into this repo directory and make it executable:

```bash
# example after downloading the .gz for linux-amd64
gunzip -k mihomo-linux-amd64-*.gz   # or: gzip -dk ...
chmod +x mihomo-linux-amd64-*
```

The filename can stay as downloaded (e.g. `mihomo-linux-amd64-compatible`); `setup.sh` / `bootstrap.sh` auto-detect any `mihomo*` binary in the workdir.

Clone this repo (with docs submodule):

```bash
git clone --recurse-submodules <this-repo-url>
# if you already cloned without submodules:
git submodule update --init --recursive
```

`Meta-Docs/` is the official [MetaCubeX/Meta-Docs](https://github.com/MetaCubeX/Meta-Docs) reference, pinned as a submodule.

This repo already includes bootstrap / control scripts under `.cursor/skills/mihomo-setup/`.

## Fast path (recommended)

On a new machine:

1. Clone this repo (`--recurse-submodules`).
2. [Download the binary](https://wiki.metacubex.one/en/startup/) into the repo directory and `chmod +x` it.
3. Create `urls.txt` with your subscription URL(s).
4. Run setup:

```bash
chmod +x setup.sh
./setup.sh
```

That will:

1. Generate `config/config.yaml` from `urls.txt`
2. Install `mihomo.sh` in this directory
3. Add helpers to `~/.bashrc` and `~/.zshrc`

Then:

```bash
source ~/.zshrc          # or: source ~/.bashrc

mihomo test
mihomo start
mihomo bench             # find live nodes (important!)
mihomo select PROXY 'AUTO'

proxy-on
curl -I --max-time 20 https://www.google.com
```

Default ports: **7890** (HTTP/SOCKS mixed), **7891** (SOCKS), **9090** (API).

---

## Step-by-step (manual)

### 1. Prepare files

Download a binary from [https://wiki.metacubex.one/en/startup/](https://wiki.metacubex.one/en/startup/), then:

```text
workdir/
├── mihomo*          # downloaded binary (gitignored)
├── urls.txt         # subscription URLs (gitignored)
└── .cursor/skills/mihomo-setup/   # from this project
```

Example `urls.txt`:

```text
https://example.com/clash-sub
https://example.com/link/xxxx?sub=3
```

### 2. Bootstrap config

```bash
bash .cursor/skills/mihomo-setup/scripts/bootstrap.sh .
```

Creates `config/config.yaml` and copies `mihomo.sh`.

### 3. Install shell one-liners

```bash
bash .cursor/skills/mihomo-setup/scripts/install-shell.sh . --both
source ~/.zshrc
```

Options:

```bash
# only zsh / only bash
bash .cursor/skills/mihomo-setup/scripts/install-shell.sh . --zsh
bash .cursor/skills/mihomo-setup/scripts/install-shell.sh . --bash

# remove the helpers later
bash .cursor/skills/mihomo-setup/scripts/install-shell.sh . --uninstall
```

### 4. Start and choose a node

```bash
mihomo start
mihomo status
mihomo bench
mihomo select PROXY 'AUTO'          # auto url-test across providers
# or pin a specific node (quote the exact name from bench):
mihomo select PROXY '[provider2] 香港S03 | IEPL'
mihomo now
```

**Do not skip `bench`.** A dead upstream looks like curl `SSL ... unexpected eof` even when the local proxy is fine.

### 5. Use the proxy in a terminal

```bash
proxy-on
curl -I https://www.google.com
# … your commands …
proxy-off
```

Browsers usually ignore shell env vars — use a system proxy setting or browser extension if needed.

---

## Shell commands cheat sheet

| Command | What it does |
|---------|----------------|
| `mihomo start` / `stop` / `restart` / `status` | Daemon lifecycle |
| `mihomo test` | Validate `config/config.yaml` |
| `mihomo bench [GROUP]` | Latency-test nodes (default group: `PROXY`) |
| `mihomo nodes [GROUP]` | List members (`*` = current) |
| `mihomo select GROUP NODE` | Switch selection |
| `mihomo now` | Show current selection chain |
| `mihomo log` | Tail `config/mihomo.log` |
| `proxy-on` | Export `http_proxy` / `https_proxy` / `all_proxy` |
| `proxy-off` | Unset proxy env vars |

Without shell helpers, call the script directly:

```bash
./mihomo.sh start
```

---

## Layout after setup

```text
.
├── setup.sh                 # one-shot installer
├── mihomo*                  # download from wiki; gitignored
├── urls.txt                 # subscriptions (you provide; gitignored)
├── mihomo.sh                # control script (generated; gitignored)
├── README.md
├── .gitmodules
├── Meta-Docs/               # official docs submodule (reference)
├── config/                  # runtime; gitignored
└── .cursor/skills/mihomo-setup/
    ├── SKILL.md
    └── scripts/
        ├── bootstrap.sh
        ├── install-shell.sh
        └── mihomo.sh
```

Update docs later with:

```bash
git submodule update --remote Meta-Docs
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `Connection refused` on `:7890` | Not running | `mihomo start` |
| `SSL ... unexpected eof` via proxy | Dead upstream node | `mihomo bench` then `select` |
| Empty providers / fetch errors | Bad/blocked URL | `curl -A clash.meta '<url>'` |
| DNS bind errors | Port in use | Edit `config.yaml` / ignore if proxy still works |
| `mihomo: command not found` | RC not sourced | `source ~/.zshrc` or re-run `install-shell.sh` |

---

## Security notes

- Keep `urls.txt` private (subscription tokens).
- Helpers set `MIHOMO_HOME` to this directory — re-run `install-shell.sh` if you move the install.
- This setup uses **mixed-port only** (no TUN). Apps must opt in via env vars or their own proxy settings.
