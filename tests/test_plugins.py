import http.client
import json
import os
import tempfile
import threading
import unittest

from faro.app import Faro
from faro.config import normalise
from faro.web import Server, make_handler

PLUGIN = '''
from faro.plugins import Action, BasePlugin, Tool


class Plugin(BasePlugin):
    name = 'hello'
    web = 'hello.js'

    def actions(self):
        return [Action('hello.say', 'Say hello', lambda who='world': {'ok': True, 'text': 'hello ' + who})]

    def tools(self):
        return [Tool('greeting', 'Greets', lambda: {'greeting': self.options['greeting']})]

    def routes(self):
        def stream(req):
            send = req.sse()
            send({'n': 1})
            send({'n': 2})
        return {('GET', '/api/p/hello/ping'): lambda req: (200, {'pong': True}),
                ('POST', '/api/p/hello/echo'): lambda req: (200, req.body),
                ('GET', '/api/p/hello/stream'): stream,
                ('GET', '/api/p/hello/boom'): lambda req: 1 / 0}
'''


class PluginTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory()
        pkg = os.path.join(cls.dir.name, 'plugins', 'hello')
        os.makedirs(os.path.join(pkg, 'web'))
        with open(os.path.join(pkg, '__init__.py'), 'w') as f:
            f.write(PLUGIN)
        with open(os.path.join(pkg, 'web', 'hello.js'), 'w') as f:
            f.write('export function init() {}\n')
        conf = normalise({'server': {'data_dir': cls.dir.name, 'plugin_dir': os.path.join(cls.dir.name, 'plugins')},
                          'auth': {'mode': 'none'},
                          'plugins': {'hello': {'greeting': 'hi'}, 'missing': {}, 'off': {'enabled': False}}})
        cls.app = Faro(conf)
        cls.httpd = Server(('127.0.0.1', 0), make_handler(cls.app))
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.dir.cleanup()

    def req(self, method, path, body=None):
        c = http.client.HTTPConnection('127.0.0.1', self.httpd.server_address[1], timeout=5)
        c.request(method, path, json.dumps(body) if body is not None else None, {'X-Faro': '1'})
        r = c.getresponse()
        data = r.read()
        c.close()
        return r.status, data

    def test_only_valid_plugins_load(self):
        self.assertEqual([p.name for p in self.app.plugins], ['hello'])

    def test_state_lists_the_web_module(self):
        state = self.app.snapshot(True)
        self.assertEqual(state['plugins'], [{'name': 'hello', 'module': '/p/hello/hello.js'}])
        self.assertEqual([a['id'] for a in state['actions']], ['hello.say'])

    def test_actions_and_tools(self):
        self.assertEqual(self.app.run_action('hello.say', {'who': 'faro'}, 'test')['text'], 'hello faro')
        self.assertEqual(self.app.run_action('hello.say', {'nope': 1}, 'test')['ok'], False)
        self.assertEqual(self.app.tools['greeting'].fn(), {'greeting': 'hi'})

    def test_static_files(self):
        status, data = self.req('GET', '/p/hello/hello.js')
        self.assertEqual(status, 200)
        self.assertIn(b'export function init', data)
        self.assertEqual(self.req('GET', '/p/hello/../__init__.py')[0], 404)
        self.assertEqual(self.req('GET', '/p/nobody/x.js')[0], 404)

    def test_routes(self):
        self.assertEqual(json.loads(self.req('GET', '/api/p/hello/ping')[1]), {'pong': True})
        self.assertEqual(json.loads(self.req('POST', '/api/p/hello/echo', {'a': 1})[1]), {'a': 1})
        self.assertEqual(self.req('GET', '/api/p/hello/boom')[0], 500)
        status, data = self.req('GET', '/api/p/hello/stream')
        self.assertEqual(data, b'data: {"n": 1}\n\ndata: {"n": 2}\n\n')


if __name__ == '__main__':
    unittest.main()
