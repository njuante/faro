# Plugins

A plugin is a Python file with a `Plugin` class. It's enabled by giving it a table
in `faro.toml`:

```toml
[plugins.proxmox]            # built-in (faro/plugins/proxmox.py)

[plugins.speedtest]          # yours: /etc/faro/plugins/speedtest.py
url = "http://10.0.0.8:8765"
```

Built-in plugins are looked up in `faro/plugins/`, your own in `server.plugin_dir`
(default `/etc/faro/plugins`). Private integrations can stay on your server and
never have to be in a public repository.

## Built-in plugins

| Plugin | What it adds | Docs |
|---|---|---|
| `proxmox` | Start, shut down and reboot guests | [proxmox.md](proxmox.md) |
| `ai` | Ask about the homelab; a local model answers | [assistant.md](assistant.md) |
| `media` | Now playing and recently added: Jellyfin, Plex, Navidrome | below |
| `speedtest` | Speed between the device in your hand and the server | below |
| `automations` | Restart what stops answering, shut down idle VMs, a daily report | below |

### media

```toml
[plugins.media]
jellyfin = { url = "http://192.168.1.21:8096", token = "env:FARO_JELLYFIN", public_url = "https://jellyfin.example.com" }
plex = { url = "http://192.168.1.22:32400", token = "file:/etc/faro/plex-token" }
navidrome = { url = "http://192.168.1.23:4533", user = "faro", password = "env:FARO_NAVIDROME" }
```

Configure any of them. `url` is how faro reaches the server. `public_url`
(optional) is where a tap on a poster takes you. A Jellyfin API key is created in
*Dashboard → API Keys*. For Plex, use the `X-Plex-Token` of your account.
Posters go through faro and stay cached on disk for a week, so the tokens never
reach the browser. The assistant gets a `now_playing` tool: *"why is the CPU
busy?"* can be answered with *"Leo is watching a film that's being transcoded"*.

### speedtest

```toml
[plugins.speedtest]
networks = [{ name = "home", cidr = "192.168.1.0/24" }, { name = "VPN", cidr = "10.8.0.0/24" }]
max_mb = 256          # cap per direction; lower it on a Raspberry Pi or a metered link
```

It measures from the browser: the best of six pings, six seconds of download
(random bytes, so nothing on the way can compress them) and an upload sized to
match. That tells you what your phone really gets from your server at home or
over your VPN, which a public speed test can't. Results are labelled with the
network they came from, and the assistant's `speed` tool reads them (*"is the
VPN slow?"*).

### automations

```toml
[plugins.automations.restart_down]      # restart the container of a service that stopped answering
after_minutes = 2
exclude = ["proxy"]                     # service ids never to restart

[plugins.automations.idle_shutdown]     # shut down VMs nobody is using
guests = ["pve1:107"]
idle_minutes = 25
below_cores = 0.08                      # idle = using less than 8 % of one core

[plugins.automations.report]            # a daily summary as a notification
at = "22:00"
```

A rule runs only if its table is there, and a switch on its card turns it off
without touching the config. `restart_down` acts once per incident: if the
restart doesn't fix it, faro leaves it alone and you get the alert. That way it
can't get stuck in a restart loop. `idle_shutdown` measures real CPU use from
the host's cgroups and warns 5 minutes before shutting down. Both need the
`proxmox` plugin with an `api_token` on the host. The `report` is written by the
assistant when the `ai` plugin is set up. Without it, you get the plain figures.

## What a plugin can do

```python
from faro.plugins import Action, BasePlugin


class Plugin(BasePlugin):
    name = 'speedtest'

    def start(self):
        """Start background threads (optional)."""

    def actions(self):
        """Buttons. fn(**params) returns {'ok': bool, 'text': str}."""
        return [Action('speedtest.run', 'Run a speed test', self.run, confirm=False)]

    def cards(self):
        """Cards on the home screen, refreshed every 30 s."""
        return [{'id': 'speed', 'title': 'Internet', 'icon': 'red',
                 'items': [{'title': '940 Mb/s down', 'sub': 'measured 5 min ago', 'progress': 0.94}]}]

    def routes(self):
        """Extra endpoints, behind the same login: {(method, path): handler}."""
        return {('GET', '/api/p/speedtest/history'): lambda req: (200, self.history)}

    def run(self, **_):
        ...
        return {'ok': True, 'text': 'Started'}
```

`self.app` is the running instance: `self.app.conf`, `self.app.hosts.data(host_id)`
(the latest agent message), `self.app.checks.get(service_id)`,
`self.app.alerts.emit(level, title, body)` and `self.app.lang` (`en`/`es`).
`self.options` is the plugin's table from the config, with `env:` and `file:`
secrets already resolved.

A plugin that fails to load is logged and skipped, and the rest of faro keeps working.

## Tools for the assistant

`tools()` returns `Tool` objects the [assistant](../faro/plugins/ai/) can call
when a question needs data that isn't in the live state:

```python
from faro.plugins import Tool

def tools(self):
    return [Tool('speed_history', 'Recent internet speed measurements.', self.history,
                 step='Checking the speed tests…')]
```

`params` is a `{name: description}` dict. Every parameter reaches `fn` as a string.

## Streaming routes

A route handler that returns `None` has answered on its own. `req.sse()` starts a
Server-Sent Events response and returns a function that sends one event:

```python
def chat(req):
    send = req.sse()
    for piece in generate(req.body['question']):
        send({'t': piece})
```

## An interface of its own

A plugin that is a package (`speedtest/__init__.py`) can ship web files in
`speedtest/web/`. They're served at `/p/speedtest/…`. If the class sets
`web = 'speedtest.js'`, the browser imports that ES module after login and calls
its `init(ctx)`:

```js
export function init(ctx) {
  const card = ctx.addCard('speedtest');          // an empty .card on the home screen
  ctx.onRender(app => {                           // about once a second
    card.innerHTML = `<header>${ctx.icon('red')}${ctx.t('Internet')}</header>…`;
  });
}
```

| `ctx.` | |
|---|---|
| `app.S` | the live state (hosts, services, config) |
| `api(path)` / `api(path, body)` | GET / POST with the session and CSRF header |
| `lang`, `t`, `esc`, `icon(name)`, `addIcon(name, svg)` | language, translation, HTML escaping, icons |
| `addCard(id)` | adds a card to the home screen and returns it |
| `onRender(fn)` | runs `fn(app)` on every update |
| `openSheet(element)`, `closeSheet()` | the bottom sheet |
| `toast(text, bad)`, `store.get/set` | a short message; per-browser settings |
