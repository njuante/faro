"""Wires everything together: config, hosts, checks, alerts, plugins and the action log."""
import json
import os
import threading
import time
from collections import deque

from . import __version__, plugins
from .alerts import Alerts
from .checks import Checks
from .config import public_view
from .hosts import Hosts


class Faro:
    def __init__(self, conf, demo=False):
        self.conf = conf
        self.demo = demo
        self.version = __version__
        self.lang = conf['language'] if conf['language'] in ('en', 'es') else 'en'
        os.makedirs(conf['server']['data_dir'], exist_ok=True)
        self.hosts = Hosts(conf)
        self.checks = Checks(conf)
        self.alerts = Alerts(conf, self.hosts, self.checks)
        self.plugins = plugins.load(self)
        self.actions = {a.id: a for p in self.plugins for a in p.actions()}
        self.routes = {k: v for p in self.plugins for k, v in p.routes().items()}
        self.action_log = deque(maxlen=100)
        self.action_lock = threading.Lock()

    def start(self):
        if self.demo:
            from . import demo
            demo.start(self)
        else:
            self.hosts.start()
            self.checks.start()
        self.alerts.start(grace=5 if self.demo else 60)
        for p in self.plugins:
            p.start()

    def run_action(self, action_id, params, who):
        a = self.actions.get(action_id)
        if not a:
            return {'ok': False, 'text': 'unknown action'}
        try:
            res = a.fn(**params)
        except TypeError:
            res = {'ok': False, 'text': 'bad parameters'}
        with self.action_lock:
            self.action_log.append({'ts': time.time(), 'action': action_id, 'params': params,
                                    'who': who, 'ok': res.get('ok'), 'text': res.get('text')})
        print(f'action: {action_id} {json.dumps(params)} by {who} -> {res.get("text")}', flush=True)
        return res

    def cards(self):
        out = []
        for p in self.plugins:
            try:
                out.extend(p.cards())
            except Exception as e:
                print(f'plugin {p.name}: cards failed: {e}', flush=True)
        return out

    def snapshot(self, full):
        out = {'now': time.time(), 'hosts': self.hosts.snapshot(full), 'services': self.checks.snapshot(full),
               'problems': self.alerts.active()}
        if full:
            out['config'] = public_view(self.conf)
            out['actions'] = [a.describe() for a in self.actions.values()]
            out['version'] = self.version
            out['demo'] = self.demo
        return out
