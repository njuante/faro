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
