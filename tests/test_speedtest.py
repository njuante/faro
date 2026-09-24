import http.client
import json
import tempfile
import threading
import unittest

from faro.app import Faro
from faro.config import normalise
from faro.web import Server, make_handler


class SpeedtestTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory()
        conf = normalise({'server': {'data_dir': cls.dir.name}, 'auth': {'mode': 'none'}, 'language': 'en',
                          'plugins': {'speedtest': {'networks': [{'name': 'loopback', 'cidr': '127.0.0.0/8'},
                                                                 {'name': 'VPN', 'cidr': '10.8.0.0/24'}]}}})
        cls.app = Faro(conf)
        cls.p = cls.app.plugin('speedtest')
        cls.httpd = Server(('127.0.0.1', 0), make_handler(cls.app))
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.dir.cleanup()

    def req(self, method, path, body=None, headers=None):
        c = http.client.HTTPConnection('127.0.0.1', self.httpd.server_address[1], timeout=10)
        c.request(method, path, body, {'X-Faro': '1', **(headers or {})})
        r = c.getresponse()
        data = r.read()
        c.close()
        return r.status, data

    def test_download_is_random_and_sized(self):
        status, data = self.req('GET', '/api/p/speedtest/down?mb=2')
        self.assertEqual((status, len(data)), (200, 2 << 20))
        self.assertGreater(len(set(data[:4096])), 200)         # not compressible
        self.assertEqual(len(self.req('GET', '/api/p/speedtest/down?mb=0')[1]), 1 << 20)

    def test_upload_takes_a_raw_body(self):
        status, data = self.req('POST', '/api/p/speedtest/up', b'\0' * (3 << 20))
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(data)['bytes'], 3 << 20)

    def test_result_history_and_tool(self):
        tool = self.app.tools['speed']
        self.assertIn('result', tool.fn())
        status, data = self.req('POST', '/api/p/speedtest/result', json.dumps({'down': 912.34, 'up': 88, 'ping': 3.2}),
                                {'User-Agent': 'Test phone'})
        m = json.loads(data)
        self.assertEqual((m['down'], m['where'], m['device']), (912.3, 'loopback', 'Test phone'))
        self.assertEqual(self.req('POST', '/api/p/speedtest/result', '{"down": "fast"}')[0], 400)
        hist = json.loads(self.req('GET', '/api/p/speedtest/history')[1])
        self.assertEqual(hist[-1]['down'], 912.3)
        out = tool.fn()
        self.assertEqual(out['latest']['where'], 'loopback')
        self.assertEqual(out['average by network (Mbps, ms)']['loopback']['tests'], 1)

    def test_where(self):
        self.assertEqual(self.p.where('10.8.0.5'), 'VPN')
        self.assertEqual(self.p.where('8.8.8.8'), 'elsewhere')
        self.assertEqual(self.p.where('nonsense'), 'elsewhere')


if __name__ == '__main__':
    unittest.main()
