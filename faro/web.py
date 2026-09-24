"""HTTP server: the web app, a JSON API and a Server-Sent Events stream."""
import ipaddress
import json
import os
import time
import urllib.parse
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .auth import COOKIE, Auth

WEB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'web')
TYPES = {'.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8',
         '.js': 'text/javascript; charset=utf-8', '.json': 'application/json', '.svg': 'image/svg+xml',
         '.png': 'image/png', '.webp': 'image/webp', '.jpg': 'image/jpeg', '.ico': 'image/x-icon',
         '.woff2': 'font/woff2', '.webmanifest': 'application/manifest+json'}
SECURITY_HEADERS = [
    ('X-Content-Type-Options', 'nosniff'),
    ('Referrer-Policy', 'same-origin'),
    ('X-Frame-Options', 'DENY'),
    ('Content-Security-Policy', "default-src 'self'; img-src 'self' data: https:; style-src 'self' 'unsafe-inline'; "
                                "script-src 'self'; connect-src 'self'; frame-ancestors 'none'"),
]
PUBLIC_API = {'/api/me', '/api/login'}


def make_handler(app):
    auth = Auth(app.conf)
    trusted = [ipaddress.ip_network(n) for n in app.conf['server'].get('trusted_proxies', ['127.0.0.1/32', '::1/128'])]

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'
        server_version = 'faro'
        sys_version = ''

        # ---------------------------------------------------------- helpers

        def client_ip(self):
            fwd = self.headers.get('X-Forwarded-For')
            if fwd and self.behind_proxy():
                return fwd.split(',')[-1].strip()
            return self.client_address[0]

        def behind_proxy(self):
            try:
                return any(ipaddress.ip_address(self.client_address[0]) in n for n in trusted)
            except ValueError:
                return False

        def is_https(self):
            return self.behind_proxy() and self.headers.get('X-Forwarded-Proto') == 'https'

        def token(self):
            c = SimpleCookie(self.headers.get('Cookie') or '')
            return c[COOKIE].value if COOKIE in c else None

        def send(self, code, body, ctype='application/json', extra=()):
            if isinstance(body, (dict, list)):
                body = json.dumps(body, ensure_ascii=False).encode()
            elif isinstance(body, str):
                body = body.encode()
            self.send_response(code)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(len(body)))
            for k, v in SECURITY_HEADERS:
                self.send_header(k, v)
            for k, v in extra:
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def api(self, code, body, extra=()):
            self.send(code, body, 'application/json', [('Cache-Control', 'no-store'), *extra])

        def read_json(self, limit=16384):
            n = int(self.headers.get('Content-Length') or 0)
            if n > limit:
                raise ValueError('body too large')
            return json.loads(self.rfile.read(n) or b'{}')

        def query(self):
            return {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).items()}

        def cookie(self, value, max_age):
            attrs = f'{COOKIE}={value}; Path=/; HttpOnly; SameSite=Strict; Max-Age={max_age}'
            return ('Set-Cookie', attrs + ('; Secure' if self.is_https() else ''))

        # ---------------------------------------------------------- routing

        def do_GET(self):
            path = urllib.parse.urlsplit(self.path).path
            if path.startswith('/api/'):
                if path not in PUBLIC_API and not auth.valid(self.token()):
                    return self.api(401, {'error': 'login required'})
                return self.get_api(path)
            return self.static(path)

        def do_POST(self):
            path = urllib.parse.urlsplit(self.path).path
            # a custom header cannot be sent cross-site without CORS: cheap CSRF protection
            if self.headers.get('X-Faro') != '1':
                return self.api(403, {'error': 'missing X-Faro header'})
            if path not in PUBLIC_API and not auth.valid(self.token()):
                return self.api(401, {'error': 'login required'})
            try:
                body = self.read_json()
            except ValueError:
                return self.api(400, {'error': 'invalid JSON'})
            return self.post_api(path, body)

        def get_api(self, path):
            if path == '/api/me':
                return self.api(200, {'auth': auth.required, 'logged_in': auth.valid(self.token()),
                                      'title': app.conf['title'], 'language': app.conf['language'],
                                      'version': app.version})
            if path == '/api/state':
                return self.api(200, app.snapshot(True))
            if path == '/api/stream':
                return self.stream()
            if path == '/api/alerts':
                n = max(1, min(300, int(self.query().get('n') or 120)))
                return self.api(200, app.alerts.recent(n))
            if path == '/api/cards':
                return self.api(200, app.cards())
            if path == '/api/actions/log':
                with app.action_lock:
                    return self.api(200, list(app.action_log)[::-1])
            handler = app.routes.get(('GET', path))
            if handler:
                return self.plugin_response(handler)
            return self.api(404, {'error': 'not found'})

        def plugin_response(self, handler):
            try:
                res = handler(self)
            except Exception as e:
                print(f'plugin route {self.path} failed: {type(e).__name__}: {e}', flush=True)
                return self.api(500, {'error': type(e).__name__})
            if res is not None:           # None: the handler already answered (e.g. a stream)
                code, body = res
                self.api(code, body)

        def post_api(self, path, body):
            if path == '/api/login':
                ip = self.client_ip()
                if auth.throttled(ip):
                    return self.api(429, {'error': 'too many attempts, wait a few minutes'})
                token = auth.login(ip, body.get('password'))
                if not token:
                    time.sleep(1)
                    return self.api(401, {'error': 'wrong password'})
                return self.api(200, {'ok': True}, [self.cookie(token, auth.ttl)])
            if path == '/api/logout':
                auth.logout(self.token())
                return self.api(200, {'ok': True}, [self.cookie('', 0)])
            if path == '/api/action':
                params = body.get('params') or {}
                if not isinstance(params, dict):
                    return self.api(400, {'error': 'params must be an object'})
                return self.api(200, app.run_action(body.get('id'), params, self.client_ip()))
            if path == '/api/alerts/test':
                app.alerts.test()
                return self.api(200, {'ok': True, 'notifiers': app.alerts.notifier.enabled})
            handler = app.routes.get(('POST', path))
            if handler:
                self.body = body
                return self.plugin_response(handler)
            return self.api(404, {'error': 'not found'})

        def sse(self):
            """Starts a Server-Sent Events response; returns a function that sends one event."""
            self.close_connection = True
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Accel-Buffering', 'no')
            self.send_header('Connection', 'close')
            self.end_headers()

            def send(data):
                self.wfile.write(f'data: {json.dumps(data, ensure_ascii=False)}\n\n'.encode())
                self.wfile.flush()
            return send

        def stream(self):
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Accel-Buffering', 'no')
            self.end_headers()
            try:
                while True:
                    msg = json.dumps(app.snapshot(False), separators=(',', ':'))
                    self.wfile.write(f'data: {msg}\n\n'.encode())
                    self.wfile.flush()
                    time.sleep(1)
                    if not auth.valid(self.token()):      # logged out elsewhere
                        return
            except (BrokenPipeError, ConnectionResetError, OSError):
                return

        def static(self, path):
            if path == '/':
                path = '/index.html'
            root = WEB
            if path.startswith('/p/'):          # a plugin's own web files: /p/<name>/<file>
                _, _, name, rest = (path.split('/', 3) + [''])[:4]
                plugin = app.plugin(name)
                if not plugin or not plugin.static_dir:
                    return self.send(404, 'not found', 'text/plain')
                root, path = plugin.static_dir, '/' + rest
            f = os.path.normpath(os.path.join(root, path.lstrip('/')))
            if not f.startswith(root + os.sep) or not os.path.isfile(f):
                return self.send(404, 'not found', 'text/plain')
            with open(f, 'rb') as fh:
                body = fh.read()
            ext = os.path.splitext(f)[1]
            cache = 'no-cache' if ext in ('.html', '.js', '.css', '.webmanifest') else 'public, max-age=86400'
            self.send(200, body, TYPES.get(ext, 'application/octet-stream'), [('Cache-Control', cache)])

        def log_message(self, fmt, *a):
            pass      # quiet: systemd's journal would fill up with SSE reconnects

    return Handler


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def serve(app):
    srv = app.conf['server']
    httpd = Server((srv['bind'], srv['port']), make_handler(app))
    print(f'faro {app.version} listening on http://{srv["bind"]}:{srv["port"]}', flush=True)
    httpd.serve_forever()
