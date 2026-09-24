import http.client
import json
import tempfile
import threading
import unittest

from faro.app import Faro
from faro.auth import hash_password
from faro.config import normalise
from faro.web import Server, make_handler


class WebTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory()
        conf = normalise({'server': {'data_dir': cls.dir.name, 'port': 0, 'bind': '127.0.0.1'},
                          'auth': {'password_hash': hash_password('pw', 1000)},
                          'hosts': [{'id': 'nas', 'address': '10.0.0.2', 'api_token': 'faro@pve!x=SECRET'}],
                          'services': [{'name': 'Web', 'url': 'http://10.0.0.3'}]})
        cls.app = Faro(conf)            # not started: no agents, no checks
        cls.httpd = Server(('127.0.0.1', 0), make_handler(cls.app))
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.dir.cleanup()

    def req(self, method, path, body=None, headers=None):
        c = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        h = dict(headers or {})
        if body is not None:
            body = json.dumps(body)
            h.setdefault('Content-Type', 'application/json')
        c.request(method, path, body, h)
        r = c.getresponse()
        data = r.read()
        c.close()
        return r, data

    def login(self):
        r, _ = self.req('POST', '/api/login', {'password': 'pw'}, {'X-Faro': '1'})
        self.assertEqual(r.status, 200)
        return r.getheader('Set-Cookie').split(';')[0]

    def test_me_is_public(self):
        r, data = self.req('GET', '/api/me')
        self.assertEqual(r.status, 200)
        self.assertEqual(json.loads(data), {'auth': True, 'logged_in': False, 'title': 'faro',
                                            'language': 'auto', 'version': self.app.version})

    def test_api_needs_login(self):
        for path in ('/api/state', '/api/alerts', '/api/stream'):
            r, _ = self.req('GET', path)
            self.assertEqual(r.status, 401, path)

    def test_post_needs_csrf_header(self):
        r, _ = self.req('POST', '/api/login', {'password': 'pw'})
        self.assertEqual(r.status, 403)

    def test_wrong_password(self):
        r, _ = self.req('POST', '/api/login', {'password': 'nope'}, {'X-Faro': '1', 'X-Forwarded-For': '5.5.5.5'})
        self.assertEqual(r.status, 401)

    def test_cookie_flags(self):
        r, _ = self.req('POST', '/api/login', {'password': 'pw'}, {'X-Faro': '1'})
        cookie = r.getheader('Set-Cookie')
        self.assertIn('HttpOnly', cookie)
        self.assertIn('SameSite=Strict', cookie)

    def test_state_after_login_has_no_secrets(self):
        cookie = self.login()
        r, data = self.req('GET', '/api/state', headers={'Cookie': cookie})
        self.assertEqual(r.status, 200)
        self.assertNotIn(b'SECRET', data)
        self.assertNotIn(b'pbkdf2', data)
        d = json.loads(data)
        self.assertEqual([s['id'] for s in d['config']['services']], ['web'])

    def test_unknown_action(self):
        cookie = self.login()
        r, data = self.req('POST', '/api/action', {'id': 'rm -rf', 'params': {}}, {'X-Faro': '1', 'Cookie': cookie})
        self.assertEqual(json.loads(data)['ok'], False)

    def test_static_and_traversal(self):
        r, data = self.req('GET', '/')
        self.assertEqual(r.status, 200)
        self.assertIn(b'<script type="module"', data)
        self.assertEqual(r.getheader('X-Frame-Options'), 'DENY')
        for path in ('/../faro/auth.py', '/%2e%2e/faro/auth.py', '/js/../../faro/auth.py'):
            r, _ = self.req('GET', path)
            self.assertEqual(r.status, 404, path)


if __name__ == '__main__':
    unittest.main()
