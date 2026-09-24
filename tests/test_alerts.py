import tempfile
import time
import unittest

from faro.alerts import Alerts
from faro.config import normalise


class FakeHosts:
    def __init__(self):
        self.seen_at, self.payload = {}, {}

    def seen(self, hid):
        return self.seen_at.get(hid)

    def data(self, hid):
        return self.payload.get(hid)


class FakeChecks:
    def __init__(self):
        self.st = {}

    def get(self, sid):
        return self.st.get(sid)


class AlertsTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        conf = normalise({'server': {'data_dir': self.dir.name}, 'language': 'en',
                          'alerts': {'service_down_after': 0, 'host_offline_after': 90},
                          'hosts': [{'id': 'nas', 'name': 'NAS', 'address': '10.0.0.2'}],
                          'services': [{'name': 'Web', 'url': 'http://10.0.0.3'}]})
        self.hosts, self.checks = FakeHosts(), FakeChecks()
        self.a = Alerts(conf, self.hosts, self.checks)
        self.a.notifier.send = lambda alert: None
        self.hosts.seen_at['nas'] = time.time()

    def tearDown(self):
        self.dir.cleanup()

    def titles(self):
        return [x['title'] for x in self.a.recent()][::-1]

    def test_track_waits_then_fires_once_then_recovers(self):
        bad = lambda: ('down', '', 4, None)            # noqa: E731
        good = lambda d: ('up', '', 3, None)           # noqa: E731
        self.a.track('k', True, 3600, bad, good)
        self.assertEqual(self.titles(), [])             # not long enough yet
        self.a.watch['k']['since'] -= 3601
        self.a.track('k', True, 3600, bad, good)
        self.a.track('k', True, 3600, bad, good)
        self.assertEqual(self.titles(), ['down'])       # only once
        self.a.track('k', False, 3600, bad, good)
        self.assertEqual(self.titles(), ['down', 'up'])

    def test_service_down_and_back(self):
        self.checks.st['web'] = {'up': False, 'code': 'refused'}
        self.a.evaluate()
        self.assertEqual(self.titles(), ['Web is down'])
        self.assertIn('port closed', self.a.recent()[0]['body'])
        self.assertEqual(self.a.active(), ['svc:web'])
        self.checks.st['web'] = {'up': True, 'code': 200}
        self.a.evaluate()
        self.assertEqual(self.titles(), ['Web is down', 'Web is back up'])
        self.assertEqual(self.a.active(), [])

    def test_host_offline(self):
        self.hosts.seen_at['nas'] = time.time() - 120
        self.a.evaluate()
        self.assertEqual(self.titles(), ['NAS stopped reporting'])

    def test_disk_rules(self):
        self.hosts.payload['nas'] = {
            'disks': [{'name': 'sda', 'serial': 'S1', 'model': 'X', 'tran': 'sata', 'rota': True,
                       'smart': {'healthy': True, 'realloc': 8, 'pending': 0, 'temp': 40}}],
            'fs': [{'mount': '/data', 'total': 100, 'used': 95, 'avail': 5}],
            'zfs': {'pools': [{'name': 'tank', 'health': 'DEGRADED'}]},
        }
        self.a.evaluate()
        self.a.watch['fs:nas:/data']['since'] -= 61
        self.a.evaluate()
        self.assertEqual(sorted(self.titles()), sorted(['Disk sda is failing', 'ZFS pool tank is DEGRADED',
                                                        '/data on NAS is almost full']))

    def test_log_survives_restart(self):
        self.a.emit('info', 'hello')
        again = Alerts(self.a.conf, self.hosts, self.checks)
        self.assertEqual(again.recent()[0]['title'], 'hello')


if __name__ == '__main__':
    unittest.main()
