# Mihomo setup reference

## urls.txt format

```text
# one URL per line
https://example.com/sub?token=...
https://other.example/link/xxxx?sub=3
```

Supported subscription body types (mihomo `proxy-providers` http):

| Kind | Typical content | Notes |
|------|-----------------|-------|
| Clash YAML | `proxies:` list (or full config) | Prefer converter with `list=true` / `target=clash` so the body is provider-friendly |
| Base64 share links | `vmess://` / `ss://` / `vless://` lines | Mihomo parses these as a provider |

Probe with curl (`-A clash.meta`) if unsure; both can work as provider `url:` values.

## Generated config shape

For N URLs → providers `provider1` … `providerN`:

- Each provider: `type: http`, `proxy: DIRECT`, health-check enabled, `additional-prefix: "[providerK] "`
- Groups:
  - `AUTO` — `url-test` over all providers
  - `PROXY` — `select` with `AUTO`, `DIRECT`, and `use:` all providers (so individual nodes appear)
- Rules: private CIDRs → `DIRECT`; `MATCH,PROXY`
- `profile.store-selected: true`
- DNS: fake-ip; **do not** bind DNS listen on a busy port (omit `dns.listen` unless free)

## Why not drop full subscription YAML as config?

Converted “online” Clash configs often include thousands of `GEOIP`/`GEOSITE` rules and need MMDB/geosite downloads (frequently blocked/slow). Provider mode avoids that and stays portable.

## Diagnosing failures

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `curl: (7) Connection refused` on 7890 | Mihomo not running | `./mihomo.sh start` |
| `SSL ... unexpected eof` via proxy | Dead/selected upstream | `./mihomo.sh bench` then `select` |
| Provider empty / fetch fail | URL blocked or needs auth | curl URL directly; fix `urls.txt` |
| DNS bind error on 1053 | Port in use | Remove `dns.listen` or change port |
| Config test wants MMDB | GEOIP rules in config | Switch to minimal provider config |

## API (controller)

Default `external-controller: 127.0.0.1:9090`

- `GET /proxies` — groups and nodes
- `GET /group/{name}/delay?url=...&timeout=5000` — latency test
- `PUT /proxies/{group}` body `{"name":"<node>"}` — select

`mihomo.sh` wraps these; prefer the script over raw curl.

## Ports

| Port | Role |
|------|------|
| 7890 | Mixed HTTP + SOCKS |
| 7891 | SOCKS |
| 9090 | External controller API |
