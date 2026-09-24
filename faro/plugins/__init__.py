"""Plugin system.

A plugin is a Python module with a `Plugin` class that subclasses `BasePlugin`.
It is enabled by giving it a table in the config:

    [plugins.proxmox]          # built-in, no options needed

    [plugins.my_plugin]        # your own: /etc/faro/plugins/my_plugin.py
    url = "http://10.0.0.5:1234"

Built-in plugins live in this package; your own go in `server.plugin_dir`
(default /etc/faro/plugins), so private integrations never need to be in
the public repository. A plugin can be a single file or a package; a package
with a `web/` folder can ship its own interface as an ES module. See docs/plugins.md.
"""
import importlib
import importlib.util
import os
import sys
import traceback


class Action:
    """Something the user can do from the UI (a button) and, later, the assistant.

    fn(**params) must return {'ok': bool, 'text': str}.
    """
    def __init__(self, id, label, fn, confirm=False, params=None):
        self.id, self.label, self.fn, self.confirm, self.params = id, label, fn, confirm, params or {}

    def describe(self):
        return {'id': self.id, 'label': self.label, 'confirm': self.confirm, 'params': self.params}


class Tool:
    """Something the assistant can look up. fn(**params) returns anything JSON-serialisable.

    params: {name: description}; all of them are strings.
    """
    def __init__(self, name, description, fn, params=None, step=None):
        self.name, self.description, self.fn, self.params = name, description, fn, params or {}
        self.step = step            # what the UI shows while it runs, e.g. "Checking Jellyfin…"


class BasePlugin:
    name = 'plugin'
    web = None                      # file in the plugin's web/ folder loaded by the browser, e.g. 'ai.js'

    def __init__(self, app, options):
        self.app = app              # the running Faro instance: .conf, .hosts, .checks, .alerts
        self.options = options      # this plugin's table from faro.toml (secrets already resolved)
        self.static_dir = None      # set by the loader when the plugin has a web/ folder

    def start(self):
        """Start background threads, if any."""

    def actions(self):
        """List of Action objects."""
        return []

    def cards(self):
        """Home-screen cards: [{'id', 'title', 'icon', 'items': [{'title', 'sub', 'url', 'img', 'progress'}]}]."""
        return []

    def tools(self):
        """Tool objects the assistant may use to answer questions."""
        return []

    def routes(self):
        """Extra HTTP endpoints: {('GET', '/api/p/<name>/x'): handler(request) -> (status, dict)}.

        A handler that writes its own response (e.g. a stream) returns None.
        POST handlers find the decoded JSON body in request.body, unless the handler
        has `raw = True`: then it reads request.rfile itself (for uploads).
        """
        return {}


def load(app):
    conf = app.conf
    plugin_dir = conf['server'].get('plugin_dir', '/etc/faro/plugins')
    loaded = []
    for name, options in conf['plugins'].items():
        if options.get('enabled') is False:
            continue
        try:
            mod = _import(name, plugin_dir)
            plugin = mod.Plugin(app, options)
            web = os.path.join(os.path.dirname(mod.__file__), 'web')
            if os.path.basename(mod.__file__) == '__init__.py' and os.path.isdir(web):
                plugin.static_dir = web
            loaded.append(plugin)
            print(f'plugin: {name} loaded', flush=True)
        except Exception:
            print(f'plugin: {name} failed to load\n{traceback.format_exc()}', flush=True)
    return loaded


def _import(name, plugin_dir):
    own = os.path.join(plugin_dir, name + '.py')
    package = os.path.join(plugin_dir, name, '__init__.py')
    if os.path.isfile(package):
        spec = importlib.util.spec_from_file_location(f'faro_plugin_{name}', package,
                                                      submodule_search_locations=[os.path.dirname(package)])
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        return mod
    if os.path.isfile(own):
        spec = importlib.util.spec_from_file_location(f'faro_plugin_{name}', own)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        return mod
    return importlib.import_module(f'{__name__}.{name}')
