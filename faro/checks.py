"""Service checks: HTTP, TCP and DNS, all in parallel every `checks.interval` seconds."""
import random
import socket
import ssl
import struct
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque

HISTORY = 90


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None     # a 302 to a login page still means "the service is up"


def make_opener(conf):
    chk = conf['checks']
    if chk['ca_file']:
        ctx = ssl.create_default_context(cafile=chk['ca_file'])
    elif chk['verify_tls']:
        ctx = ssl.create_default_context()
    else:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return urllib.request.build_opener(NoRedirect, urllib.request.HTTPSHandler(context=ctx))


def probe_http(opener, url, timeout):
    t = time.perf_counter()
    try:
        r = opener.open(urllib.request.Request(url, headers={'User-Agent': 'faro'}), timeout=timeout)
        code = r.status
        r.close()
    except urllib.error.HTTPError as e:
        code = e.code
    return code < 500, code, (time.perf_counter() - t) * 1000


def probe_dns(server, timeout, name='example.com'):
    """Sends one A query and expects NOERROR: proves the resolver answers, not just that port 53 is open."""
    host, _, port = server.partition(':')
    qid = random.randint(0, 65535)
    q = struct.pack('>HHHHHH', qid, 0x0100, 1, 0, 0, 0)
    q += b''.join(bytes([len(p)]) + p.encode() for p in name.split('.')) + b'\0' + struct.pack('>HH', 1, 1)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(timeout)
    t = time.perf_counter()
    try:
        s.sendto(q, (host, int(port or 53)))
        r = s.recv(512)
    finally:
        s.close()
    rcode = r[3] & 0x0f
    return struct.unpack('>H', r[:2])[0] == qid and rcode == 0, rcode, (time.perf_counter() - t) * 1000


def probe_tcp(target, timeout):
    host, port = target.rsplit(':', 1)
    t = time.perf_counter()
    socket.create_connection((host, int(port)), timeout=timeout).close()
    return True, None, (time.perf_counter() - t) * 1000


def reason(e):
    if 'CERTIFICATE' in str(e):
        return 'certificate'
    if isinstance(e, urllib.error.URLError) and isinstance(e.reason, Exception):
        e = e.reason
    return {ConnectionRefusedError: 'refused', TimeoutError: 'timeout', socket.timeout: 'timeout',
            socket.gaierror: 'dns'}.get(type(e), 'unreachable')


class Checks:
    def __init__(self, conf):
        self.conf = conf
        self.opener = make_opener(conf)
        self.lock = threading.Lock()
        now = time.time()
        self.state = {s['id']: {'up': None, 'ms': None, 'code': None, 'checked': 0, 'since': now,
                                'history': deque(maxlen=HISTORY)}
                      for s in conf['services'] if s['check'] != 'none'}

    def check(self, svc):
        timeout = self.conf['checks']['timeout']
        try:
            if svc['check'] == 'http':
                return probe_http(self.opener, svc['target'], timeout)
            if svc['check'] == 'dns':
                return probe_dns(svc['target'], timeout)
            if svc['check'] == 'tcp':
                return probe_tcp(svc['target'], timeout)
        except Exception as e:
            return False, reason(e), None
        return None, None, None

    def run_once(self):
        todo = [s for s in self.conf['services'] if s['check'] != 'none']
        results = {}
        threads = [threading.Thread(target=lambda s=s: results.__setitem__(s['id'], self.check(s)), daemon=True)
                   for s in todo]
        for th in threads:
            th.start()
        for th in threads:
            th.join(self.conf['checks']['timeout'] + 2)
        now = time.time()
        with self.lock:
            for sid, (up, code, ms) in results.items():
                st = self.state[sid]
                if st['up'] != up:
                    st['since'] = now
                st.update(up=up, code=code, ms=round(ms, 1) if ms else None, checked=now)
                st['history'].append([round(now), 1 if up else 0, st['ms']])

    def start(self):
        def loop():
            while True:
                self.run_once()
                time.sleep(self.conf['checks']['interval'])
        threading.Thread(target=loop, daemon=True, name='checks').start()

    def get(self, sid):
        with self.lock:
            st = self.state.get(sid)
            return dict(st) if st else None

    def snapshot(self, full):
        out = {}
        with self.lock:
            for sid, st in self.state.items():
                out[sid] = {k: (list(v) if isinstance(v, deque) else v) for k, v in st.items()
                            if full or k != 'history'}
                if not full and st['history']:
                    out[sid]['last'] = st['history'][-1]
        return out
