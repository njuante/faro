"""Speed test between the device you are holding and your server: at home, or from outside over a VPN.

    [plugins.speedtest]
    networks = [
      { name = "home", cidr = "192.168.1.0/24" },
      { name = "VPN", cidr = "10.8.0.0/24" },
    ]

`networks` (optional) labels each measurement by where it was taken from.
`max_mb` (default 256) caps how much a test sends each way: lower it on a
Raspberry Pi or a metered link.
Results are kept (the last 100) and the assistant can read them.
"""
import ipaddress
import json
import os
import re
import threading
import time

from .. import BasePlugin, Tool

BLOCK = os.urandom(1 << 20)       # 1 MiB of random bytes: nothing on the way can compress it
MAX_DOWN_MB = 256
MAX_UP_MB = 128
KEEP = 100
TEXT = {
    'en': {'tool': ('Speed tests between the owner\'s devices and the server: the latest one and averages per network. '
                    'E.g. "how fast is my connection?", "is the VPN slow?"', 'Checking the speed tests…'),
           'none': 'No speed test yet. It is run from the Speed card on the home screen.', 'other': 'elsewhere',
           'reference': '1080p video needs about 8 Mbps and 4K 25 Mbps; a ping under 30 ms is good.'},
    'es': {'tool': ('Mediciones de velocidad entre los aparatos del dueño y el servidor: la última y las medias por red. '
                    'Ej.: "¿qué velocidad tengo?", "¿va lenta la VPN?"', 'Mirando las mediciones…'),
           'none': 'Todavía no se ha medido la velocidad. Se mide desde la tarjeta Velocidad de la pantalla de inicio.',
           'other': 'otra red',
           'reference': 'Para vídeo 1080p hacen falta unos 8 Mbps y para 4K 25; un ping por debajo de 30 ms es bueno.'},
}


class Plugin(BasePlugin):
    name = 'speedtest'
    web = 'speedtest.js'

    def __init__(self, app, options):
        super().__init__(app, options)
        self.T = TEXT.get(app.lang, TEXT['en'])
        self.networks = [(n['name'], ipaddress.ip_network(n['cidr'], strict=False)) for n in options.get('networks', [])]
        self.max_mb = int(options.get('max_mb', MAX_DOWN_MB))
        self.path = os.path.join(app.conf['server']['data_dir'], 'speedtest.json')
        self.lock = threading.Lock()

    def where(self, ip):
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return self.T['other']
        return next((name for name, net in self.networks if addr in net), self.T['other'])

    def history(self):
        try:
            with open(self.path) as f:
                return json.load(f)
        except (OSError, ValueError):
            return []

    def save(self, req, body):
        try:
            m = {'ts': round(time.time()), 'down': round(float(body['down']), 1), 'up': round(float(body['up']), 1),
                 'ping': round(float(body['ping']), 1)}
        except (KeyError, TypeError, ValueError):
            return None
        ip = req.client_ip()
        m.update(where=self.where(ip), device=re.sub(r'\s+', ' ', req.headers.get('User-Agent') or '')[:80])
        with self.lock:
            hist = (self.history() + [m])[-KEEP:]
            tmp = self.path + '.tmp'
            with open(tmp, 'w') as f:
                json.dump(hist, f)
            os.replace(tmp, self.path)
        return m

    # ------------------------------------------------------------------ routes

    def routes(self):
        def ping(req):
            return 200, {'ok': 1, 'max_mb': self.max_mb}

        def down(req):
            mb = max(1, min(self.max_mb, int(req.query().get('mb') or 32)))
            req.send_response(200)
            req.send_header('Content-Type', 'application/octet-stream')
            req.send_header('Content-Length', str(mb << 20))
            req.send_header('Cache-Control', 'no-store')
            req.send_header('Content-Encoding', 'identity')
            req.end_headers()
            try:
                for _ in range(mb):
                    req.wfile.write(BLOCK)
            except (BrokenPipeError, ConnectionResetError, OSError):
                req.close_connection = True      # the browser stops reading after a few seconds: expected

        def up(req):
            n = int(req.headers.get('Content-Length') or 0)
            if n > min(self.max_mb, MAX_UP_MB) << 20:
                return 413, {'error': 'too large'}
            t0, got = time.perf_counter(), 0
            while got < n:
                chunk = req.rfile.read(min(1 << 20, n - got))
                if not chunk:
                    break
                got += len(chunk)
            secs = max(time.perf_counter() - t0, 0.001)
            return 200, {'bytes': got, 'secs': round(secs, 3), 'mbps': round(got * 8 / secs / 1e6, 2)}
        up.raw = True

        def result(req):
            m = self.save(req, req.body)
            return (200, m) if m else (400, {'error': 'bad result'})

        def history(req):
            return 200, self.history()[-12:]

        return {('GET', '/api/p/speedtest/ping'): ping, ('GET', '/api/p/speedtest/down'): down,
                ('POST', '/api/p/speedtest/up'): up, ('POST', '/api/p/speedtest/result'): result,
                ('GET', '/api/p/speedtest/history'): history}

    def tools(self):
        def speed():
            hist = self.history()
            if not hist:
                return {'result': self.T['none']}
            avg = {}
            for name in sorted({m['where'] for m in hist}):
                ms = [m for m in hist if m['where'] == name]
                avg[name] = {'tests': len(ms), **{k: round(sum(m[k] for m in ms) / len(ms), 1) for k in ('down', 'up', 'ping')}}
            last = hist[-1]
            return {'latest': {k: last[k] for k in ('down', 'up', 'ping', 'where')} |
                    {'when': time.strftime('%Y-%m-%d %H:%M', time.localtime(last['ts']))},
                    'average by network (Mbps, ms)': avg, 'reference': self.T['reference']}
        return [Tool('speed', self.T['tool'][0], speed, step=self.T['tool'][1])]
