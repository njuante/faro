import tempfile
import time
import unittest

from faro.app import Faro
from faro.config import normalise


class FakeProxmox:
    name = 'proxmox'

    def __init__(self):
        self.hosts = {'pve': {}}
        self.calls = []

    def power(self, host, vmid, op):
        self.calls.append((host, str(vmid), op))
        return {'ok': True, 'text': f'{op} {vmid}'}


class AutomationsTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        conf = normalise({
            'server': {'data_dir': self.dir.name}, 'auth': {'mode': 'none'}, 'language': 'en',
            'hosts': [{'id': 'pve', 'address': '10.0.0.2'}],
            'services': [{'name': 'Photos', 'url': 'http://10.0.0.5', 'host': 'pve', 'guest': 105},
                         {'name': 'Proxy', 'url': 'http://10.0.0.6', 'host': 'pve', 'guest': 106}],
            'plugins': {'automations': {'restart_down': {'after_minutes': 2, 'exclude': ['proxy']},
                                        'idle_shutdown': {'guests': ['pve:107'], 'idle_minutes': 25},
                                        'report': {'at': '00:00'}}}})
        self.app = Faro(conf)
        self.px = FakeProxmox()
        self.app.plugins.append(self.px)
        self.auto = self.app.plugin('automations')
        self.app.alerts.notifier.send = lambda a: None

    def tearDown(self):
        self.dir.cleanup()

    def set_down(self, sid, down):
        self.app.checks.state[sid]['up'] = not down

    def test_restart_once_per_incident(self):
        t = time.time()
        self.set_down('photos', True)
        self.set_down('proxy', True)
        self.auto.check_down(t)
        self.auto.check_down(t + 60)
        self.assertEqual(self.px.calls, [])                             # not two minutes yet
        self.auto.check_down(t + 121)
        self.auto.check_down(t + 300)
        self.assertEqual(self.px.calls, [('pve', '105', 'reboot')])      # once, and never the excluded one
        self.set_down('photos', False)
        self.auto.check_down(t + 400)
        self.set_down('photos', True)
        self.auto.check_down(t + 500)
        self.auto.check_down(t + 700)
        self.assertEqual(len(self.px.calls), 2)                          # a new incident may restart again
        self.assertIn('Photos was not answering', self.app.alerts.recent()[0]['title'])

    def test_idle_shutdown_warns_then_stops(self):
        guest = {'vmid': 107, 'name': 'win11', 'status': 'running', 'kind': 'qemu', 'cpus': 4}
        data = {'ts': time.time(), 'cpu': {'total': 1, 'cores': [1]}, 'guests': [guest], 'gcpu': {'107': 0.01}}
        self.app.hosts.feed(self.app.conf['hosts'][0], data)
        t = time.time()
        self.auto.check_idle(t)
        self.auto.check_idle(t + 20 * 60 + 1)
        self.assertEqual(self.app.alerts.recent()[0]['title'], 'win11 shuts down in 5 minutes')
        self.auto.check_idle(t + 25 * 60 + 1)
        self.assertEqual(self.px.calls, [('pve', '107', 'shutdown')])
        # busy again: the countdown starts over
        data['gcpu'] = {'107': 1.5}
        self.app.hosts.feed(self.app.conf['hosts'][0], dict(data, ts=time.time()))
        self.auto.check_idle(t + 30 * 60)
        self.assertNotIn('pve:107', self.auto.idle_since)

    def test_report_once_a_day_without_a_model(self):
        self.auto.report_day = ''
        self.auto.check_report()
        self.auto.check_report()
        reports = [a for a in self.app.alerts.recent() if a['title'] == 'Daily report']
        self.assertEqual(len(reports), 1)
        self.assertIn('services answering', reports[0]['body'])

    def test_toggle_is_saved(self):
        self.auto.enabled['report'] = False
        self.auto._save()
        again = type(self.auto)(self.app, self.auto.options)
        self.assertFalse(again.enabled['report'])
        self.assertTrue(again.enabled['restart_down'])
        self.assertEqual([r['id'] for r in again.describe()], ['restart_down', 'idle_shutdown', 'report'])

    def test_without_proxmox_it_only_logs(self):
        self.app.plugins.remove(self.px)
        t = time.time()
        self.set_down('photos', True)
        self.auto.check_down(t)
        self.auto.check_down(t + 200)
        self.assertIn('enable the proxmox plugin', self.auto.log[-1]['text'])


if __name__ == '__main__':
    unittest.main()
