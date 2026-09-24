# Configuration

faro reads one TOML file: `/etc/faro/faro.toml` by default, or `$FARO_CONFIG`, or
`faro -c path`. A running faro watches the file and restarts itself when it
changes, **if the new version is valid**. If it isn't, it logs the error and keeps
running with the old one. You can check a file before saving it with:

```sh
faro check            # syntax and references
faro check --hosts    # ...and reach every agent
```

## Secrets

Any string value can be a reference instead of the secret itself:

| Value | Read from |
|---|---|
| `"env:FARO_NTFY_TOKEN"` | the environment variable (e.g. `Environment=` in a systemd drop-in) |
| `"file:/etc/faro/pve-token"` | a file, without its trailing newline |

## Sections

### `[server]`

| Key | Default | |
|---|---|---|
| `bind` | `"0.0.0.0"` | address to listen on |
| `port` | `8080` | |
| `data_dir` | `"/var/lib/faro"` | history, alert log, sessions, the SSH key |
| `public_url` | `""` | used for links in notifications |
| `trusted_proxies` | `["127.0.0.1/32", "::1/128"]` | proxies allowed to set `X-Forwarded-For` / `-Proto` |
| `plugin_dir` | `"/etc/faro/plugins"` | where your own plugins live |

### `[auth]`

| Key | Default | |
|---|---|---|
| `mode` | `"password"` | or `"none"` when a proxy (Authelia, Authentik, Tailscale…) already protects faro |
| `password_hash` | `""` | set it with `faro set-password` |
| `session_days` | `30` | |

### `[[hosts]]`

| Key | Default | |
|---|---|---|
| `id` | from `name` | used by services and disks to refer to the host |
| `name` | `id` | |
| `address` | required for ssh | |
| `transport` | `"ssh"` | `"local"` runs the agent directly: for the machine faro runs on |
| `user` / `port` | `"root"` / `22` | SMART and Proxmox details need root |
| `nic` | default route's | interface to chart |
| `description` | `""` | |
| `api_token` | | Proxmox API token for the power buttons ([proxmox.md](proxmox.md)) |
| `api_url` | `https://<address>:8006` | |

### `[[services]]`

| Key | Default | |
|---|---|---|
| `name` | required | |
| `id` | from `name` | |
| `url` | `""` | what the icon opens |
| `check` | `"http"` if there is a url, else `"none"` | `http`, `tcp`, `dns` or `none` |
| `target` | the url | what to check: `"http://10.0.0.5:8096/health"`, `"10.0.0.5:22"` (tcp), `"10.0.0.53"` (dns) |
| `icon` | first letter | a built-in name (`play`, `nube`, `llave`, `escudo`, `grafica`, `casa`, `servidor`…) or an image URL |
| `color` | derived from the name | `"#aa5cc3"` |
| `host`, `guest` | | link the service to a Proxmox guest: its CPU, RAM and disk show in the list |
| `description`, `group` | `""` | |

An HTTP check counts any answer below 500 as up, including a redirect to a login
page. `dns` sends a real query and expects `NOERROR`, so it proves the resolver
works, not just that port 53 is open.

### `[checks]`

`interval` (10 s), `timeout` (4 s), `verify_tls` (false: homelabs are full of
self-signed certificates), `ca_file` (verify against your own CA instead).

### `[alerts]`

| Key | Default | |
|---|---|---|
| `service_down_after` | `30` | seconds down before alerting |
| `host_offline_after` | `90` | seconds without agent data |
| `disk_temp_hdd` / `_ssd` / `_nvme` | `60` / `70` / `80` | °C for 5 minutes |
| `disk_full_percent` | `90` | any filesystem |

SMART failures, reallocated/pending sectors and ZFS pools that are not `ONLINE` always alert.

### `[notify.ntfy]` and `[notify.webhook]`

```toml
[notify.ntfy]
url = "https://ntfy.sh"         # or your own ntfy
topic = "homelab-8f3k2"
token = "env:FARO_NTFY_TOKEN"   # optional

[notify.webhook]
url = "file:/etc/faro/discord-webhook"
format = "discord"              # json, discord or slack
```

Test them with `faro test-notify` or from Settings in the UI.

### `[[disks]]`, `[guests]`, `[backup_max_age]`

Names and roles for disks (matched by serial number), descriptions for Proxmox
guests without a service (`"pve1:106" = "Kubernetes lab"`), and how many hours a
backup may age per backup storage before it shows as late.

### `[plugins.<name>]`

See [plugins.md](plugins.md).
