"""Public demo stays local even if integration credentials are configured."""
import copy
import http.client
import json
import tempfile
import threading
import time
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from faro import demo
from faro.app import Faro
from faro.config import normalise
from faro.web import Server, make_handler


class DemoTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        raw = copy.deepcopy(demo.CONFIG)
        raw['server']['data_dir'] = self.directory.name
        raw['notify'] = {'ntfy': {'url': 'https://ntfy.example.com'},
                         'webhook': {'url': 'https://hooks.example.com', 'format': 'discord'}}
        raw['hosts'][0]['api_token'] = 'faro@pve!demo=secret'
        raw['plugins']['proxmox'] = {}
        raw['plugins']['ai'] = {'demo': False, 'url': 'https://model.example.com', 'log': True}
        raw['plugins']['media'] = {'demo': False, 'jellyfin': {'url': 'https://media.example.com', 'token': 'secret'}}
        self.app = Faro(normalise(raw), demo=True)
        now = time.time()
        self.app.hosts.feed(self.app.conf['hosts'][0], demo.pve1(now, 86400))
        self.app.hosts.feed(self.app.conf['hosts'][1], demo.pi(now, 86400))
        self.httpd = Server(('127.0.0.1', 0), make_handler(self.app))
        self.addCleanup(self.httpd.server_close)
        self.addCleanup(self.httpd.shutdown)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def request(self, method, path, body=None):
        with closing(http.client.HTTPConnection('127.0.0.1', self.httpd.server_address[1], timeout=5)) as conn:
            conn.request(method, path, json.dumps(body) if body is not None else None, {'X-Faro': '1'})
            response = conn.getresponse()
            return response.status, response.read()

    def test_public_without_password_and_no_configuration_routes(self):
        status, page = self.request('GET', '/')
        self.assertEqual(status, 200)
        self.assertIn(b'<script type="module"', page)
        status, body = self.request('GET', '/api/me')
        self.assertEqual(status, 200)
        me = json.loads(body)
        self.assertTrue(me['demo'])
        self.assertFalse(me['auth'])
        self.assertTrue(me['logged_in'])
        self.assertEqual(self.request('GET', '/api/state')[0], 200)
        for path in ('/api/config', '/api/settings', '/api/hosts', '/api/plugins', '/api/upload'):
            for method in ('GET', 'POST'):
                self.assertEqual(self.request(method, path, {} if method == 'POST' else None)[0], 404, (method, path))
        for path in ('/../faro/config.py', '/%2e%2e/faro/config.py', '/p/ai/../../../../etc/passwd'):
            self.assertEqual(self.request('GET', path)[0], 404, path)

    def test_no_notifications_models_media_or_power_calls(self):
        with patch('urllib.request.urlopen') as network:
            self.assertFalse(self.app.alerts.notifier.enabled)
            status, body = self.request('POST', '/api/alerts/test', {})
            self.assertEqual(status, 200)
            self.assertFalse(json.loads(body)['notifiers'])
            ai = self.app.plugin('ai')
            self.assertEqual(self.request('GET', '/api/p/ai/status?warm=1')[0], 200)
            self.assertEqual(self.request('POST', '/api/p/ai/sleep', {})[0], 200)
            ai.warm_up()
            with self.assertRaises(RuntimeError):
                ai.chat([])
            with patch('faro.plugins.ai.time.sleep'):
                status, body = self.request('POST', '/api/p/ai/chat', {
                    'messages': [{'role': 'user', 'text': 'How are my servers?'}]})
            self.assertEqual(status, 200)
            self.assertIn(b'"done": true', body)
            self.app.plugin('automations').send_report()
            media = self.app.plugin('media')
            media.start()
            self.assertTrue(media.state['playing'])
            status, body = self.request('GET', '/api/p/media/img?src=jf&key=' + 'a' * 32)
            self.assertEqual(status, 200)
            self.assertTrue(body.startswith(b'<svg'))
            px = self.app.plugin('proxmox')
            for op in ('start', 'shutdown', 'reboot', 'stop'):
                self.assertFalse(px.power(host='pve1', vmid=101, op=op)['ok'])
            self.assertNotIn('guest.power', self.app.actions)
            network.assert_not_called()

    def test_demo_start_never_starts_ssh_or_service_checks(self):
        with patch('faro.demo.start') as seed, patch.object(self.app.hosts, 'start') as hosts, \
                patch.object(self.app.checks, 'start') as checks, patch.object(self.app.alerts, 'start'), \
                patch('faro.plugins.BasePlugin.start'), patch('threading.Thread.start'):
            self.app.start()
            seed.assert_called_once_with(self.app)
            hosts.assert_not_called()
            checks.assert_not_called()

    def test_writes_stay_in_the_demo_data_directory(self):
        before = copy.deepcopy(self.app.conf)
        status, _ = self.request('POST', '/api/p/automations/toggle', {'id': 'report', 'on': False})
        self.assertEqual(status, 200)
        status, _ = self.request('POST', '/api/p/speedtest/result', {
            'down': 100, 'up': 50, 'ping': 5, 'path': '/etc/faro/faro.toml',
            'data_dir': '/etc/faro', 'url': 'https://model.example.com'})
        self.assertEqual(status, 200)
        self.app.alerts.test()
        self.app.hosts.save()
        self.app.plugin('ai').log('question', 'answer', 1, [])
        root = Path(self.directory.name).resolve()
        paths = [self.app.alerts.path, self.app.hosts.history_path, self.app.plugin('ai').log_path,
                 self.app.plugin('media').img_dir, self.app.plugin('speedtest').path,
                 self.app.plugin('automations').state_path]
        for path in paths:
            self.assertTrue(Path(path).resolve().is_relative_to(root), path)
        self.assertEqual({p.name for p in root.iterdir()}, {
            'automations.json', 'speedtest.json', 'alerts.json', 'history.json', 'ai.jsonl'})
        self.assertEqual(self.app.conf, before)


if __name__ == '__main__':
    unittest.main()
