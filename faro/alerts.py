"""Turns state into alerts: something bad for long enough -> notify; fixed -> notify again.

Every alert is kept in a small log (the bell in the UI) and sent to the configured
notifiers: ntfy and/or a generic webhook (plain JSON, Discord or Slack format).
"""
import json
import os
import threading
import time
import urllib.request
from collections import deque

from .i18n import duration, gib, strings

LOG_SIZE = 300


class Notifier:
    def __init__(self, conf):
        self.conf = conf
        nt = conf['notify']
        self.ntfy = nt.get('ntfy')
        self.webhook = nt.get('webhook')

    @property
    def enabled(self):
        return bool(self.ntfy or self.webhook)

    def send(self, alert):
        for fn in (self._ntfy, self._webhook):
            threading.Thread(target=self._safe, args=(fn, alert), daemon=True).start()

    def _safe(self, fn, alert):
        try:
            fn(alert)
        except Exception as e:
            print(f'notify: {fn.__name__[1:]} failed for "{alert["title"]}": {e}', flush=True)

    def _post(self, url, body, headers=None):
        req = urllib.request.Request(url, data=json.dumps(body).encode(), method='POST',
                                     headers={'Content-Type': 'application/json', 'User-Agent': 'faro',
                                              **(headers or {})})
        urllib.request.urlopen(req, timeout=10).close()

    def _ntfy(self, a):
        if not self.ntfy:
            return
        body = {'topic': self.ntfy['topic'], 'title': a['title'], 'message': a['body'] or a['title'],
                'priority': a['priority'], 'tags': [{'bad': 'red_circle', 'good': 'green_circle',
                                                     'info': 'information_source'}[a['level']]]}
        if a.get('url'):
            body['click'] = a['url']
        headers = {'Authorization': 'Bearer ' + self.ntfy['token']} if self.ntfy.get('token') else {}
        self._post(self.ntfy['url'], body, headers)

    def _webhook(self, a):
        if not self.webhook:
            return
        fmt = self.webhook['format']
        text = f'**{a["title"]}**\n{a["body"]}' if a['body'] else f'**{a["title"]}**'
        if fmt == 'discord':
            body = {'content': text}
        elif fmt == 'slack':
            body = {'text': text.replace('**', '*')}
        else:
            body = a
        self._post(self.webhook['url'], body)


class Alerts:
    def __init__(self, conf, hosts, checks):
        self.conf = conf
        self.hosts = hosts
        self.checks = checks
        self.notifier = Notifier(conf)
        self.T = strings(conf['language'] if conf['language'] != 'auto' else 'en')
        self.lang = conf['language'] if conf['language'] in ('en', 'es') else 'en'
        self.watch = {}                               # key -> {'since', 'fired'}
        self.log = deque(maxlen=LOG_SIZE)
        self.lock = threading.Lock()
        self.path = os.path.join(conf['server']['data_dir'], 'alerts.json')
        self.base = conf['server']['public_url']
        try:
            with open(self.path) as f:
                self.log.extend(json.load(f))
        except (OSError, ValueError):
            pass

    # ------------------------------------------------------------- emitting

    def emit(self, level, title, body='', priority=3, url=None, key=None):
        a = {'ts': time.time(), 'level': level, 'title': title, 'body': body, 'priority': priority,
             'url': url or (self.base or None), 'key': key}
        with self.lock:
            self.log.append(a)
            snap = list(self.log)
        print(f'alert: {title}', flush=True)
        self.notifier.send(a)
        try:
            tmp = self.path + '.tmp'
            with open(tmp, 'w') as f:
                json.dump(snap, f, ensure_ascii=False)
            os.replace(tmp, self.path)
        except OSError:
            pass

    def recent(self, n=120):
        with self.lock:
            return list(self.log)[-n:][::-1]

    def active(self):
        """Keys that are currently firing: the UI shows them as open problems."""
        return [k for k, w in self.watch.items() if w['fired']]

    def track(self, key, bad, wait, on_bad, on_good):
        """Fires on_bad() once `bad` has held for `wait` seconds, and on_good(duration) when it clears."""
        w = self.watch.setdefault(key, {'since': None, 'fired': False})
        now = time.time()
        if bad:
            w['since'] = w['since'] or now
            if not w['fired'] and now - w['since'] >= wait:
                w['fired'] = True
                self.emit('bad', *on_bad(), key=key)
        else:
            if w['fired']:
                self.emit('good', *on_good(now - w['since']), key=key)
            w['since'], w['fired'] = None, False

    # ------------------------------------------------------------- rules

    def evaluate(self):
        T, al, lang = self.T, self.conf['alerts'], self.lang
        link = lambda frag: f'{self.base}/#{frag}' if self.base else None    # noqa: E731

        for s in self.conf['services']:
            st = self.checks.get(s['id'])
            if not st:
                continue
            code = st['code']
            why = f'HTTP {code}' if isinstance(code, int) else T['reason'].get(code, code or '')
            what = s['description'] or s.get('target') or ''
            self.track('svc:' + s['id'], st['up'] is False, al['service_down_after'],
                       lambda s=s, what=what, why=why: (
                           T['svc_down'].format(name=s['name']),
                           T['svc_down_body'].format(what=what, reason=(' · ' if what and why else '') + why),
                           4, s['url'] or link('services')),
                       lambda d, s=s: (T['svc_up'].format(name=s['name']),
                                       T['svc_up_body'].format(dur=duration(d, lang)), 3, s['url'] or None))

        now = time.time()
        for h in self.conf['hosts']:
            seen = self.hosts.seen(h['id'])
            limit = al['host_offline_after']
            self.track('host:' + h['id'], not seen or now - seen > limit, 0,
                       lambda h=h: (T['host_off'].format(name=h['name']),
                                    T['host_off_body'].format(name=h['name'], address=h['address'], secs=limit),
                                    5, link('system')),
                       lambda d, h=h: (T['host_on'].format(name=h['name']),
                                       T['host_on_body'].format(dur=duration(d + limit, lang)), 3, link('system')))
            d = self.hosts.data(h['id']) or {}
            self._disks(h, d, link)
            self._storage(h, d, link)

    def _disks(self, h, d, link):
        T, al, lang = self.T, self.conf['alerts'], self.lang
        for x in d.get('disks') or []:
            sm = x.get('smart') or {}
            if not sm or sm.get('standby'):
                continue
            cfg = next((c for c in self.conf['disks'] if c['host'] == h['id'] and c['serial'] == x.get('serial')), {})
            name = cfg.get('label') or x['name']
            key = f'{h["id"]}:{x.get("serial") or x["name"]}'
            bad_sectors = (sm.get('realloc') or 0) + (sm.get('pending') or 0)
            what = T['smart_failed'] if sm.get('healthy') is False else T['smart_sectors'].format(n=bad_sectors)
            self.track('smart:' + key, sm.get('healthy') is False or bad_sectors > 0, 0,
                       lambda name=name, x=x, what=what: (
                           T['smart_bad'].format(name=name),
                           T['smart_bad_body'].format(host=h['name'], model=x.get('model'), what=what),
                           5, link('disks')),
                       lambda _d, name=name: (T['smart_ok'].format(name=name), T['smart_ok_body'], 3, link('disks')))
            t = sm.get('temp')
            if t is None:
                continue
            limit = al['disk_temp_nvme'] if x.get('tran') == 'nvme' else \
                al['disk_temp_hdd'] if x.get('rota') else al['disk_temp_ssd']
            hot_key = 'temp:' + key
            # 3 °C of hysteresis so it does not flap around the limit
            hot = t >= (limit - 3 if self.watch.get(hot_key, {}).get('fired') else limit)
            self.track(hot_key, hot, 300,
                       lambda name=name, t=t: (T['disk_hot'].format(name=name),
                                               T['disk_hot_body'].format(host=h['name'], temp=t), 4, link('disks')),
                       lambda dd, name=name: (T['disk_cool'].format(name=name),
                                              T['disk_cool_body'].format(dur=duration(dd, lang)), 3, link('disks')))

    def _storage(self, h, d, link):
        T, al = self.T, self.conf['alerts']
        for f in d.get('fs') or []:
            pct = round(100 * f['used'] / f['total']) if f['total'] else 0
            key = f'fs:{h["id"]}:{f["mount"]}'
            limit = al['disk_full_percent']
            full = pct >= (limit - 2 if self.watch.get(key, {}).get('fired') else limit)
            self.track(key, full, 60,
                       lambda f=f, pct=pct: (T['fs_full'].format(mount=f['mount'], host=h['name']),
                                             T['fs_full_body'].format(pct=pct, free=gib(f['avail'])), 4, link('disks')),
                       lambda _d, f=f, pct=pct: (T['fs_ok'].format(mount=f['mount'], host=h['name']),
                                                 T['fs_ok_body'].format(pct=pct), 3, link('disks')))
        for p in (d.get('zfs') or {}).get('pools') or []:
            self.track(f'pool:{h["id"]}:{p["name"]}', p['health'] != 'ONLINE', 0,
                       lambda p=p: (T['pool_bad'].format(name=p['name'], health=p['health']),
                                    T['pool_bad_body'].format(host=h['name'], name=p['name']), 5, link('disks')),
                       lambda _d, p=p: (T['pool_ok'].format(name=p['name']),
                                        T['pool_ok_body'].format(host=h['name']), 3, link('disks')))

    def start(self, grace=60):
        def loop():
            time.sleep(grace)         # let data and checks arrive before judging anything
            while True:
                try:
                    self.evaluate()
                except Exception as e:     # a bad rule must never stop the others
                    print('alerts:', type(e).__name__, e, flush=True)
                time.sleep(10)
        threading.Thread(target=loop, daemon=True, name='alerts').start()

    def test(self):
        self.emit('info', self.T['test'], self.T['test_body'], 3)
