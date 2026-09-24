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
