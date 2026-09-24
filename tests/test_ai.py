import http.client
import json
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from faro.app import Faro
from faro.config import normalise
from faro.web import Server, make_handler

AGENT_DATA = {
    'ts': 0, 'cpu': {'total': 12.0, 'cores': [12.0]}, 'mem': {'total': 8 * 2**30, 'used': 2 * 2**30},
    'uptime': 86400 * 3, 'cpu_temp': 44.0, 'host': {'node': 'nas', 'threads': 4, 'os': 'Debian'},
    'guests': [{'vmid': 101, 'kind': 'lxc', 'name': 'jellyfin', 'status': 'running', 'cpus': 2, 'maxmem': 2**31}],
    'backups': {'usb': {'guests': {'101': {'ts': time.time() - 7200, 'size': 1}}}},
    'gcpu': {101: 0.5}, 'net': {}, 'temps': [],
}


class FakeOllama(BaseHTTPRequestHandler):
    """Picks the 'guests' tool in step 1 and streams two words in step 2; remembers what it was sent."""
    seen = []

    def do_GET(self):
        body = b'{"version":"0.0"}' if self.path == '/api/version' else b'{"models":[]}'
        self.send_response(200)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        FakeOllama.seen.append(req)
        if not req.get('stream'):
            body = json.dumps({'message': {'content': json.dumps({'tool': 'guests', 'argument': ''})}}).encode()
            self.send_response(200)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            return self.wfile.write(body)
        lines = [{'message': {'content': 'All '}}, {'message': {'content': 'good.'}},
                 {'done': True, 'eval_count': 10, 'eval_duration': 1e9}]
        body = ''.join(json.dumps(x) + '\n' for x in lines).encode()
        self.send_response(200)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


class AiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ollama = ThreadingHTTPServer(('127.0.0.1', 0), FakeOllama)
        threading.Thread(target=cls.ollama.serve_forever, daemon=True).start()
        cls.dir = tempfile.TemporaryDirectory()
        conf = normalise({'server': {'data_dir': cls.dir.name}, 'auth': {'mode': 'none'}, 'language': 'en',
                          'hosts': [{'id': 'nas', 'name': 'NAS', 'address': '10.0.0.2'}],
                          'plugins': {'ai': {'url': f'http://127.0.0.1:{cls.ollama.server_address[1]}',
                                             'guide': 'The NAS keeps the backups.'}}})
        cls.app = Faro(conf)
        cls.app.hosts.feed(conf['hosts'][0], dict(AGENT_DATA, ts=time.time()))
        cls.ai = cls.app.plugin('ai')
        cls.httpd = Server(('127.0.0.1', 0), make_handler(cls.app))
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        for s in (cls.httpd, cls.ollama):
            s.shutdown()
            s.server_close()
        cls.dir.cleanup()

    def test_state_text(self):
        slow, live = self.ai.state_text()
        self.assertIn('101 jellyfin', slow)
        self.assertIn('Backups on usb: newest 2 h ago (1 guests)', slow)
        self.assertIn('NAS (Debian): CPU 12 %', live)

    def test_system_prompt_lists_tools_and_guide(self):
        p = self.ai.system_prompt()
        self.assertIn('The NAS keeps the backups.', p)
        for tool in ('cpu', 'guests', 'disks', 'backups', 'alerts'):
            self.assertIn(f'- {tool}(', p)

    def test_empty_tool_result_is_spelled_out(self):
        self.assertEqual(self.ai.run_tool('alerts', {}), {'result': 'Nothing found: the list is empty.'})
        self.assertIn('error', self.ai.run_tool('nope', {}))

    def test_chat_picks_a_tool_and_streams(self):
        FakeOllama.seen.clear()
        c = http.client.HTTPConnection('127.0.0.1', self.httpd.server_address[1], timeout=10)
        c.request('POST', '/api/p/ai/chat', json.dumps({'messages': [{'role': 'user', 'text': 'Is jellyfin on?'}]}),
                  {'X-Faro': '1'})
        events = [json.loads(line[6:]) for line in c.getresponse().read().decode().split('\n\n') if line]
        c.close()
        self.assertEqual(events[0], {'step': 'Checking the machines…'})
        self.assertEqual(''.join(e.get('t', '') for e in events), 'All good.')
        self.assertEqual(events[-1], {'done': True, 'tps': 10.0, 'tools': ['guests']})
        decide, answer = FakeOllama.seen
        self.assertEqual(decide['format']['properties']['tool']['enum'][0], 'none')
        # the tool's result reached the model in the second call
        self.assertIn('"name": "jellyfin"', answer['messages'][-1]['content'])
        # both calls start with the same system prompt: Ollama can reuse its cache
        self.assertEqual(decide['messages'][0], answer['messages'][0])


if __name__ == '__main__':
    unittest.main()
